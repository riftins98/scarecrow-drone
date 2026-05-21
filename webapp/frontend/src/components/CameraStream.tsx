import React, { useEffect, useRef, useState } from 'react';
import { CameraInfo } from '../types/flight';
import { setSimCamera } from '../services/api';

interface Props {
  /** Backend-captured stream root, e.g. `http://localhost:8080`. The same
   *  URL the popout link uses — embeds the WebRTC viewer page directly. */
  streamUrl: string | null;
  /** Sim is mid-launch. Skip the embed and show a STANDBY state — the
   *  stream server isn't up yet and trying to load just produces a flicker
   *  of "offline/retry" the user can't act on. */
  launching: boolean;
  /** Sim is fully connected. We only attempt the iframe once this is true. */
  connected: boolean;
  /** Camera flag stem currently streamed (e.g. "fixed", "center"). Used
   *  for the header label. Null in GUI mode. */
  camera: string | null;
  /** Cameras the active world offers; powers the live-switch dropdown.
   *  Empty array hides the dropdown entirely. */
  availableCameras: CameraInfo[];
}

/**
 * Embeds the headless Gazebo camera by iframing the launcher's own WebRTC
 * viewer page. The page does its own SDP/ICE handshake against /offer on
 * the same origin, so there's no CORS to navigate from our side.
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
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  // True while a switch_camera POST is in flight; flips back when the
  // confirmed `camera` prop matches the requested one (or after a timeout).
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);
  // Camera we asked the backend to switch to; null when no swap is in flight.
  const pendingCamRef = useRef<string | null>(null);

  // When the sim transitions from "not connected" to "connected" make sure
  // we have a fresh iframe load (in case the stream came up *after* the
  // iframe initially mounted with a 404).
  useEffect(() => {
    if (connected && streamUrl) {
      setNonce(n => n + 1);
    }
  }, [connected, streamUrl]);

  // Clear the "switching" overlay once the backend confirms the new camera.
  // The status poller in Dashboard refreshes /api/sim/status every 3s, so
  // worst case the user sees the SWITCHING overlay for that long; we also
  // bump the iframe nonce here so it re-handshakes against the new stream.
  useEffect(() => {
    if (!switching) return;
    if (pendingCamRef.current && camera === pendingCamRef.current) {
      pendingCamRef.current = null;
      setSwitching(false);
      setNonce(n => n + 1);
    }
  }, [camera, switching]);

  const handleSwitch = async (next: string) => {
    if (!next || next === camera || switching) return;
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
      // No-op (already on the requested camera): clear immediately.
      if (res.noop) {
        setSwitching(false);
        pendingCamRef.current = null;
      }
      // Otherwise the effect above will clear once status reflects the swap.
    } catch (e: unknown) {
      setSwitchError(e instanceof Error ? e.message : String(e));
      setSwitching(false);
      pendingCamRef.current = null;
    }
  };

  const state: 'no-url' | 'standby' | 'live' =
    !streamUrl ? 'no-url'
    : launching || !connected ? 'standby'
    : 'live';

  const reload = () => setNonce(n => n + 1);

  return (
    <div className="camstream">
      <div className="camstream-header">
        <span className="camstream-title">
          CAM // {camera ? camera.toUpperCase() : 'FIXED'}
        </span>
        <span className={`camstream-pill camstream-pill-${state}`}>
          {switching ? 'SWITCHING'
            : state === 'live' ? 'LIVE'
            : state === 'standby' ? 'STANDBY'
            : 'NO SIGNAL'}
        </span>
        {state === 'live' && availableCameras.length > 1 && (
          <select
            className="camstream-select"
            value={camera ?? ''}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => handleSwitch(e.target.value)}
            disabled={switching}
            aria-label="Switch camera"
          >
            {availableCameras.map((c: CameraInfo) => (
              <option key={c.name} value={c.name}>{c.label}</option>
            ))}
          </select>
        )}
        {state === 'live' && (
          <button
            type="button"
            className="camstream-popout camstream-reload"
            onClick={reload}
            title="Reload stream"
            aria-label="Reload camera stream"
            disabled={switching}
          >
            <ReloadIcon />
          </button>
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
        {state === 'live' && streamUrl && (
          <iframe
            key={nonce}
            ref={iframeRef}
            src={streamUrl}
            className="camstream-iframe"
            title="Camera feed"
            allow="autoplay"
          />
        )}
        {state === 'live' && switching && (
          <div className="camstream-overlay camstream-overlay-switching">
            <div className="camstream-spinner" aria-hidden="true" />
            <div className="camstream-overlay-text">
              SWITCHING TO {pendingCamRef.current?.toUpperCase() ?? '…'}
            </div>
            <div className="camstream-overlay-sub">
              respawning stream worker — ~2s
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

      <div className="camstream-footer">
        <span className="camstream-meta">
          {streamUrl ? `SRC: ${streamUrl}` : '—'}
        </span>
        <span className="camstream-meta">WebRTC // H.264</span>
      </div>
    </div>
  );
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

function ReloadIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 3 V7 H9" />
      <path d="M3 13 V9 H7" />
      <path d="M12.5 7 A5 5 0 0 0 3.5 7" />
      <path d="M3.5 9 A5 5 0 0 0 12.5 9" />
    </svg>
  );
}
