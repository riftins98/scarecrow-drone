import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getSimLog, simLogViewUrl, ApiError } from '../services/api';

interface Props {
  /** Are we currently connected to the sim? Controls poll rate + placeholder state. */
  connected: boolean;
  /** Active flight? Just used to label the header pill. */
  flying: boolean;
}

interface LogEntry {
  /** Absolute line index from the backend. Stable across the run. */
  idx: number;
  text: string;
}

interface Gap {
  kind: 'gap';
  idx: number;
  count: number;
}

type Row = LogEntry | Gap;

const MAX_RENDERED_ROWS = 600;

/**
 * Tail of the live flight-script stdout. Polls /api/flight/log every second,
 * passing back the last cursor so the backend only sends new lines.
 *
 * Three modes:
 *   normal     — embedded in the dashboard at its natural size
 *   expanded   — full-window overlay (Esc or the same button to close)
 *   (popout)   — opens /api/flight/log/view in a new browser tab; that page
 *                runs its own polling independent of React
 *
 * Buffer drops are surfaced as visible "[N lines dropped]" gap markers so
 * users can see they missed something.
 */
export default function SystemLog({ connected, flying }: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [cursor, setCursor] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [autoscroll, setAutoscroll] = useState(true);
  const [running, setRunning] = useState(false);
  // When the backend doesn't have the log route yet (e.g. it predates the
  // feature), it returns 404. Stop polling rather than spam the console
  // and the network tab — once the backend is restarted with the route,
  // refreshing the page will pick it back up.
  const [routeMissing, setRouteMissing] = useState(false);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  // Reset rows when sim is disconnected — old launcher output isn't useful
  // once the user is back in pre-connect mode. New launch starts fresh.
  useEffect(() => {
    if (!connected) {
      setRows([]);
      setCursor(0);
      setRunning(false);
    }
  }, [connected]);

  // Poll loop. 1s when connected, 3s otherwise (so the page still detects
  // a fresh flight starting without hammering the server while idle).
  // Uses a ref for cursor so each tick reads the latest value without the
  // effect needing to restart every time we advance the cursor — that was
  // burning a setInterval/clearInterval per second.
  const cursorRef = useRef(0);
  useEffect(() => { cursorRef.current = cursor; }, [cursor]);

  useEffect(() => {
    if (routeMissing) return;
    let cancelled = false;
    const intervalMs = connected ? 1000 : 3000;

    const tick = async () => {
      try {
        const data = await getSimLog(cursorRef.current);
        if (cancelled) return;
        setRunning(data.running);
        if (data.lines.length === 0 && data.dropped === 0) return;

        setRows(prev => {
          const next: Row[] = [...prev];
          if (data.dropped > 0) {
            next.push({ kind: 'gap', idx: data.start, count: data.dropped });
          }
          let idx = data.start;
          for (const text of data.lines) {
            next.push({ idx, text });
            idx += 1;
          }
          // Cap at MAX_RENDERED_ROWS so very long flights don't drag the DOM down.
          if (next.length > MAX_RENDERED_ROWS) {
            return next.slice(next.length - MAX_RENDERED_ROWS);
          }
          return next;
        });
        setCursor(data.cursor);
      } catch (e) {
        // Backend missing the route entirely -> stop polling. Any other
        // error (network blip, 500, etc.) -> keep retrying silently.
        if (e instanceof ApiError && e.status === 404) {
          if (!cancelled) setRouteMissing(true);
        }
      }
    };

    tick();
    const id = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [connected, routeMissing]);

  // Autoscroll on new content.
  useEffect(() => {
    if (!autoscroll) return;
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [rows, autoscroll]);

  // Esc closes the expanded overlay.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded]);

  // Detect "user scrolled away from bottom" to pause autoscroll, then
  // re-engage when they return to the bottom.
  const onScroll = () => {
    const el = bodyRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom !== autoscroll) setAutoscroll(atBottom);
  };

  const headerPill = routeMissing
    ? 'NO LOG ROUTE'
    : !connected
    ? 'OFFLINE'
    : running
    ? 'STREAMING'
    : flying
    ? 'WAITING'
    : 'IDLE';

  const panel = (variant: 'inline' | 'overlay') => (
    <div className={`syslog ${variant === 'overlay' ? 'syslog-expanded' : ''}`}>
      <div className="syslog-header">
        <span className={`syslog-pill ${running ? 'on' : 'off'}`}>{headerPill}</span>
        <span className="syslog-spacer" />
        <div className="syslog-actions">
          <button
            type="button"
            className="syslog-btn"
            onClick={() => setExpanded(e => !e)}
            title={variant === 'overlay' ? 'Collapse' : 'Expand to full window'}
            aria-label={variant === 'overlay' ? 'Collapse log' : 'Expand log to full window'}
          >
            {variant === 'overlay' ? <IconCollapse /> : <IconExpand />}
          </button>
          <button
            type="button"
            className="syslog-btn"
            onClick={() => window.open(simLogViewUrl(), '_blank', 'noopener,noreferrer')}
            title="Open in new browser tab"
            aria-label="Open log in new browser tab"
          >
            <IconPopout />
          </button>
        </div>
        <span className="syslog-light" />
      </div>
      <div
        className="syslog-body"
        ref={variant === 'inline' ? bodyRef : undefined}
        onScroll={variant === 'inline' ? onScroll : undefined}
      >
        {rows.length === 0 && (
          <div className={`syslog-line ${routeMissing ? 'syslog-level-warn' : 'syslog-level-info'}`}>
            <span className="syslog-ts">-----</span>
            <span className="syslog-level">{routeMissing ? 'WARN' : 'INFO'}</span>
            <span className="syslog-msg">
              {routeMissing
                ? 'backend does not expose /api/sim/log yet — restart backend to enable live log'
                : 'awaiting sim launch…'}
            </span>
          </div>
        )}
        {rows.map(row =>
          isGap(row) ? (
            <div key={`gap-${row.idx}`} className="syslog-gap">
              … {row.count} line{row.count === 1 ? '' : 's'} dropped (buffer rolled) …
            </div>
          ) : (
            <div key={row.idx} className={`syslog-line ${levelClassFor(row.text)}`}>
              <span className="syslog-ts">{row.idx.toString().padStart(5, '0')}</span>
              <span className="syslog-level">{levelTagFor(row.text)}</span>
              <span className="syslog-msg">{row.text}</span>
            </div>
          )
        )}
        <div className="syslog-cursor">_</div>
      </div>
      <div className="syslog-footer">
        <label className="syslog-toggle">
          <input
            type="checkbox"
            checked={autoscroll}
            onChange={e => setAutoscroll(e.target.checked)}
          />
          AUTOSCROLL
        </label>
        {variant === 'overlay' && (
          <button
            type="button"
            className="syslog-btn syslog-close"
            onClick={() => setExpanded(false)}
            aria-label="Close expanded log"
          >
            CLOSE
          </button>
        )}
      </div>
    </div>
  );

  // The inline panel always stays mounted in the Dashboard grid. When the
  // user expands, we ALSO render an overlay copy via a portal to document.body.
  // This keeps SimControl + Minimap untouched in the DOM, so their internal
  // state (selected world, headless flag, script picker, arg values) is
  // preserved across expand/collapse cycles.
  return (
    <>
      {panel('inline')}
      {expanded && typeof document !== 'undefined' && createPortal(
        <div className="syslog-overlay" onClick={() => setExpanded(false)}>
          <div className="syslog-overlay-inner" onClick={e => e.stopPropagation()}>
            {panel('overlay')}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

function isGap(row: Row): row is Gap {
  return (row as Gap).kind === 'gap';
}

/**
 * Infer a level tag for color-coding from the raw stdout line. The flight
 * scripts don't emit structured levels, so we recognise the well-known
 * protocol lines and a few common phrases. Unknown lines fall through as INFO.
 */
function levelTagFor(line: string): string {
  if (line.startsWith('TELEMETRY:'))   return 'TEL';
  if (line.startsWith('DETECTION_IMAGE:')) return 'DET';
  if (line.startsWith('VIDEO_PATH:'))  return 'VID';
  if (line.startsWith('ABORT_REQUESTED')) return 'ABRT';
  const lower = line.toLowerCase();
  if (/(error|traceback|exception|failed|fatal)/.test(lower)) return 'ERR';
  if (/(warn|warning|denied)/.test(lower)) return 'WARN';
  if (/(takeoff|land|arm|hover|hold|wall_follow|heading|altitude)/.test(lower)) return 'NAV';
  if (/(ekf|imu|optical|flow|attitude|estimator)/.test(lower)) return 'EKF';
  if (/(frame |pigeon|yolo|conf )/.test(lower)) return 'DET';
  return 'INFO';
}

function levelClassFor(line: string): string {
  const tag = levelTagFor(line).toLowerCase();
  if (tag === 'abrt') return 'syslog-level-err';
  return `syslog-level-${tag}`;
}

function IconExpand() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6 V3 H6 M13 6 V3 H10 M3 10 V13 H6 M13 10 V13 H10" />
    </svg>
  );
}

function IconCollapse() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 3 V6 H3 M10 3 V6 H13 M6 13 V10 H3 M10 13 V10 H13" />
    </svg>
  );
}

function IconPopout() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 3 H13 V7" />
      <path d="M13 3 L7 9" />
      <path d="M11 9 V13 H3 V5 H7" />
    </svg>
  );
}
