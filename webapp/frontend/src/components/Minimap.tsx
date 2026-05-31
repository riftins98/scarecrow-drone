import React, { useEffect, useRef, useState } from 'react';
import { SimStatus, FlightStatus, SimOptions } from '../types/flight';
import {
  PAD,
  viewBox, worldToSvg, rectSvg, obstaclePolygon, airplanePath,
} from './garageMap';
import { spawnMapForWorld } from './spawnMapLookup';

interface Props {
  simStatus: SimStatus | null;
  flightStatus: FlightStatus | null;
  options: SimOptions | null;
  previewWorld?: string | null;
}

interface Pt { x: number; y: number; } // world meters

/**
 * Top-down map of the active world, drawn to scale from SDF-derived geometry.
 * The drone marker sits at its live world pose (queried from Gazebo via
 * simStatus.dronePose), falling back to the session spawn point when a live
 * pose isn't available. A short trail follows the drone while flying.
 */
export default function Minimap({ simStatus, flightStatus, options, previewWorld }: Props) {
  const connected = !!simStatus?.connected;
  const launching = !!simStatus?.launching;
  const flying = !!flightStatus?.isFlying;
  const activeWorld = connected || launching
    ? (simStatus?.world || previewWorld)
    : previewWorld;
  const mapWorld =
    activeWorld ??
    options?.spawnWorld ??
    options?.worlds.find((w) => w.spawn)?.name ??
    null;
  const map = spawnMapForWorld(options, mapWorld);
  const obstacles = map?.obstacles ?? [];

  // Live drone pose (meters + heading deg). Prefer the Gazebo-queried pose;
  // fall back to the session spawn (drone is sitting there pre-flight).
  const pose = simStatus?.dronePose ?? null;
  const spawn = simStatus?.spawn ?? null;
  const droneX = pose?.x ?? spawn?.x ?? 0;
  const droneY = pose?.y ?? spawn?.y ?? 0;
  const droneHdg = pose?.heading ?? 0;

  // Trail of recent world positions while flying.
  const [trail, setTrail] = useState<Pt[]>([]);
  const lastFlightId = useRef<string | null>(null);
  useEffect(() => {
    const fid = flightStatus?.flight_id ?? null;
    if (fid !== lastFlightId.current) {
      lastFlightId.current = fid;
      setTrail([]); // reset trail on a new flight
    }
    if (!flying) return;
    setTrail((prev) => {
      const last = prev[prev.length - 1];
      // Only append when the drone has actually moved a bit (>=0.1m).
      if (last && Math.hypot(last.x - droneX, last.y - droneY) < 0.1) return prev;
      const next = [...prev, { x: droneX, y: droneY }];
      return next.length > 200 ? next.slice(next.length - 200) : next;
    });
  }, [flying, droneX, droneY, flightStatus]);

  if (!map) {
    return (
      <div className={`minimap ${connected ? 'on' : 'off'}`}>
        <div className="minimap-header">
          <span className="minimap-title">Map : {mapWorld || 'World'}</span>
          <span className={`minimap-live ${connected ? 'live' : ''}`}>
            {flying ? 'TRACKING' : connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
        <div className="minimap-scope minimap-unavailable">
          <span className="minimap-coord">Map unavailable</span>
        </div>
        <div className="minimap-footer">
          <span className="minimap-coord">X: {droneX.toFixed(1)}  Y: {droneY.toFixed(1)}</span>
          <span className="minimap-coord">HDG: {Math.floor((droneHdg + 360) % 360)}°</span>
        </div>
      </div>
    );
  }

  const vb = viewBox(map);
  const wall = rectSvg(map, map.wallBounds);
  const drone = worldToSvg(map, droneX, droneY);

  // Pads sit under each obstacle center as a quick visual anchor.
  const pads = obstacles.map((o) => worldToSvg(map, o.cx, o.cy));

  return (
    <div className={`minimap ${connected ? 'on' : 'off'}`}>
      <div className="minimap-header">
        <span className="minimap-title">Map : {map.world}</span>
        <span className={`minimap-live ${connected ? 'live' : ''}`}>
          {flying ? 'TRACKING' : connected ? 'LIVE' : 'OFFLINE'}
        </span>
      </div>
      <div className="minimap-scope">
        <svg viewBox={`0 0 ${vb.width} ${vb.height}`} className="minimap-svg">
          <defs>
            <pattern id="mm-grid2" width={14} height={14} patternUnits="userSpaceOnUse">
              <path d="M 14 0 L 0 0 0 14" fill="none"
                stroke="rgba(139,154,91,0.12)" strokeWidth="0.5" />
            </pattern>
          </defs>

          {/* Floor + 1m grid (SCALE = 14 SVG units / meter). */}
          <rect x={wall.x} y={wall.y}
            width={wall.width} height={wall.height}
            fill="#0d1208" />
          <rect x={wall.x} y={wall.y}
            width={wall.width} height={wall.height}
            fill="url(#mm-grid2)" />

          {/* Room walls (to scale). */}
          <rect x={wall.x} y={wall.y}
            width={wall.width} height={wall.height}
            fill="none" stroke="#8b9a5b" strokeWidth="1.5" />

          {/* Landing pads under each aircraft. */}
          {pads.map((p, i) => (
            <circle key={i} cx={p.sx} cy={p.sy} r="10"
              fill="none" stroke="rgba(122,154,154,0.4)" strokeWidth="0.8"
              strokeDasharray="2 2" />
          ))}

          {/* Static obstacles (real footprints; aircraft get silhouettes). */}
          {obstacles.map((o, i) => (
            o.kind === 'aircraft' ? (
              <path key={i} d={airplanePath(map, o)}
                fill="rgba(122,154,154,0.16)" stroke="#7a9a9a" strokeWidth="0.8"
                strokeLinejoin="round" />
            ) : (
              <polygon key={i} points={obstaclePolygon(map, o)}
                fill="rgba(122,154,154,0.14)" stroke="#7a9a9a" strokeWidth="0.8" />
            )
          ))}

          {/* North indicator. In this Gazebo-matched view, +x points upward. */}
          <text x={vb.width / 2} y={PAD - 1} textAnchor="middle"
            fill="#7a9a9a" fontSize="7" fontFamily="monospace">N ↑</text>

          {/* Drone trail. */}
          {trail.length > 1 && (
            <polyline
              points={trail.map((p) => {
                const s = worldToSvg(map, p.x, p.y);
                return `${s.sx.toFixed(1)},${s.sy.toFixed(1)}`;
              }).join(' ')}
              fill="none" stroke="#7a9a9a" strokeWidth="1.2"
              strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
          )}

          {/* Drone marker at live pose (yaw 0 / +x points up in this view). */}
          {connected && (
            <g transform={`translate(${drone.sx.toFixed(2)} ${drone.sy.toFixed(2)}) rotate(${droneHdg.toFixed(1)})`}>
              <circle r="5" fill="rgba(139,154,91,0.18)" />
              <circle r="2.6" fill="#8b9a5b" />
              <path d="M 0 -5.5 L 1.6 -2 L -1.6 -2 Z" fill="#d4e090" />
            </g>
          )}
        </svg>
      </div>
      <div className="minimap-footer">
        <span className="minimap-coord">X: {droneX.toFixed(1)}  Y: {droneY.toFixed(1)}</span>
        <span className="minimap-coord">HDG: {Math.floor((droneHdg + 360) % 360)}°</span>
      </div>
    </div>
  );
}
