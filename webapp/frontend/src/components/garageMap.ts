// Shared geometry + drawing helpers for the top-down garage map, used by both
// SpawnPicker (interactive spawn placement) and Minimap (live world view).
// One source of truth for the room scale, world<->SVG mapping, and the aircraft
// silhouette so the two maps stay visually consistent.
import { SpawnObstacle } from '../types/flight';

// Garage room in meters: 24m (x, north/south) by 15m (y, east/west), centered
// on the origin; inner wall faces at x=+-12 / y=+-7.5. Rendered top-down with
// +x pointing UP (north at top) to match the drone's default heading.
export const ROOM_X = 12;
export const ROOM_Y = 7.5;
export const PAD = 10;     // SVG padding around the room (SVG units)
export const SCALE = 14;   // SVG units per meter

export const VIEW_W = ROOM_Y * 2 * SCALE + PAD * 2;
export const VIEW_H = ROOM_X * 2 * SCALE + PAD * 2;

export interface SvgPoint { sx: number; sy: number; }

/** World (x,y) meters -> SVG (sx, sy). +x up (north top), +y right. */
export function worldToSvg(x: number, y: number): SvgPoint {
  return {
    sx: PAD + (y + ROOM_Y) * SCALE,
    sy: PAD + (ROOM_X - x) * SCALE, // invert x so +x is at the top
  };
}

/** SVG (sx, sy) -> world (x,y) meters (inverse of worldToSvg). */
export function svgToWorld(sx: number, sy: number): { x: number; y: number } {
  return {
    y: (sx - PAD) / SCALE - ROOM_Y,
    x: ROOM_X - (sy - PAD) / SCALE,
  };
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/** Is (x, y) inside an aircraft's rotated footprint, expanded by margin?
 *  Mirrors the backend's _in_obstacle so the UI blocks exactly what the API
 *  would reject. */
export function inObstacle(x: number, y: number, o: SpawnObstacle, margin: number): boolean {
  const dx = x - o.cx;
  const dy = y - o.cy;
  const c = Math.cos(-o.yaw);
  const s = Math.sin(-o.yaw);
  const lx = dx * c - dy * s;
  const ly = dx * s + dy * c;
  return Math.abs(lx) <= o.halfW + margin && Math.abs(ly) <= o.halfL + margin;
}

/**
 * Build an SVG path (in SVG user units) for a top-down airplane silhouette
 * filling an aircraft's footprint. Drawn in the craft's local frame (local +y =
 * fuselage/nose direction, local +x = wings) then transformed world->SVG.
 *
 * `inset` (meters) shrinks the silhouette slightly inside the true footprint so
 * the outline reads cleanly. The shape: pointed nose, swept delta wings, a
 * tailplane, all proportioned from the craft's half-extents.
 */
export function airplanePath(o: SpawnObstacle, inset = 0.2): string {
  const hw = Math.max(0.2, o.halfW - inset); // wing half-span
  const hl = Math.max(0.2, o.halfL - inset); // fuselage half-length (nose +y)

  // Silhouette vertices in local (lx along wings, ly along fuselage; +ly = nose).
  // Proportions are fractions of the half-extents so it scales with the model.
  const bodyW = hw * 0.16;            // fuselage half-width
  const wingLy = -hl * 0.05;          // wing root just aft of center
  const wingTipLy = -hl * 0.45;       // wing sweep-back at the tips
  const tailLy = -hl * 0.78;          // tailplane position
  const tailW = hw * 0.42;            // tailplane half-span

  const pts: Array<[number, number]> = [
    [0, hl],                    // nose
    [bodyW, hl * 0.45],         // right forward fuselage
    [bodyW, wingLy],            // right wing root front
    [hw, wingTipLy],            // right wing tip
    [bodyW * 1.2, wingTipLy - hl * 0.04], // right wing trailing root
    [bodyW, tailLy + hl * 0.1], // right rear fuselage
    [tailW, tailLy],            // right tail tip
    [bodyW, -hl],               // right tail trailing
    [-bodyW, -hl],              // left tail trailing
    [-tailW, tailLy],           // left tail tip
    [-bodyW, tailLy + hl * 0.1],
    [-bodyW * 1.2, wingTipLy - hl * 0.04],
    [-hw, wingTipLy],           // left wing tip
    [-bodyW, wingLy],           // left wing root front
    [-bodyW, hl * 0.45],        // left forward fuselage
  ];

  const c = Math.cos(o.yaw);
  const s = Math.sin(o.yaw);
  const d = pts
    .map(([lx, ly], i) => {
      const wx = o.cx + lx * c - ly * s;
      const wy = o.cy + lx * s + ly * c;
      const p = worldToSvg(wx, wy);
      return `${i === 0 ? 'M' : 'L'} ${p.sx.toFixed(1)} ${p.sy.toFixed(1)}`;
    })
    .join(' ');
  return `${d} Z`;
}
