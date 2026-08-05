import React, { useEffect, useRef, useState } from 'react';
import { CameraInfo } from '../types/flight';
import { setSimCamera } from '../services/api';

interface Props {
  /** Backend-captured stream root, e.g. `http://localhost:8080`. The same
   *  URL the popout link uses — embeds the MJPEG viewer page directly. */
  streamUrl: string | null;
  /** Sim is mid-launch. Skip the embed and show a STANDBY state — the
   *  stream server isn't up yet and trying to load just produces a flicker
   *  of "offline/retry" the user can't act on. */
  launching: boolean;
  /** Sim is fully connected. We only attempt the iframe once this is true. */
  connected: boolean;
  /** Camera flag stem currently streamed (e.g. "fixed", "drone_view"). Used
   *  for the header label. Null in GUI mode. */
  camera: string | null;
  /** Cameras the active world offers; used only to display the active label. */
  availableCameras: CameraInfo[];
}

/**
 * Embeds the headless Gazebo camera by iframing the launcher's own MJPEG
 * viewer page. The page pulls its own multipart stream from the same origin,
 * so there's no CORS to navigate from our side.
 *
 * States:
 *   no-url      — GUI mode or launcher hasn't surfaced the URL yet
 *   standby     — sim is launching; don't try to embed yet
 *   live        — connected, iframe mounted
 */
export default function CameraStream({
  streamUrl, launching, connected, camera, availableCameras,
}: Props) {
  // Bumping nonce remounts the iframe, forcing a fresh page load.
  const [nonce, setNonce] = useState(0);
  // Keep live-switch plumbing available for future UI, even though the current
  // header intentionally displays only the selected launch camera.
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const pendingCamRef = useRef<string | null>(null);

  // When the sim transitions from "not connected" to "connected" make sure
  // we have a fresh iframe load (in case the stream came up *after* the
  // iframe initially mounted with a 404).
  useEffect(() => {
    if (connected && streamUrl) {
      setNonce(n => n + 1);
    }
  }, [connected, streamUrl]);

  useEffect(() => {
    if (!switching) return;
    if (pendingCamRef.current && camera === pendingCamRef.current) {
      pendingCamRef.current = null;
      setSwitching(false);
      setNonce(n => n + 1);
    }
  }, [camera, switching]);

  const handleSwitch = async (next: string) => {
    if (!next || next === camera || switching || !streamUrl) return;
    setSwitching(true);
    setSwitchError(null);
    pendingCamRef.current = next;
    try {
      const res = await setSimCamera(next);
      if (!res.success) {
        setSwitchError(res.error || 'switch failed');
        setSwitching(false);
        pendingCamRef.current = null;
        return;
      }
      if (res.noop) {
        setSwitching(false);
        pendingCamRef.current = null;
        return;
      }
      await waitForStreamer(streamUrl);
      pendingCamRef.current = null;
      setSwitching(false);
      setNonce(n => n + 1);
    } catch (e: unknown) {
      setSwitchError(e instanceof Error ? e.message : String(e));
      setSwitching(false);
      pendingCamRef.current = null;
    }
  };
  void handleSwitch;

  const state: 'no-url' | 'standby' | 'live' =
    !streamUrl ? 'no-url'
    : launching || !connected ? 'standby'
    : 'live';
  const cameraLabel =
    availableCameras.find((c: CameraInfo) => c.name === camera)?.label
    ?? (camera ? camera.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase()) : null);

  return (
    <div className="camstream">
        <div className="camstream-header">
          <span className="camstream-title">Camera</span>
          <span className={`camstream-pill camstream-pill-${state}`}>
          {state === 'live' ? 'LIVE'
            : state === 'standby' ? 'STANDBY'
            : 'NO SIGNAL'}
          </span>
        {state === 'live' && cameraLabel && (
          <span className="camstream-current-camera" aria-label="Current camera">
            {cameraLabel}
          </span>
        )}
        {streamUrl && (
          <a
            className="camstream-popout"
            href={streamUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="Open in new browser tab"
            aria-label="Open camera stream in new tab"
          >
            <PopoutIcon />
          </a>
        )}
      </div>

      <div className="camstream-frame">
        {/* Unmount the iframe entirely while switching. Otherwise the old
            iframe stays mounted pointing at a dead/respawning server, the
            browser caches a connection-refused on the origin, and that
            cache survives the subsequent key-bump remount, leaving you
            with a permanent "refused to connect" error.
            By killing the iframe DOM node here, the browser drops its
            connection state for the origin; the remount after `switching`
            clears is a true cold load. */}
        {state === 'live' && streamUrl && !switching && (
          <iframe
            key={nonce}
            // Cache-buster baked into nonce — Chrome's negative connection
            // cache is keyed on the request URL, so varying the query string
            // on every remount forces a fresh attempt instead of replaying
            // a cached "connection refused".
            src={`${streamUrl}/?n=${nonce}`}
            className="camstream-iframe"
            title="Camera feed"
            allow="autoplay"
          />
        )}
        {state === 'live' && switching && (
          <div className="camstream-overlay camstream-overlay-switching">
            <div className="camstream-spinner" aria-hidden="true" />
            <div className="camstream-overlay-text">
              SWITCHING TO {pendingCamRef.current?.toUpperCase() ?? '...'}
            </div>
            <div className="camstream-overlay-sub">
              respawning stream worker - ~2s
            </div>
          </div>
        )}
        {state === 'live' && switchError && !switching && (
          <div className="camstream-error-banner">
            switch failed: {switchError}
          </div>
        )}
        {state === 'standby' && (
          <div className="camstream-overlay camstream-overlay-standby">
            <div className="camstream-spinner" aria-hidden="true" />
            <div className="camstream-overlay-text">SIM LAUNCHING</div>
            <div className="camstream-overlay-sub">
              stream comes online after launch completes
            </div>
          </div>
        )}
        {state === 'no-url' && (
          <div className="camstream-overlay camstream-overlay-no-url">
            <div className="camstream-noise" aria-hidden="true" />
            <div className="camstream-overlay-text">NO STREAM CONFIGURED</div>
            <div className="camstream-overlay-sub">
              connect with headless mode to enable camera feed
            </div>
          </div>
        )}
      </div>

    </div>
  );
}

async function waitForStreamer(streamUrl: string, maxMs = 10000): Promise<void> {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const probe = `${streamUrl}/?_=${Date.now()}`;
    try {
      await fetch(probe, { mode: 'no-cors', cache: 'no-store' });
      return;
    } catch {
      await new Promise(r => setTimeout(r, 300));
    }
  }
  throw new Error('streamer did not become ready within ' + maxMs + 'ms');
}

function PopoutIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 3 H13 V7" />
      <path d="M13 3 L7 9" />
      <path d="M11 9 V13 H3 V5 H7" />
    </svg>
  );
}
