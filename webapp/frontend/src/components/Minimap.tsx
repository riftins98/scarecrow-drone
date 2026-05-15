import React, { useEffect, useRef, useState } from 'react';

interface Props {
  active: boolean;
}

interface Point { x: number; y: number; }

/**
 * Decorative top-down mini-map: a fake garage interior. The drone follows
 * a hand-built waypoint path that hugs the walls and routes AROUND every
 * interior obstacle (no clipping). Movement is slow enough to read.
 */
export default function Minimap({ active }: Props) {
  const [trail, setTrail] = useState<Point[]>([]);
  const [t, setT] = useState(0);

  // 1 frame ~ 16ms. 1800 frames ~ 30 seconds per full loop.
  const LOOP_FRAMES = 1800;

  const rafRef = useRef<number | null>(null);
  useEffect(() => {
    if (!active) {
      setTrail([]);
      return;
    }
    let cancelled = false;
    let frame = 0;
    let prevPhase = 0;
    const step = () => {
      if (cancelled) return;
      frame += 1;
      const phase = (frame / LOOP_FRAMES) % 1;
      const pos = pathPoint(phase);
      // Detect loop wrap (phase reset from near-1 back to near-0).
      const wrapped = phase < prevPhase;
      prevPhase = phase;
      setTrail(prev => {
        if (wrapped) return [pos];
        // Add a trail point every few frames so the line is readable.
        if (frame % 4 !== 0) return prev;
        return [...prev, pos];
      });
      setT(frame);
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => {
      cancelled = true;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [active]);

  const phase = active ? (t / LOOP_FRAMES) % 1 : 0;
  const current = active ? pathPoint(phase) : { x: 100, y: 100 };
  const headingDeg = active ? pathHeading(phase) : 0;

  return (
    <div className={`minimap ${active ? 'on' : 'off'}`}>
      <div className="minimap-header">
        <span className="minimap-title">MAP // GARAGE_A</span>
        <span className="minimap-tag">TOP DOWN</span>
      </div>
      <div className="minimap-scope">
        <svg viewBox="0 0 200 200" className="minimap-svg" aria-hidden="true">
          <defs>
            <pattern id="mm-grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20"
                fill="none"
                stroke="rgba(139,154,91,0.15)"
                strokeWidth="0.5" />
            </pattern>
          </defs>

          <rect x="0" y="0" width="200" height="200" fill="#0d1208" />
          <rect x="0" y="0" width="200" height="200" fill="url(#mm-grid)" />

          {/* Room walls */}
          <rect x="20" y="20" width="160" height="160"
            fill="none"
            stroke="#8b9a5b"
            strokeWidth="1.2" />

          {/* Interior obstacles — must match avoidance waypoints */}
          <rect x="60" y="60" width="20" height="14" fill="rgba(122,154,154,0.08)"
            stroke="#7a9a9a" strokeWidth="0.8" />
          <rect x="130" y="50" width="14" height="22" fill="rgba(122,154,154,0.08)"
            stroke="#7a9a9a" strokeWidth="0.8" />
          <rect x="120" y="120" width="30" height="14" fill="rgba(122,154,154,0.08)"
            stroke="#7a9a9a" strokeWidth="0.8" />
          <circle cx="55" cy="140" r="6" fill="rgba(122,154,154,0.08)"
            stroke="#7a9a9a" strokeWidth="0.8" />

          {/* Pigeon markers (decorative) */}
          {active && (
            <>
              <PigeonMarker x={45} y={45} blink={t} />
              <PigeonMarker x={165} y={170} blink={t + 120} />
              <PigeonMarker x={95} y={155} blink={t + 240} />
            </>
          )}

          {/* Trail */}
          {trail.length > 1 && (
            <polyline
              points={trail.map(p => `${p.x},${p.y}`).join(' ')}
              fill="none"
              stroke="#7a9a9a"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.55"
            />
          )}

          {/* Drone */}
          <g transform={`translate(${current.x.toFixed(2)} ${current.y.toFixed(2)}) rotate(${headingDeg.toFixed(1)})`}>
            <circle r="5" fill="rgba(139,154,91,0.18)" />
            <circle r="2.8" fill="#8b9a5b" />
            <path d="M 0 -5.5 L 1.6 -2 L -1.6 -2 Z" fill="#d4e090" />
          </g>
        </svg>
      </div>
      <div className="minimap-footer">
        <span className="minimap-coord">X: {current.x.toFixed(1)}  Y: {current.y.toFixed(1)}</span>
        <span className="minimap-coord">HDG: {Math.floor((headingDeg + 360) % 360)}°</span>
      </div>
    </div>
  );
}

function PigeonMarker({ x, y, blink }: { x: number; y: number; blink: number }) {
  const on = Math.floor(blink / 60) % 2 === 0;
  return (
    <g opacity={on ? 1 : 0.35}>
      <circle cx={x} cy={y} r="2.8" fill="none" stroke="#d4e090" strokeWidth="0.8" />
      <circle cx={x} cy={y} r="1.1" fill="#d4e090" />
    </g>
  );
}

/**
 * Hand-built waypoint loop that hugs the wall and routes AROUND each
 * obstacle. Coordinates are in the 0..200 SVG space.
 *
 * Obstacle reference:
 *   - box A: 60..80  x  60..74
 *   - box B: 130..144 x 50..72
 *   - box C: 120..150 x 120..134
 *   - pillar: circle cx=55 cy=140 r=6  (avoid radius ~10)
 *
 * The path goes clockwise: start TL, run along top wall jogging down
 * around box A and box B, down the right wall, along the bottom wall
 * detouring up around box C, up the left wall detouring out around the
 * pillar, back to start.
 */
const WAYPOINTS: Point[] = [
  // top wall, left-to-right with detours around box A and box B
  { x: 35,  y: 35  },
  { x: 55,  y: 35  },
  { x: 55,  y: 52  },  // dip down before box A's top-left corner
  { x: 85,  y: 52  },  // skim past A's right edge
  { x: 85,  y: 35  },
  { x: 125, y: 35  },
  { x: 125, y: 45  },  // dip before box B
  { x: 150, y: 45  },  // around B's right side
  { x: 150, y: 35  },
  { x: 165, y: 35  },
  // right wall, top-to-bottom
  { x: 165, y: 100 },
  { x: 165, y: 155 },
  // bottom wall, right-to-left with detour up around box C
  { x: 155, y: 165 },
  { x: 155, y: 145 }, // come up before C's right edge
  { x: 115, y: 145 }, // skim past C's bottom
  { x: 115, y: 165 }, // back down to bottom wall
  { x: 80,  y: 165 },
  { x: 35,  y: 165 },
  // left wall, bottom-to-top with detour around the pillar at (55,140)
  { x: 35,  y: 155 },
  { x: 35,  y: 152 }, // approach pillar
  { x: 40,  y: 140 }, // arc out left of the pillar (pillar avoid radius ~10)
  { x: 35,  y: 128 },
  { x: 35,  y: 35  }, // back to start
];

function pathPoint(phase: number): Point {
  // Total perimeter along the waypoint loop, in screen units.
  const segments = WAYPOINTS.map((p, i) => {
    const next = WAYPOINTS[(i + 1) % WAYPOINTS.length];
    const dx = next.x - p.x;
    const dy = next.y - p.y;
    return Math.hypot(dx, dy);
  });
  const totalLen = segments.reduce((a, b) => a + b, 0);
  const target = phase * totalLen;

  let acc = 0;
  for (let i = 0; i < WAYPOINTS.length; i++) {
    const segLen = segments[i];
    if (target <= acc + segLen) {
      const t = segLen === 0 ? 0 : (target - acc) / segLen;
      const p = WAYPOINTS[i];
      const next = WAYPOINTS[(i + 1) % WAYPOINTS.length];
      return {
        x: p.x + (next.x - p.x) * t,
        y: p.y + (next.y - p.y) * t,
      };
    }
    acc += segLen;
  }
  return WAYPOINTS[0];
}

function pathHeading(phase: number): number {
  const ahead = pathPoint((phase + 0.005) % 1);
  const here = pathPoint(phase);
  const dx = ahead.x - here.x;
  const dy = ahead.y - here.y;
  // SVG y goes down. atan2(dx, -dy) so 0deg = north (up).
  return Math.atan2(dx, -dy) * (180 / Math.PI);
}
