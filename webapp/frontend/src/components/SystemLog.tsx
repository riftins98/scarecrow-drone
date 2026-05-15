import React, { useEffect, useRef, useState } from 'react';

interface Props {
  connected: boolean;
  flying: boolean;
}

interface LogEntry {
  id: number;
  ts: string;
  level: 'INFO' | 'OK' | 'WARN' | 'EKF' | 'DET' | 'NAV';
  msg: string;
}

const IDLE_LINES = [
  { level: 'INFO' as const, msg: 'awaiting operator input' },
  { level: 'INFO' as const, msg: 'mavsdk_server: standby' },
  { level: 'INFO' as const, msg: 'tcp/14540 listening' },
  { level: 'INFO' as const, msg: 'px4 not connected' },
];

const CONNECTED_LINES = [
  { level: 'EKF' as const, msg: 'ekf2: nominal // attitude valid' },
  { level: 'NAV' as const, msg: 'optical_flow: locked // quality 0.87' },
  { level: 'INFO' as const, msg: 'lidar: 360° sweep // 12.4Hz' },
  { level: 'OK' as const,   msg: 'health check passed' },
  { level: 'NAV' as const, msg: 'wall_follow: ready' },
  { level: 'INFO' as const, msg: 'battery telemetry: bus A nominal' },
  { level: 'EKF' as const, msg: 'imu drift compensation active' },
  { level: 'WARN' as const, msg: 'gps signal: denied (expected)' },
];

const FLYING_LINES = [
  { level: 'NAV' as const, msg: 'wall_follow engaged // stand-off 0.8m' },
  { level: 'DET' as const, msg: 'yolo inference 28fps // conf 0.62' },
  { level: 'NAV' as const, msg: 'heading correction -2.3°' },
  { level: 'EKF' as const, msg: 'altitude hold @ 2.4m // err 0.04m' },
  { level: 'DET' as const, msg: 'frame buffer flushed // 32 frames' },
  { level: 'NAV' as const, msg: 'lidar: obstacle bearing 045°' },
  { level: 'DET' as const, msg: 'pigeon class // bbox 0.18 area' },
  { level: 'INFO' as const, msg: 'recording chunk written // 4MB' },
  { level: 'NAV' as const, msg: 'optical flow vel: 0.21 m/s' },
];

type LinePool = ReadonlyArray<{ level: LogEntry['level']; msg: string }>;

function pickLine(pool: LinePool): { level: LogEntry['level']; msg: string } {
  return pool[Math.floor(Math.random() * pool.length)];
}

function nowStamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export default function SystemLog({ connected, flying }: Props) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const idCounter = useRef(0);

  useEffect(() => {
    const intervalMs = flying ? 700 : connected ? 1400 : 2400;
    const pool = flying
      ? [...CONNECTED_LINES, ...FLYING_LINES, ...FLYING_LINES]
      : connected
      ? CONNECTED_LINES
      : IDLE_LINES;

    const tick = () => {
      const line = pickLine(pool);
      setEntries(prev => {
        const next: LogEntry[] = [
          ...prev,
          { id: ++idCounter.current, ts: nowStamp(), level: line.level, msg: line.msg },
        ];
        // Keep last 40
        return next.slice(-40);
      });
    };

    // Seed one immediately
    tick();
    const i = setInterval(tick, intervalMs);
    return () => clearInterval(i);
  }, [connected, flying]);

  return (
    <div className="syslog">
      <div className="syslog-header">
        <span className="syslog-title">SYS // LIVE LOG</span>
        <span className="syslog-rate">{flying ? '700ms' : connected ? '1.4s' : '2.4s'}</span>
        <span className="syslog-light" />
      </div>
      <div className="syslog-body">
        {entries.length === 0 && (
          <div className="syslog-line">
            <span className="syslog-ts">--:--:--</span>
            <span className="syslog-level">INFO</span>
            <span className="syslog-msg">booting…</span>
          </div>
        )}
        {entries.map(e => (
          <div key={e.id} className={`syslog-line syslog-level-${e.level.toLowerCase()}`}>
            <span className="syslog-ts">{e.ts}</span>
            <span className="syslog-level">{e.level}</span>
            <span className="syslog-msg">{e.msg}</span>
          </div>
        ))}
        <div className="syslog-cursor">_</div>
      </div>
    </div>
  );
}
