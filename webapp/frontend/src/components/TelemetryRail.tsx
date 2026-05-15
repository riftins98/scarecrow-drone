import React, { useEffect, useState } from 'react';

interface Props {
  connected: boolean;
  flying: boolean;
}

/**
 * Mock telemetry strip. ALT, SIG, and RTF read fixed values when connected
 * (no drift); BAT drains slowly so the rail still feels live.
 */
export default function TelemetryRail({ connected, flying }: Props) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!connected) return;
    const t = setInterval(() => setTick(x => x + 1), 800);
    return () => clearInterval(t);
  }, [connected]);

  const altitude = connected ? 0 : null;
  const battery = connected ? Math.max(0.2, 0.92 - tick * 0.0005) : null;
  const signal = connected ? 1 : null;
  const rtf = connected ? 1 : null;

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
        value={battery !== null ? battery * 100 : null}
        max={100}
        decimals={0}
        color={battery !== null && battery < 0.3 ? 'red' : 'olive'}
      />
      <Gauge
        label="SIG"
        unit="%"
        value={signal !== null ? signal * 100 : null}
        max={100}
        decimals={0}
        color="teal"
      />
      <Gauge
        label="RTF"
        unit="%"
        value={rtf !== null ? rtf * 100 : null}
        max={100}
        decimals={0}
        color="olive"
      />
      <GpsDeniedBadge active={connected} />
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

function GpsDeniedBadge({ active }: { active: boolean }) {
  return (
    <div className={`tel-badge ${active ? 'on' : 'off'}`}>
      <div className="tel-badge-corner tel-badge-tl" />
      <div className="tel-badge-corner tel-badge-tr" />
      <div className="tel-badge-corner tel-badge-bl" />
      <div className="tel-badge-corner tel-badge-br" />
      <div className="tel-badge-text">
        <div className="tel-badge-line1">GPS</div>
        <div className="tel-badge-line2">DENIED</div>
      </div>
    </div>
  );
}
