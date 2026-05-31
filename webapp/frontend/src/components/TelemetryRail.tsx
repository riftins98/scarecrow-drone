import React, { useEffect, useRef, useState } from 'react';
import { FlightStatus, SimStatus } from '../types/flight';

interface Props {
  /** Sim status; used only to gate display on connection. */
  simStatus: SimStatus | null;
  /** Flight status; we read the latest (log-parsed) TELEMETRY payload from
   *  .telemetry plus frames_processed from the top level. */
  flightStatus: FlightStatus | null;
}

type Color = 'olive' | 'teal' | 'red';

/**
 * Shared instant tooltip. The rail scrolls horizontally (`overflow-x: auto`),
 * which clips any child positioned outside it, so the tooltip is rendered as a
 * single `position: fixed` element at the document layer and follows the
 * cursor. `bind(text)` returns the mouse handlers a gauge spreads onto its root.
 */
interface Tooltip {
  bind: (text: string) => {
    onMouseEnter: (e: React.MouseEvent) => void;
    onMouseMove: (e: React.MouseEvent) => void;
    onMouseLeave: () => void;
  };
  node: React.ReactNode;
}

function useTooltip(): Tooltip {
  const [state, setState] = useState<{ text: string; x: number; y: number } | null>(null);

  const bind = (text: string) => ({
    onMouseEnter: (e: React.MouseEvent) => setState({ text, x: e.clientX, y: e.clientY }),
    onMouseMove: (e: React.MouseEvent) =>
      setState((s) => (s ? { ...s, x: e.clientX, y: e.clientY } : { text, x: e.clientX, y: e.clientY })),
    onMouseLeave: () => setState(null),
  });

  // Flip below the cursor when there isn't room above (the rail sits near the
  // top of the page, so above-cursor tooltips can run off-screen).
  const below = state ? state.y < 90 : false;
  const node = state ? (
    <div
      className={`tel-tooltip ${below ? 'tel-tooltip-below' : ''}`}
      role="tooltip"
      // Fixed so the rail's overflow can't clip it; offset from the cursor so
      // it doesn't sit directly under the pointer.
      style={{ left: state.x + 12, top: below ? state.y + 18 : state.y - 14 }}
    >
      {state.text}
    </div>
  ) : null;

  return { bind, node };
}

/**
 * One readout's spec. The rail is data-driven from RAIL_SPEC so behavior is
 * uniform: a `core` gauge shows from the moment a flight starts (reading "--"
 * until data arrives); a non-core gauge is "sticky" — it appears the first
 * time its value shows and then stays pinned for the rest of the flight even
 * if the value later drops to null. The set resets on a new flight.
 */
interface RailItem {
  key: string;
  label: string;
  /** Short hover explanation. */
  tip: string;
  /** Shown from flight start (vs. appearing only once data first arrives). */
  core?: boolean;
  /** Pull this readout's raw value out of the flight status. */
  get: (tel: Telemetry, frames: number | undefined) => number | string | null | undefined;
  /** How to render it. */
  render: (value: number | string | null, item: RailItem, tooltip: Tooltip) => React.ReactNode;
}

type Telemetry = NonNullable<FlightStatus['telemetry']>;

// Proximity gauge factory (lidar distances): 0..5m, red when < 0.5m.
const distGauge = (key: string, label: string, tip: string): RailItem => ({
  key, label, tip,
  get: (tel) => (tel as any)[key],
  render: (v, _i, tt) => (
    <Gauge label={label} unit="M" value={v as number | null} max={5} decimals={2}
           color={typeof v === 'number' && v < 0.5 ? 'red' : 'teal'} tip={tip} tooltip={tt} />
  ),
});

// The full catalog, in display order. `core` ones anchor the rail at flight
// start; the rest are sticky add-ons relevant only to certain scripts.
const RAIL_SPEC: RailItem[] = [
  { key: 'phase', label: 'PHASE', core: true, tip: 'Current mission phase (takeoff, hover, descent, …).',
    get: (t) => t.phase ?? null,
    render: (v, i, tt) => <Readout label={i.label} value={v as string | null} color="teal" tip={i.tip} tooltip={tt} /> },
  { key: 'target', label: 'TARGET', tip: 'Pigeon-pursuit outcome: REACHED or the reason pursuit ended.',
    get: (t) => t.target ?? null,
    render: (v, i, tt) => <Readout label={i.label} value={v as string | null} color={v === 'REACHED' ? 'olive' : 'red'} tip={i.tip} tooltip={tt} /> },
  { key: 'stop_reason', label: 'STOP', tip: 'Why the wall-follow run stopped (e.g. front wall, health lost).',
    get: (t) => t.stop_reason ?? null,
    render: (v, i, tt) => <Readout label={i.label} value={v as string | null} color="red" tip={i.tip} tooltip={tt} /> },
  { key: 'altitude', label: 'ALT', core: true, tip: 'Altitude above ground from the flight controller, in meters.',
    get: (t) => t.altitude ?? null,
    render: (v, i, tt) => <Gauge label={i.label} unit="M" value={v as number | null} max={5} decimals={2} color="olive" tip={i.tip} tooltip={tt} /> },
  { key: 'agl', label: 'AGL', tip: 'Live altitude-above-ground during climb/descent, parsed from log lines.',
    get: (t) => t.agl ?? null,
    render: (v, i, tt) => <Gauge label={i.label} unit="M" value={v as number | null} max={5} decimals={2} color="olive" tip={i.tip} tooltip={tt} /> },
  { key: 'ceiling', label: 'CEILING', tip: 'Clearance to the ceiling from the upward rangefinder, in meters.',
    get: (t) => t.ceiling ?? null,
    render: (v, i, tt) => <Gauge label={i.label} unit="M" value={v as number | null} max={3} decimals={2} color="teal" tip={i.tip} tooltip={tt} /> },
  distGauge('front', 'FRONT', 'Lidar distance to the wall ahead, in meters (red under 0.5m).'),
  distGauge('left', 'LEFT', 'Lidar distance to the wall on the left, in meters (red under 0.5m).'),
  distGauge('right', 'RIGHT', 'Lidar distance to the wall on the right, in meters (red under 0.5m).'),
  distGauge('rear', 'REAR', 'Lidar distance to the wall behind, in meters (red under 0.5m).'),
  distGauge('wall', 'WALL', 'Distance to the wall the controller is following, in meters.'),
  { key: 'heading', label: 'HDG', core: true, tip: 'Compass heading (yaw), 0–360 degrees.',
    get: (t) => t.heading ?? null,
    render: (v, i, tt) => <HeadingGauge value={v as number | null} tip={i.tip} tooltip={tt} /> },
  { key: 'vel', label: 'VEL', tip: 'Commanded velocity: F=forward, L=lateral (m/s), Y=yaw rate (deg/s).',
    get: (t) => {
      const parts: string[] = [];
      if (typeof t.fwd === 'number') parts.push(`F${signed(t.fwd)}`);
      if (typeof t.lat === 'number') parts.push(`L${signed(t.lat)}`);
      if (typeof t.yaw === 'number') parts.push(`Y${signed(t.yaw)}`);
      return parts.length ? parts.join(' ') : null;
    },
    render: (v, i, tt) => <Readout label={i.label} value={v as string | null} color="olive" tip={i.tip} tooltip={tt} /> },
  { key: 'distance', label: 'DIST', core: true, tip: 'Straight-line distance from the takeoff point, in meters.',
    get: (t) => t.distance ?? null,
    render: (v, i, tt) => <Gauge label={i.label} unit="M" value={v as number | null} max={10} decimals={2} color="olive" tip={i.tip} tooltip={tt} /> },
  { key: 'leg', label: 'LEG', tip: 'Room-circuit leg number completed.',
    get: (t) => t.leg ?? null,
    render: (v, i, tt) => <Counter label={i.label} value={v as number | null} tip={i.tip} tooltip={tt} /> },
  { key: 'detections', label: 'DETS', core: true, tip: 'Cumulative pigeons detected this flight.',
    get: (t) => t.detections ?? null,
    render: (v, i, tt) => <Counter label={i.label} value={v as number | null} tip={i.tip} tooltip={tt} /> },
  { key: 'frames', label: 'FRAMES', core: true, tip: 'Camera frames processed by the YOLO detector.',
    get: (_t, frames) => frames ?? null,
    render: (v, i, tt) => <Counter label={i.label} value={v as number | null} tip={i.tip} tooltip={tt} /> },
  { key: 'fps', label: 'FPS', tip: 'Detection throughput (frames per second), from the run summary.',
    get: (t) => t.fps ?? null,
    render: (v, i, tt) => <Gauge label={i.label} unit="" value={v as number | null} max={30} decimals={1} color="olive" tip={i.tip} tooltip={tt} /> },
  { key: 'battery', label: 'BAT', core: true, tip: 'Battery charge remaining (percent); red under 30%.',
    get: (t) => t.battery ?? null,
    render: (v, i, tt) => <Gauge label={i.label} unit="%" value={v as number | null} max={100} decimals={0}
                            color={typeof v === 'number' && v < 30 ? 'red' : 'olive'} tip={i.tip} tooltip={tt} /> },
];

/**
 * Live telemetry strip. Gauges show ONLY while a script is actively running
 * (`flightStatus.running`); otherwise the rail shows a single live "AWAITING
 * TELEMETRY" placeholder. (`flight_id` is NOT used to gate this — the backend
 * keeps it set after a flight ends, which previously left the core gauges
 * showing with no script running.) While running, a fixed core set
 * (PHASE/ALT/HDG/DIST/DETS/FRAMES/BAT) shows reading "--" until data arrives,
 * plus any script-specific gauge that becomes "sticky" the first time its value
 * appears, so nothing pops in/out mid-flight. Hover any gauge for an instant
 * explanation.
 */
export default function TelemetryRail({ simStatus, flightStatus }: Props) {
  const connected = !!simStatus?.connected;
  const tel: Telemetry = flightStatus?.telemetry ?? {};
  const flightId = flightStatus?.flight_id ?? null;
  const running = !!flightStatus?.running;
  const frames = running ? flightStatus?.frames_processed : undefined;

  // Track which non-core readouts have produced data during the current run;
  // once seen they stay pinned. The set is cleared both when the flight id
  // changes (new run) and when the flight stops running (sticky wears off).
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const lastFlightId = useRef<string | null>(null);

  useEffect(() => {
    if (flightId !== lastFlightId.current) {
      lastFlightId.current = flightId;
      setPinned(new Set());
    }
  }, [flightId]);

  // Sticky wears off when detection/flight is no longer running.
  useEffect(() => {
    if (!running) setPinned((prev) => (prev.size ? new Set() : prev));
  }, [running]);

  useEffect(() => {
    if (!running) return;
    setPinned((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const item of RAIL_SPEC) {
        if (item.core || next.has(item.key)) continue;
        const v = item.get(tel, frames);
        if (v !== undefined && v !== null && v !== '') {
          next.add(item.key);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [tel, frames, running]);

  // Shared instant tooltip (escapes the rail's overflow-x clipping by being
  // fixed-positioned at the document level).
  const tooltip = useTooltip();

  // Show telemetry ONLY while a script is actively running. Note `flight_id`
  // persists after a flight ends (the backend keeps it until the next run), so
  // it can't gate this — `running` is the real "a script is feeding us" signal.
  if (!connected || !running) {
    return (
      <div className="telemetry-rail">
        <AwaitingReadout tooltip={tooltip} />
        {tooltip.node}
      </div>
    );
  }

  // A script is running: render core gauges + any sticky pinned add-ons, each
  // showing its current value or "--" if it hasn't arrived (or has dropped).
  const items = RAIL_SPEC
    .filter((item) => item.core || pinned.has(item.key))
    .map((item) => {
      const raw = item.get(tel, frames);
      const value = raw === undefined || raw === '' ? null : raw;
      return <React.Fragment key={item.key}>{item.render(value, item, tooltip)}</React.Fragment>;
    });

  return (
    <div className="telemetry-rail">
      {items}
      {tooltip.node}
    </div>
  );
}

/** Format a signed number with a leading +/- for the velocity readout. */
function signed(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

function Gauge({
  label, unit, value, max, decimals, color, tip, tooltip,
}: {
  label: string;
  unit: string;
  value: number | null;
  max: number;
  decimals: number;
  color: Color;
  tip: string;
  tooltip: Tooltip;
}) {
  const nil = value === null;
  const pct = nil ? 0 : Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={`tel-gauge tel-${color} ${nil ? 'nil' : ''}`} {...tooltip.bind(tip)}>
      <div className="tel-head">
        <span className="tel-label">{label}</span>
        <span className="tel-value">
          {nil ? '--' : value.toFixed(decimals)}
          <span className="tel-unit">{unit}</span>
        </span>
      </div>
      <div className="tel-bar">
        <div className="tel-bar-fill" style={{ width: `${pct}%` }} />
        <div className="tel-bar-ticks" aria-hidden="true">
          {Array.from({ length: 10 }).map((_, i) => (
            <span key={i} className="tel-bar-tick" />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Heading is unbounded (-180..180), display as degrees with a wraparound bar. */
function HeadingGauge({ value, tip, tooltip }: { value: number | null; tip: string; tooltip: Tooltip }) {
  const nil = value === null;
  // Normalize to 0..360 for the bar fill so "north" is 0% and "back to north" is 100%.
  const normalized = nil ? 0 : ((value + 360) % 360);
  const pct = (normalized / 360) * 100;
  const display = nil ? '--' : Math.round(normalized).toString();
  return (
    <div className={`tel-gauge tel-teal ${nil ? 'nil' : ''}`} {...tooltip.bind(tip)}>
      <div className="tel-head">
        <span className="tel-label">HDG</span>
        <span className="tel-value">
          {display}
          <span className="tel-unit">°</span>
        </span>
      </div>
      <div className="tel-bar">
        <div className="tel-bar-fill" style={{ width: `${pct}%` }} />
        <div className="tel-bar-ticks" aria-hidden="true">
          {Array.from({ length: 10 }).map((_, i) => (
            <span key={i} className="tel-bar-tick" />
          ))}
        </div>
      </div>
    </div>
  );
}

function Counter({ label, value, tip, tooltip }: { label: string; value: number | null; tip: string; tooltip: Tooltip }) {
  const nil = value === null;
  return (
    <div className={`tel-gauge tel-olive ${nil ? 'nil' : ''}`} {...tooltip.bind(tip)}>
      <div className="tel-head">
        <span className="tel-label">{label}</span>
        <span className="tel-value">{nil ? '--' : value.toString()}</span>
      </div>
      <div className="tel-bar">
        <div className="tel-bar-fill" style={{ width: !nil && value > 0 ? '100%' : '0%' }} />
      </div>
    </div>
  );
}

/** Text readout (no numeric bar) for non-numeric state like PHASE. */
function Readout({
  label, value, color, tip, tooltip,
}: {
  label: string;
  value: string | null;
  color: Color;
  tip: string;
  tooltip: Tooltip;
}) {
  const nil = value === null;
  return (
    <div className={`tel-gauge tel-${color} ${nil ? 'nil' : ''}`} {...tooltip.bind(tip)}>
      <div className="tel-head">
        <span className="tel-label">{label}</span>
        <span className="tel-value tel-value-text">{nil ? '--' : value}</span>
      </div>
      <div className="tel-bar">
        <div className="tel-bar-fill" style={{ width: nil ? '0%' : '100%' }} />
      </div>
    </div>
  );
}

/**
 * Idle placeholder shown when the sim is connected but no flight is feeding
 * telemetry yet. A teal bar sweeps left-to-right on a loop so the rail reads
 * as a live, armed link awaiting data — not a dead/greyed-out cell.
 */
function AwaitingReadout({ tooltip }: { tooltip: Tooltip }) {
  return (
    <div className="tel-gauge tel-teal tel-awaiting"
         {...tooltip.bind('Connected and armed — waiting for a flight to start streaming telemetry.')}>
      <div className="tel-head">
        <span className="tel-label">TELEMETRY</span>
        <span className="tel-value tel-value-text">
          <span className="tel-await-dot" aria-hidden="true" />
          AWAITING
        </span>
      </div>
      <div className="tel-bar">
        <div className="tel-bar-fill tel-await-fill" />
      </div>
    </div>
  );
}
