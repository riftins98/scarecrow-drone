import React, { useRef } from 'react';
import { SpawnMap, SpawnPoint } from '../types/flight';
import {
  PAD,
  viewBox, worldToSvg, svgToWorld, rectSvg, inObstacle, obstaclePolygon, airplanePath,
} from './garageMap';

interface Props {
  /** SDF-derived world map: full floor, valid interior, and no-spawn obstacles. */
  map: SpawnMap;
  /** Currently selected spawn (meters), or null for none yet. */
  value: SpawnPoint | null;
  /** Called with a valid (x, y) when the user clicks inside the allowed zone. */
  onChange: (p: SpawnPoint) => void;
  /** Disable interaction (e.g. while connecting / flying). */
  disabled?: boolean;
}

/**
 * Top-down world map for picking the drone's spawn point. The valid interior
 * (>=3m from every wall) is drawn as a clear olive zone; the wall margin is
 * shaded red and clicks there are rejected so you can only land the marker on
 * a legal spot. X,Y only; the drone launches with yaw 0.
 */
export default function SpawnPicker({
  map, value, onChange, disabled,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const vb = viewBox(map);
  const bounds = map.bounds;
  const obstacles = map.obstacles ?? [];
  const obstacleMargin = map.obstacleMargin ?? 0;

  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (disabled) return;
    const svg = svgRef.current;
    if (!svg) return;
    // Map the click from screen px to SVG user units via the viewBox.
    const rect = svg.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) / rect.width) * vb.width;
    const sy = ((e.clientY - rect.top) / rect.height) * vb.height;
    const world = svgToWorld(map, sx, sy);
    // Round to 0.1m, then validate the rounded point (so what we accept is
    // exactly what we send / what the backend re-checks).
    const x = Math.round(world.x * 10) / 10;
    const y = Math.round(world.y * 10) / 10;
    // Hard rule 1: inside the valid (wall-margin) rectangle.
    if (x < bounds.xMin || x > bounds.xMax || y < bounds.yMin || y > bounds.yMax) {
      return; // wall margin — rejected
    }
    // Hard rule 2: clear of every static obstacle.
    if (obstacles.some((o) => inObstacle(x, y, o, obstacleMargin))) {
      return; // on/too close to an obstacle — rejected
    }
    onChange({ x, y });
  };

  const wall = rectSvg(map, map.wallBounds);
  const valid = rectSvg(map, bounds);
  const marker = value ? worldToSvg(map, value.x, value.y) : null;

  return (
    <div className={`spawn-picker ${disabled ? 'spawn-picker-disabled' : ''}`}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${vb.width} ${vb.height}`}
        className="spawn-picker-svg"
        onClick={handleClick}
        role="img"
        aria-label="Drone spawn location picker"
      >
        {/* Wall-margin background (off-limits, red tint) fills the whole floor. */}
        <rect
          x={wall.x} y={wall.y}
          width={wall.width} height={wall.height}
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
          x={wall.x} y={wall.y}
          width={wall.width} height={wall.height}
          fill="url(#sp-hatch)"
        />

        {/* Valid interior zone (clear, olive outline). */}
        <rect
          x={valid.x} y={valid.y}
          width={valid.width} height={valid.height}
          fill="rgba(139,154,91,0.10)" stroke="#8b9a5b" strokeWidth="1"
          strokeDasharray="3 2"
        />

        {/* Obstacles: the full footprint+margin rectangle is the real no-spawn
            zone. Aircraft get a silhouette on top; other props stay as boxes. */}
        {obstacles.map((o, i) => (
          <g key={i}>
            <polygon
              points={obstaclePolygon(map, o, obstacleMargin)}
              fill="rgba(160,90,90,0.22)"
              stroke="#c97a7a"
              strokeWidth="1"
            />
            <polygon
              points={obstaclePolygon(map, o, obstacleMargin)}
              fill="url(#sp-hatch)"
            />
            {o.kind === 'aircraft' ? (
              <path
                d={airplanePath(map, o)}
                fill="rgba(90,40,40,0.65)"
                stroke="#e0a0a0"
                strokeWidth="0.9"
                strokeLinejoin="round"
              />
            ) : (
              <polygon
                points={obstaclePolygon(map, o)}
                fill="rgba(90,40,40,0.55)"
                stroke="#e0a0a0"
                strokeWidth="0.9"
              />
            )}
          </g>
        ))}

        {/* North indicator. In this Gazebo-matched view, +x points upward. */}
        <text x={vb.width / 2} y={PAD - 1} textAnchor="middle"
          fill="#7a9a9a" fontSize="7" fontFamily="monospace">N ↑</text>

        {/* Selected spawn marker: olive arrow pointing yaw 0 (+x). */}
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
