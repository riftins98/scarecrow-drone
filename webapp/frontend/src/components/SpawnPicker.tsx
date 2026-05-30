import React, { useRef } from 'react';
import { SpawnBounds, SpawnObstacle, SpawnPoint } from '../types/flight';

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

/** Is (x, y) inside an aircraft's rotated footprint, expanded by margin?
 *  Mirrors the backend's _in_obstacle so the UI blocks exactly what the API
 *  would reject. */
function inObstacle(x: number, y: number, o: SpawnObstacle, margin: number): boolean {
  const dx = x - o.cx;
  const dy = y - o.cy;
  const c = Math.cos(-o.yaw);
  const s = Math.sin(-o.yaw);
  const lx = dx * c - dy * s;
  const ly = dx * s + dy * c;
  return Math.abs(lx) <= o.halfW + margin && Math.abs(ly) <= o.halfL + margin;
}

// Full room (garage) in meters: 24m (x) by 15m (y), centered on the origin,
// walls at x=+-12 / y=+-7.5. We render it top-down with +x pointing UP (north
// at the top), to match the drone's default "facing north" heading.
const ROOM_X = 12;   // half-extent along x (north/south), meters
const ROOM_Y = 7.5;  // half-extent along y (east/west), meters
const PAD = 10;      // SVG padding around the room, in SVG units
const SCALE = 14;    // SVG units per meter (room ~ 210 x 336 + padding... see below)

// SVG canvas size derived from the room + padding. World y maps to SVG x
// (horizontal), world x maps to SVG y (vertical, inverted so +x is up).
const VIEW_W = ROOM_Y * 2 * SCALE + PAD * 2;
const VIEW_H = ROOM_X * 2 * SCALE + PAD * 2;

/** World (x,y) meters -> SVG (sx, sy). +x up (north top), +y right. */
function worldToSvg(x: number, y: number): { sx: number; sy: number } {
  const sx = PAD + (y + ROOM_Y) * SCALE;
  const sy = PAD + (ROOM_X - x) * SCALE; // invert x so +x is at the top
  return { sx, sy };
}

/** SVG (sx, sy) -> world (x,y) meters (inverse of worldToSvg). */
function svgToWorld(sx: number, sy: number): SpawnPoint {
  const y = (sx - PAD) / SCALE - ROOM_Y;
  const x = ROOM_X - (sy - PAD) / SCALE;
  return { x, y };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
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

  // Build an SVG polygon for a rotated aircraft footprint (+margin) so we can
  // draw the no-spawn zone exactly where clicks are blocked.
  const obstaclePolygon = (o: SpawnObstacle): string => {
    const hw = o.halfW + obstacleMargin;
    const hl = o.halfL + obstacleMargin;
    const c = Math.cos(o.yaw);
    const s = Math.sin(o.yaw);
    // Local corners (lx, ly) -> world -> SVG.
    const corners: Array<[number, number]> = [
      [-hw, -hl], [hw, -hl], [hw, hl], [-hw, hl],
    ];
    return corners
      .map(([lx, ly]) => {
        const wx = o.cx + lx * c - ly * s;
        const wy = o.cy + lx * s + ly * c;
        const p = worldToSvg(wx, wy);
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

        {/* Parked-aircraft no-spawn footprints (rotated rectangles, red). */}
        {obstacles.map((o, i) => (
          <polygon
            key={i}
            points={obstaclePolygon(o)}
            fill="rgba(160,90,90,0.22)"
            stroke="#a05a5a"
            strokeWidth="1"
          />
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
