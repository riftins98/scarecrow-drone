"""Area mapping unit -- records boundaries during mapping flights.

This is intentionally lighter than full SLAM: it records the drone route and
lidar-derived wall hits, then builds a rectangular wall envelope from those
hits for room-circuit maps.
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from ..sensors.lidar.base import LidarScan


@dataclass
class MappingPoint:
    """A single measurement recorded during mapping."""
    x: float          # north_m (NED)
    y: float          # east_m (NED)
    yaw_deg: float
    front_dist: float
    rear_dist: float
    left_dist: float
    right_dist: float


class MapUnit:
    """Records area boundaries during a mapping flight.

    Typical use:
        mapper = MapUnit()
        mapper.start_mapping()
        mapper.set_takeoff_point(north_m, east_m)
        # at each waypoint during flight:
        mapper.record_position(scan, north_m=pos.north, east_m=pos.east)
        # after last waypoint:
        result = mapper.finish_mapping()
        # result -> {"boundaries": "[{...}]", "route": [{...}], "area_size": 42.5}
    """

    def __init__(self) -> None:
        self.points: list[MappingPoint] = []
        self.corners: list[dict] = []
        self.wall_points: list[dict] = []
        self.active: bool = False
        self.takeoff_point: Optional[dict] = None

    def start_mapping(self) -> None:
        """Begin recording. Clears any previous points."""
        self.points = []
        self.corners = []
        self.wall_points = []
        self.active = True

    def set_takeoff_point(self, north_m: float, east_m: float) -> None:
        """Record the takeoff position so it can be included in the map."""
        self.takeoff_point = {"x": north_m, "y": east_m}

    def record_position(
        self,
        scan: LidarScan,
        north_m: float,
        east_m: float,
        yaw_deg: float = 0.0,
    ) -> Optional[MappingPoint]:
        """Record a measurement at the current position. No-op if not active
        or if the scan is empty. Returns the point that was recorded."""
        if not self.active or scan is None or scan.num_samples == 0:
            return None
        point = MappingPoint(
            x=north_m,
            y=east_m,
            yaw_deg=yaw_deg,
            front_dist=scan.front_distance(),
            rear_dist=scan.rear_distance(),
            left_dist=scan.left_distance(),
            right_dist=scan.right_distance(),
        )
        self.points.append(point)
        return point

    def record_corner(self, north_m: float, east_m: float) -> None:
        """Record a corner location (typically when turning)."""
        if not self.active:
            return
        self.corners.append({"x": north_m, "y": east_m})

    def record_left_wall_hit(
        self,
        scan: LidarScan,
        north_m: float,
        east_m: float,
        yaw_deg: float,
        *,
        min_m: float,
        max_m: float,
    ) -> Optional[dict]:
        """Record a single left-wall hit projected into world frame."""
        if not self.active or scan is None or scan.num_samples == 0:
            return None
        left_dist = scan.left_distance()
        if not math.isfinite(left_dist) or left_dist < min_m or left_dist > max_m:
            return None

        yaw_rad = math.radians(yaw_deg)
        right_x = -math.sin(yaw_rad)
        right_y = math.cos(yaw_rad)
        hit = {
            "x": north_m - right_x * left_dist,
            "y": east_m - right_y * left_dist,
        }
        self.wall_points.append(hit)
        return hit

    def record_wall_hits(
        self,
        scan: LidarScan,
        north_m: float,
        east_m: float,
        yaw_deg: float,
        *,
        min_m: float,
        max_m: float,
    ) -> list[dict]:
        """Record front/rear/left/right lidar wall hits in world frame."""
        if not self.active or scan is None or scan.num_samples == 0:
            return []

        yaw_rad = math.radians(yaw_deg)
        fwd_x = math.cos(yaw_rad)
        fwd_y = math.sin(yaw_rad)
        right_x = -math.sin(yaw_rad)
        right_y = math.cos(yaw_rad)

        candidates = [
            (scan.front_distance(), fwd_x, fwd_y),
            (scan.rear_distance(), -fwd_x, -fwd_y),
            (scan.left_distance(), -right_x, -right_y),
            (scan.right_distance(), right_x, right_y),
        ]

        hits = []
        for dist, vec_x, vec_y in candidates:
            if not math.isfinite(dist) or dist < min_m or dist > max_m:
                continue
            hit = {
                "x": north_m + vec_x * dist,
                "y": east_m + vec_y * dist,
            }
            self.wall_points.append(hit)
            hits.append(hit)
        return hits

    def finish_mapping(self) -> dict:
        """Return wall boundaries, drone route, and wall-hit points."""
        self.active = False
        if not self.points:
            return {
                "boundaries": "[]",
                "route": [],
                "wall_points": [],
                "area_size": 0.0,
            }

        route = list(self.corners)
        wall_points = list(self.wall_points) or self._wall_points()
        boundaries = self._axis_aligned_boundary(wall_points) if wall_points else route

        return {
            "boundaries": json.dumps(boundaries),
            "route": route,
            "wall_points": wall_points,
            "area_size": round(self._polygon_area(boundaries), 2),
        }

    # ------------------------------------------------------------------
    # Annotation
    # ------------------------------------------------------------------

    @staticmethod
    def annotate_map(
        map_json_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        *,
        show: bool = False,
        debug: bool = False,
    ) -> Path:
        """Render a production-friendly top-down view of a saved map JSON.

        The default image hides developer-only samples such as raw wall hits,
        lidar distance points, turn points, and heading-restore events. Pass
        debug=True to include those map construction details.
        """
        import os
        import matplotlib
        if not show or not os.environ.get("DISPLAY"):
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        map_json_path = Path(map_json_path)
        with open(map_json_path, "r") as fh:
            data = json.load(fh)

        if output_path is None:
            output_path = map_json_path.parent / "map_annotated.png"
        else:
            output_path = Path(output_path)

        # --- extract data ---
        boundaries = data.get("boundaries", [])
        route = data.get("route") or data.get("route_points") or []
        points = data.get("points", [])
        route_samples = data.get("route_samples", [])
        wall_points = data.get("wall_points", [])
        takeoff = data.get("takeoff_point", None)
        events = data.get("events", [])
        if wall_points and not route and boundaries:
            # Legacy maps used the route/turn points as "boundaries".
            route = boundaries
            boundaries = MapUnit._axis_aligned_boundary(wall_points)

        # --- set up figure ---
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.set_aspect("equal")
        ax.set_facecolor("#1a1a2e")
        fig.patch.set_facecolor("#0f0f1a")

        # --- wall boundary polygon ---
        if boundaries:
            bx = [b["x"] for b in boundaries] + [boundaries[0]["x"]]
            by = [b["y"] for b in boundaries] + [boundaries[0]["y"]]
            ax.plot(
                bx, by, color="#ffffff", linewidth=2.2, linestyle="-",
                zorder=2, label="Wall boundary",
            )
            if debug:
                ax.scatter(
                    bx[:-1], by[:-1], s=30, c="#ffffff", zorder=4,
                    label="Wall boundary corners",
                )

        # --- developer-only recorded flight path ---
        if debug and points:
            px = [p["x"] for p in points]
            py = [p["y"] for p in points]
            ax.plot(
                px, py, color="#ffd166", linewidth=1.8, alpha=0.9,
                zorder=5, label="Drone flight path",
            )
            ax.scatter(px, py, s=4, c="#888888", alpha=0.7, zorder=3,
                       label=f"Flight points ({len(points)})")

        # --- developer-only route/turn points, kept open because the final leg
        # may not end exactly on the first recorded point.
        if debug and route:
            rx = [p["x"] for p in route]
            ry = [p["y"] for p in route]
            ax.plot(
                rx, ry, color="#ffd166", linewidth=1.0, linestyle="--",
                alpha=0.75, zorder=5, label="Turn-point route",
            )
            ax.scatter(
                rx, ry, s=24, c="#ffd166", zorder=6,
                label="Route turn points",
            )

        # --- sampled mission route by phase ---
        if route_samples:
            phase_styles = {
                "wall_follow": ("#ffd166", "Wall-follow route"),
                "pursuit": ("#ff4d6d", "Pursuit route"),
                "corner_turn": ("#f8961e", "Corner turn route"),
                "return_entry": ("#9b5de5", "Return to pursuit entry"),
                "restore_heading": ("#f15bb5", "Restore heading"),
                "reverse_leg": ("#00bbf9", "Reverse to leg start"),
                "stabilize_landing": ("#00f5d4", "Pre-landing stabilize"),
                "landing": ("#80ed99", "Landing"),
            }
            seen_phase_labels = set()
            segment: list[dict] = []
            segment_phase = None

            def draw_segment(samples: list[dict], phase: str | None) -> None:
                if len(samples) < 2:
                    return
                color, label = phase_styles.get(
                    phase or "unknown",
                    ("#cdb4db", f"{phase or 'Unknown'} route"),
                )
                legend_label = label if label not in seen_phase_labels else None
                seen_phase_labels.add(label)
                sx = [p["x"] for p in samples]
                sy = [p["y"] for p in samples]
                ax.plot(sx, sy, color=color, linewidth=2.4, alpha=0.95,
                        zorder=6, label=legend_label)
                if debug:
                    ax.scatter(sx, sy, s=12, c=color, alpha=0.95, zorder=7)

            for sample in route_samples:
                phase = sample.get("phase", "unknown")
                if segment_phase is None:
                    segment_phase = phase
                if phase != segment_phase:
                    draw_segment(segment, segment_phase)
                    segment = []
                    segment_phase = phase
                segment.append(sample)
            draw_segment(segment, segment_phase)

        # --- developer-only wall hit points (cyan dots) ---
        if debug and wall_points:
            wx = [p["x"] for p in wall_points]
            wy = [p["y"] for p in wall_points]
            ax.scatter(wx, wy, s=2, c="#4fc3f7", alpha=0.28, zorder=2,
                       label=f"Raw lidar wall hits ({len(wall_points)})")

        # --- takeoff point, used only when there is no circuit-start event ---
        has_circuit_start = any(event.get("type") == "circuit_start" for event in events)
        if takeoff and not has_circuit_start:
            ax.scatter(
                [takeoff["x"]], [takeoff["y"]],
                s=60, c="#ff4444", edgecolors="#ffffff", linewidths=0.8,
                zorder=4, label="Start",
            )

        # --- production mission events ---
        if events:
            event_styles = {
                "circuit_start": ("#00d1ff", "Start", "o"),
                "pursuit_entry": ("#ff6b6b", "Pigeon detected", "X"),
                "target_reached": ("#ff9f1c", "Target reached", "*"),
                "landing_target": ("#7bd88f", "Landing", "P"),
            }
            seen_event_labels = set()
            for event in events:
                event_type = event.get("type")
                if event_type not in event_styles:
                    if not debug:
                        continue
                    if event_type == "leg_start":
                        continue
                if event_type == "leg_start":
                    continue
                if "x" not in event or "y" not in event:
                    continue
                color, default_label, marker = event_styles.get(
                    event_type,
                    ("#f4d35e", "Mission event", "o"),
                )
                label = default_label if default_label not in seen_event_labels else None
                seen_event_labels.add(default_label)
                ax.scatter(
                    [event["x"]], [event["y"]],
                    s=70, c=color, marker=marker, edgecolors="#ffffff",
                    linewidths=0.8, zorder=7, label=label,
                )
                text = default_label if not debug else event.get("label")
                labeled_event_types = (
                    {"circuit_start", "pursuit_entry", "target_reached", "landing_target"}
                    if debug else {"pursuit_entry", "target_reached"}
                )
                if text and event_type in labeled_event_types:
                    ax.annotate(
                        str(text),
                        xy=(event["x"], event["y"]),
                        xytext=(5, 5),
                        textcoords="offset points",
                        color="white",
                        fontsize=7,
                        zorder=8,
                    )

        # --- styling ---
        title = "Mission Map"
        if data.get("area_size"):
            title = f"Mission Map - {float(data['area_size']):.1f} m²"
        ax.set_title(title, color="white", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("X  (north_m)", color="white", fontsize=10)
        ax.set_ylabel("Y  (east_m)", color="white", fontsize=10)
        ax.tick_params(colors="white", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#333333")
        ax.grid(True, color="#2a2a3e", linewidth=0.5, alpha=0.6)

        ax.legend(
            loc="upper right", fontsize=9, framealpha=0.7,
            facecolor="#1a1a2e", edgecolor="#4fc3f7", labelcolor="white",
        )

        # --- save ---
        fig.savefig(
            output_path, dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        if show:
            plt.show()
        plt.close(fig)

        return output_path.resolve()

    def _wall_points(self) -> list[dict]:
        """Project lidar distances into world-frame wall-hit points."""
        wall_points: list[dict] = []
        for p in self.points:
            yaw_rad = math.radians(p.yaw_deg)
            fwd_x = math.cos(yaw_rad)
            fwd_y = math.sin(yaw_rad)
            right_x = -math.sin(yaw_rad)
            right_y = math.cos(yaw_rad)

            if math.isfinite(p.front_dist):
                wall_points.append({"x": p.x + fwd_x * p.front_dist, "y": p.y + fwd_y * p.front_dist})
            if math.isfinite(p.rear_dist):
                wall_points.append({"x": p.x - fwd_x * p.rear_dist, "y": p.y - fwd_y * p.rear_dist})
            if math.isfinite(p.left_dist):
                wall_points.append({"x": p.x - right_x * p.left_dist, "y": p.y - right_y * p.left_dist})
            if math.isfinite(p.right_dist):
                wall_points.append({"x": p.x + right_x * p.right_dist, "y": p.y + right_y * p.right_dist})
        return wall_points

    @staticmethod
    def _axis_aligned_boundary(points: list[dict]) -> list[dict]:
        """Build the room wall rectangle from projected wall-hit points."""
        if not points:
            return []

        xs = sorted(p["x"] for p in points)
        ys = sorted(p["y"] for p in points)
        if len(xs) < 4 or len(ys) < 4:
            return MapUnit._convex_hull(points)

        trim = max(1, int(len(xs) * 0.1))
        min_x = statistics.fmean(xs[:trim])
        max_x = statistics.fmean(xs[-trim:])
        min_y = statistics.fmean(ys[:trim])
        max_y = statistics.fmean(ys[-trim:])
        if math.isclose(min_x, max_x) or math.isclose(min_y, max_y):
            return MapUnit._convex_hull(points)

        return [
            {"x": min_x, "y": max_y},
            {"x": min_x, "y": min_y},
            {"x": max_x, "y": min_y},
            {"x": max_x, "y": max_y},
        ]

    @staticmethod
    def _convex_hull(points: list[dict]) -> list[dict]:
        """Compute a convex hull (monotonic chain) for map boundaries."""
        if len(points) <= 1:
            return points

        def cross(o, a, b) -> float:
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        pts = sorted({(p["x"], p["y"]) for p in points})
        if len(pts) <= 2:
            return [{"x": x, "y": y} for x, y in pts]

        lower: list[tuple[float, float]] = []
        for pt in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], pt) <= 0:
                lower.pop()
            lower.append(pt)

        upper: list[tuple[float, float]] = []
        for pt in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], pt) <= 0:
                upper.pop()
            upper.append(pt)

        hull = lower[:-1] + upper[:-1]
        return [{"x": x, "y": y} for x, y in hull]

    @staticmethod
    def _polygon_area(points: list[dict]) -> float:
        """Compute polygon area using the shoelace formula."""
        if len(points) < 3:
            return 0.0

        area = 0.0
        for i in range(len(points)):
            x1, y1 = points[i]["x"], points[i]["y"]
            x2, y2 = points[(i + 1) % len(points)]["x"], points[(i + 1) % len(points)]["y"]
            area += x1 * y2 - x2 * y1
        return abs(area) * 0.5
