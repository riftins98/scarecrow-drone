// Shared geometry + drawing helpers for top-down world maps, used by both
// SpawnPicker (interactive spawn placement) and Minimap (live world view).
import { SpawnBounds, SpawnMap, SpawnObstacle } from '../types/flight';

export const PAD = 10;     // SVG padding around the world floor (SVG units)
export const SCALE = 14;   // SVG units per meter

export interface SvgPoint { sx: number; sy: number; }
export interface ViewBox { width: number; height: number; }

export function viewBox(map: SpawnMap): ViewBox {
  return {
    width: (map.wallBounds.yMax - map.wallBounds.yMin) * SCALE + PAD * 2,
    height: (map.wallBounds.xMax - map.wallBounds.xMin) * SCALE + PAD * 2,
  };
}

/** World (x,y) meters -> SVG (sx, sy).
 *  Matches the Gazebo GUI view used by the team: +x is up, +y is left. */
export function worldToSvg(map: SpawnMap, x: number, y: number): SvgPoint {
  return {
    sx: PAD + (map.wallBounds.yMax - y) * SCALE,
    sy: PAD + (map.wallBounds.xMax - x) * SCALE,
  };
}

/** SVG (sx, sy) -> world (x,y) meters (inverse of worldToSvg). */
export function svgToWorld(map: SpawnMap, sx: number, sy: number): { x: number; y: number } {
  return {
    y: map.wallBounds.yMax - (sx - PAD) / SCALE,
    x: map.wallBounds.xMax - (sy - PAD) / SCALE,
  };
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

export function rectSvg(map: SpawnMap, bounds: SpawnBounds) {
  const a = worldToSvg(map, bounds.xMax, bounds.yMin);
  const b = worldToSvg(map, bounds.xMin, bounds.yMax);
  return {
    x: Math.min(a.sx, b.sx),
    y: Math.min(a.sy, b.sy),
    width: Math.abs(b.sx - a.sx),
    height: Math.abs(b.sy - a.sy),
  };
}

/** Is (x, y) inside a static obstacle footprint, expanded by margin?
 *  Mirrors the backend obstacle check so the UI blocks what the API rejects. */
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
 * filling an aircraft's footprint. Drawn in the craft's local frame (local -y =
 * fuselage/nose direction, local +x = wings) then transformed world->SVG.
 *
 * `inset` (meters) shrinks the silhouette slightly inside the true footprint so
 * the outline reads cleanly. The shape: pointed nose, swept delta wings, a
 * tailplane, all proportioned from the craft's half-extents.
 */
export function obstaclePolygon(map: SpawnMap, o: SpawnObstacle, margin = 0): string {
  const hw = o.halfW + margin;
  const hl = o.halfL + margin;
  const c = Math.cos(o.yaw);
  const s = Math.sin(o.yaw);
  return ([[-hw, -hl], [hw, -hl], [hw, hl], [-hw, hl]] as Array<[number, number]>)
    .map(([lx, ly]) => {
      const p = worldToSvg(map, o.cx + lx * c - ly * s, o.cy + lx * s + ly * c);
      return `${p.sx},${p.sy}`;
    })
    .join(' ');
}

export function airplanePath(map: SpawnMap, o: SpawnObstacle, inset = 0.2): string {
  const hw = Math.max(0.2, o.halfW - inset); // wing half-span
  const hl = Math.max(0.2, o.halfL - inset); // fuselage half-length (nose -y)

  // Silhouette vertices in local (lx along wings, ly along fuselage; -ly = nose).
  // Proportions are fractions of the half-extents so it scales with the model.
  const bodyW = hw * 0.16;            // fuselage half-width
  const wingLy = hl * 0.05;           // wing root just aft of center
  const wingTipLy = hl * 0.45;        // wing sweep-back at the tips
  const tailLy = hl * 0.78;           // tailplane position
  const tailW = hw * 0.42;            // tailplane half-span

  const pts: Array<[number, number]> = [
    [0, -hl],                   // nose
    [bodyW, -hl * 0.45],        // right forward fuselage
    [bodyW, wingLy],            // right wing root front
    [hw, wingTipLy],            // right wing tip
    [bodyW * 1.2, wingTipLy + hl * 0.04], // right wing trailing root
    [bodyW, tailLy - hl * 0.1], // right rear fuselage
    [tailW, tailLy],            // right tail tip
    [bodyW, hl],                // right tail trailing
    [-bodyW, hl],               // left tail trailing
    [-tailW, tailLy],           // left tail tip
    [-bodyW, tailLy - hl * 0.1],
    [-bodyW * 1.2, wingTipLy + hl * 0.04],
    [-hw, wingTipLy],           // left wing tip
    [-bodyW, wingLy],           // left wing root front
    [-bodyW, -hl * 0.45],       // left forward fuselage
  ];

  const c = Math.cos(o.yaw);
  const s = Math.sin(o.yaw);
  const d = pts
    .map(([lx, ly], i) => {
      const wx = o.cx + lx * c - ly * s;
      const wy = o.cy + lx * s + ly * c;
      const p = worldToSvg(map, wx, wy);
      return `${i === 0 ? 'M' : 'L'} ${p.sx.toFixed(1)} ${p.sy.toFixed(1)}`;
    })
    .join(' ');
  return `${d} Z`;
}
