import React, { useRef } from 'react';
import { SpawnBounds, SpawnObstacle, SpawnPoint } from '../types/flight';
import {
  ROOM_X, ROOM_Y, PAD, VIEW_W, VIEW_H,
  worldToSvg, svgToWorld, clamp, inObstacle, airplanePath,
} from './garageMap';

interface Props {
  /** Valid interior rectangle (meters). */
  bounds: SpawnBounds;
  /** Parked-aircraft footprints to block (rotated rectangles). */
  obstacles?: SpawnObstacle[];
  /** Clearance (meters) required outside each obstacle. */
  obstacleMargin?: number;
  /** Currently selected spawn (meters), or null for none yet. */
  value: SpawnPoint | null;
  /** Called with a valid (x, y) when the user clicks inside the allowed zone. */
  onChange: (p: SpawnPoint) => void;
  /** Disable interaction (e.g. while connecting / flying). */
  disabled?: boolean;
}

/**
 * Top-down room map for picking the drone's spawn point. The valid interior
 * (>=3m from every wall) is drawn as a clear olive zone; the wall margin is
 * shaded red and clicks there are snapped back / rejected so you can only land
 * the marker on a legal spot. X,Y only — the drone always faces north.
 */
export default function SpawnPicker({
  bounds, obstacles = [], obstacleMargin = 0, value, onChange, disabled,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (disabled) return;
    const svg = svgRef.current;
    if (!svg) return;
    // Map the click from screen px to SVG user units via the viewBox.
    const rect = svg.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) / rect.width) * VIEW_W;
    const sy = ((e.clientY - rect.top) / rect.height) * VIEW_H;
    const world = svgToWorld(sx, sy);
    // Round to 0.1m, then validate the rounded point (so what we accept is
    // exactly what we send / what the backend re-checks).
    const x = Math.round(clamp(world.x, bounds.xMin, bounds.xMax) * 10) / 10;
    const y = Math.round(clamp(world.y, bounds.yMin, bounds.yMax) * 10) / 10;
    // Hard rule 1: inside the valid (wall-margin) rectangle.
    if (x < bounds.xMin || x > bounds.xMax || y < bounds.yMin || y > bounds.yMax) {
      return; // wall margin — rejected
    }
    // Hard rule 2: clear of every parked aircraft.
    if (obstacles.some((o) => inObstacle(x, y, o, obstacleMargin))) {
      return; // on/too close to an aircraft — rejected
    }
    onChange({ x, y });
  };

  // Clearance halo: the rotated footprint expanded by the margin, drawn faintly
  // so the actual no-spawn zone (which the click check uses) is visible behind
  // the airplane silhouette.
  const clearancePolygon = (o: SpawnObstacle): string => {
    const hw = o.halfW + obstacleMargin;
    const hl = o.halfL + obstacleMargin;
    const c = Math.cos(o.yaw);
    const s = Math.sin(o.yaw);
    return ([[-hw, -hl], [hw, -hl], [hw, hl], [-hw, hl]] as Array<[number, number]>)
      .map(([lx, ly]) => {
        const p = worldToSvg(o.cx + lx * c - ly * s, o.cy + lx * s + ly * c);
        return `${p.sx},${p.sy}`;
      })
      .join(' ');
  };

  // Room outer rect (walls) and the valid inner rect, in SVG units.
  const wallTL = worldToSvg(ROOM_X, -ROOM_Y);   // top-left = (+x, -y)
  const wallBR = worldToSvg(-ROOM_X, ROOM_Y);   // bottom-right = (-x, +y)
  const validTL = worldToSvg(bounds.xMax, bounds.yMin);
  const validBR = worldToSvg(bounds.xMin, bounds.yMax);

  const marker = value ? worldToSvg(value.x, value.y) : null;

  return (
    <div className={`spawn-picker ${disabled ? 'spawn-picker-disabled' : ''}`}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="spawn-picker-svg"
        onClick={handleClick}
        role="img"
        aria-label="Drone spawn location picker"
      >
        {/* Wall-margin background (off-limits, red tint) fills the whole room. */}
        <rect
          x={wallTL.sx} y={wallTL.sy}
          width={wallBR.sx - wallTL.sx} height={wallBR.sy - wallTL.sy}
          fill="rgba(160,90,90,0.12)" stroke="#8b9a5b" strokeWidth="1.5"
        />
        {/* Hatch the margin so it clearly reads as no-go. */}
        <defs>
          <pattern id="sp-hatch" width="6" height="6" patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="rgba(160,90,90,0.35)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect
          x={wallTL.sx} y={wallTL.sy}
          width={wallBR.sx - wallTL.sx} height={wallBR.sy - wallTL.sy}
          fill="url(#sp-hatch)"
        />

        {/* Valid interior zone (clear, olive outline). */}
        <rect
          x={validTL.sx} y={validTL.sy}
          width={validBR.sx - validTL.sx} height={validBR.sy - validTL.sy}
          fill="rgba(139,154,91,0.10)" stroke="#8b9a5b" strokeWidth="1"
          strokeDasharray="3 2"
        />

        {/* Parked aircraft: faint clearance halo (the actual no-spawn zone)
            with an airplane silhouette on top so it reads as a plane. */}
        {obstacles.map((o, i) => (
          <g key={i}>
            <polygon
              points={clearancePolygon(o)}
              fill="rgba(160,90,90,0.10)"
              stroke="rgba(160,90,90,0.35)"
              strokeWidth="0.75"
              strokeDasharray="2 2"
            />
            <path
              d={airplanePath(o)}
              fill="rgba(160,90,90,0.5)"
              stroke="#c97a7a"
              strokeWidth="0.8"
              strokeLinejoin="round"
            />
          </g>
        ))}

        {/* North indicator (top = +x, the drone's facing). */}
        <text x={VIEW_W / 2} y={PAD - 1} textAnchor="middle"
          fill="#7a9a9a" fontSize="7" fontFamily="monospace">N ↑</text>

        {/* Selected spawn marker: olive arrow pointing north (drone heading). */}
        {marker && (
          <g transform={`translate(${marker.sx}, ${marker.sy})`}>
            <circle r="5" fill="rgba(139,154,91,0.25)" stroke="#b6c57a" strokeWidth="1" />
            <path d="M 0 -6 L 3 3 L 0 1 L -3 3 Z" fill="#b6c57a" />
          </g>
        )}
      </svg>
      <div className="spawn-picker-readout">
        {value
          ? `X ${value.x.toFixed(1)}  Y ${value.y.toFixed(1)} (m)`
          : 'Click inside the zone to set a spawn'}
      </div>
    </div>
  );
}
