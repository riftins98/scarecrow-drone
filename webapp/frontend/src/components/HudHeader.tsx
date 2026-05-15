import React, { useEffect, useState } from 'react';

interface Props {
  connected: boolean;
  launching: boolean;
  flying: boolean;
  world?: string;
}

export default function HudHeader({ connected, launching, flying, world }: Props) {
  const [clock, setClock] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const pad = (n: number) => String(n).padStart(2, '0');
  const localTime = `${pad(clock.getHours())}:${pad(clock.getMinutes())}:${pad(clock.getSeconds())}`;
  const localDate = `${clock.getFullYear()}-${pad(clock.getMonth() + 1)}-${pad(clock.getDate())}`;

  let systemState: 'standby' | 'launching' | 'nominal' | 'active' = 'standby';
  if (flying) systemState = 'active';
  else if (connected) systemState = 'nominal';
  else if (launching) systemState = 'launching';

  return (
    <header className="hud-header">
      <div className="hud-header-left">
        <div className="hud-callsign">
          <span className="hud-callsign-bracket">[</span>
          SCARECROW
          <span className="hud-callsign-bracket">]</span>
        </div>
        <div className="hud-subline">UNIT 01 // GPS-DENIED OPS // PIGEON DETECTION</div>
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
          <Light label="PWR" on={true} color="olive" />
          <Light label="NET" on={connected || launching} color="olive" />
          <Light label="EKF" on={connected} color="teal" />
          <Light label="DET" on={flying} color="teal" pulsing={flying} />
        </div>
      </div>
    </header>
  );
}

function Light({
  label, on, color, pulsing,
}: { label: string; on: boolean; color: 'olive' | 'teal'; pulsing?: boolean }) {
  return (
    <div className={`hud-light hud-light-${color} ${on ? 'on' : 'off'} ${pulsing ? 'pulsing' : ''}`}>
      <span className="hud-light-bulb" />
      <span className="hud-light-label">{label}</span>
    </div>
  );
}
