import React, { useEffect, useState } from 'react';
import { FlightStatus, SimStatus } from '../types/flight';

interface Props {
  simStatus: SimStatus | null;
  flightStatus: FlightStatus | null;
}

/**
 * Top HUD banner.
 *   Left   — callsign + tagline
 *   Center — system-state pill (standby / launching / nominal / active) + world tag
 *   Right  — local-time clock + four live indicator lights
 *
 * The four lights are color-coded by current value (not just on/off):
 *   grey  — not running / value is 0 / no signal
 *   red   — below 25%
 *   green — at or above 25%
 *
 * Mapping (each light shows a different live reading):
 *   BAT  — battery percent
 *   ALT  — altitude as % of 2.5m target altitude
 *   RTF  — Gazebo real-time factor (1.0 = 100%)
 *   DET  — flight active (binary; grey when not flying, green when flying)
 */
export default function HudHeader({ simStatus, flightStatus }: Props) {
  const [clock, setClock] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const pad = (n: number) => String(n).padStart(2, '0');
  const localTime = `${pad(clock.getHours())}:${pad(clock.getMinutes())}:${pad(clock.getSeconds())}`;
  const localDate = `${clock.getFullYear()}-${pad(clock.getMonth() + 1)}-${pad(clock.getDate())}`;

  const connected = !!simStatus?.connected;
  const launching = !!simStatus?.launching;
  const flying = !!flightStatus?.isFlying;
  const world = simStatus?.world;
  const tel = flightStatus?.telemetry ?? {};

  let systemState: 'standby' | 'launching' | 'nominal' | 'active' = 'standby';
  if (flying) systemState = 'active';
  else if (connected) systemState = 'nominal';
  else if (launching) systemState = 'launching';

  // Percentages 0..100 for color thresholding. null = grey.
  const batPct = connected && tel.battery !== undefined ? tel.battery : null;
  const altPct = connected && tel.altitude !== undefined
    ? Math.max(0, (tel.altitude / 2.5) * 100)
    : null;
  const rtfPct = connected && simStatus?.rtf !== undefined && simStatus?.rtf !== null
    ? simStatus.rtf * 100
    : null;
  const detPct = flying ? 100 : null;

  return (
    <header className="hud-header">
      <div className="hud-header-left">
        <div className="hud-callsign">
          <span className="hud-callsign-bracket">[</span>
          SCARECROW DRONE
          <span className="hud-callsign-bracket">]</span>
        </div>
        <div className="hud-subline">PIGEON DETECTION</div>
      </div>

      <div className="hud-header-center">
        <div className={`hud-state hud-state-${systemState}`}>
          <span className="hud-state-dot" />
          <span className="hud-state-label">
            {systemState === 'active' && 'MISSION ACTIVE'}
            {systemState === 'nominal' && 'SYS NOMINAL'}
            {systemState === 'launching' && 'BOOT SEQUENCE'}
            {systemState === 'standby' && 'STANDBY'}
          </span>
        </div>
        {world && (
          <div className="hud-world-tag">WORLD: {world.toUpperCase()}</div>
        )}
      </div>

      <div className="hud-header-right">
        <div className="hud-clock">
          <span className="hud-clock-time">{localTime}</span>
          <span className="hud-clock-date">{localDate}</span>
        </div>
        <div className="hud-lights">
          <Light label="BAT" pct={batPct} />
          <Light label="ALT" pct={altPct} />
          <Light label="RTF" pct={rtfPct} />
          <Light label="DET" pct={detPct} pulsing={flying} />
        </div>
      </div>
    </header>
  );
}

/**
 * One indicator light. Color is derived from `pct`:
 *   null or 0 → grey (off)
 *   < 25      → red
 *   >= 25     → green
 */
function Light({
  label, pct, pulsing,
}: { label: string; pct: number | null; pulsing?: boolean }) {
  let tone: 'off' | 'red' | 'green' = 'off';
  if (pct !== null && pct > 0) {
    tone = pct < 25 ? 'red' : 'green';
  }
  return (
    <div className={`hud-light hud-light-${tone} ${pulsing ? 'pulsing' : ''}`}>
      <span className="hud-light-bulb" />
      <span className="hud-light-label">{label}</span>
    </div>
  );
}
