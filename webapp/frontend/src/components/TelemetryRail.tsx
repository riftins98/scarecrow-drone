import React from 'react';
import { FlightStatus, SimStatus } from '../types/flight';

interface Props {
  /** Sim status; we read rtf + connected/headless flags from it. */
  simStatus: SimStatus | null;
  /** Flight status; we read the latest TELEMETRY: payload from .telemetry. */
  flightStatus: FlightStatus | null;
}

/**
 * Live telemetry strip. Five readouts:
 *   ALT — meters AGL, from the flight script's TELEMETRY: stream
 *   BAT — battery percent, ditto (PX4 SITL barely drains so it usually stays near 100)
 *   HDG — yaw degrees, ditto
 *   DETS — cumulative pigeon detections, ditto
 *   RTF — Gazebo real_time_factor (sim wall-clock speed), from /api/sim/status
 *
 * Anything we don't have data for yet shows "--" rather than a mocked value.
 */
export default function TelemetryRail({ simStatus, flightStatus }: Props) {
  const connected = !!simStatus?.connected;
  const tel = flightStatus?.telemetry ?? {};
  const altitude  = connected && tel.altitude  !== undefined ? tel.altitude  : null;
  const battery   = connected && tel.battery   !== undefined ? tel.battery   : null;
  const heading   = connected && tel.heading   !== undefined ? tel.heading   : null;
  const detections = connected && tel.detections !== undefined ? tel.detections : null;
  const rtf       = connected && simStatus?.rtf !== undefined && simStatus?.rtf !== null
    ? simStatus.rtf
    : null;

  return (
    <div className="telemetry-rail">
      <Gauge
        label="ALT"
        unit="M"
        value={altitude}
        max={5}
        decimals={2}
        color="olive"
      />
      <Gauge
        label="BAT"
        unit="%"
        value={battery}
        max={100}
        decimals={0}
        color={battery !== null && battery < 30 ? 'red' : 'olive'}
      />
      <HeadingGauge value={heading} />
      <Counter label="DETS" value={detections} />
      <Gauge
        label="RTF"
        unit="x"
        value={rtf}
        max={1}
        decimals={2}
        color={rtf !== null && rtf < 0.5 ? 'red' : 'olive'}
      />
    </div>
  );
}

function Gauge({
  label, unit, value, max, decimals, color,
}: {
  label: string;
  unit: string;
  value: number | null;
  max: number;
  decimals: number;
  color: 'olive' | 'teal' | 'red';
}) {
  const pct = value !== null ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className={`tel-gauge tel-${color} ${value === null ? 'nil' : ''}`}>
      <div className="tel-head">
        <span className="tel-label">{label}</span>
        <span className="tel-value">
          {value !== null ? value.toFixed(decimals) : '--'}
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
function HeadingGauge({ value }: { value: number | null }) {
  // Normalize to 0..360 for the bar fill so "north" is 0% and "back to north" is 100%.
  const normalized = value !== null ? ((value + 360) % 360) : null;
  const pct = normalized !== null ? (normalized / 360) * 100 : 0;
  const display = value !== null ? Math.round(((value + 360) % 360)).toString() : '--';
  return (
    <div className={`tel-gauge tel-teal ${value === null ? 'nil' : ''}`}>
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

function Counter({ label, value }: { label: string; value: number | null }) {
  return (
    <div className={`tel-gauge tel-olive ${value === null ? 'nil' : ''}`}>
      <div className="tel-head">
        <span className="tel-label">{label}</span>
        <span className="tel-value">
          {value !== null ? value.toString() : '--'}
        </span>
      </div>
      <div className="tel-bar">
        <div className="tel-bar-fill" style={{ width: value && value > 0 ? '100%' : '0%' }} />
      </div>
    </div>
  );
}
