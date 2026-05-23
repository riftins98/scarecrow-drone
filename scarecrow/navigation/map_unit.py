"""Area mapping unit -- records boundaries during mapping flights.

Stub implementation for UC1 Map Area. Collects lidar-derived distance
measurements at each position and computes a bounding box as the area map.

Not full SLAM -- it just records "drone was at (x,y) and saw walls at these
distances" for each sample point, then produces a rectangular envelope.
Full SLAM is out of scope for the university project.
"""
from __future__ import annotations

import json
import math
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
        # result -> {"boundaries": "[{...}]", "area_size": 42.5}
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
        yaw_deg: float,
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

    def finish_mapping(self) -> dict:
        """Return recorded boundaries and wall-hit points."""
        self.active = False
        if not self.points:
            return {"boundaries": "[]", "wall_points": []}

        boundaries = list(self.corners)
        wall_points = list(self.wall_points)

        return {
            "boundaries": json.dumps(boundaries),
            "wall_points": wall_points,
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
    ) -> Path:
        """Render an annotated top-down view of a saved map JSON."""
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
        points = data.get("points", [])
        wall_points = data.get("wall_points", [])
        takeoff = data.get("takeoff_point", None)

        # --- set up figure ---
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.set_aspect("equal")
        ax.set_facecolor("#1a1a2e")
        fig.patch.set_facecolor("#0f0f1a")

        # --- boundaries polygon ---
        if boundaries:
            bx = [b["x"] for b in boundaries] + [boundaries[0]["x"]]
            by = [b["y"] for b in boundaries] + [boundaries[0]["y"]]
            ax.plot(bx, by, color="#ffffff", linewidth=1.5, linestyle="-",
                zorder=2, label="Boundary")
            ax.scatter(bx[:-1], by[:-1], s=30, c="#ffffff", zorder=4,
                   label="Boundary points")

        # --- flight points (tiny gray dots) ---
        if points:
            px = [p["x"] for p in points]
            py = [p["y"] for p in points]
            ax.scatter(px, py, s=4, c="#888888", alpha=0.7, zorder=3,
                       label=f"Flight points ({len(points)})")

        # --- wall hit points (cyan dots) ---
        if wall_points:
            wx = [p["x"] for p in wall_points]
            wy = [p["y"] for p in wall_points]
            ax.scatter(wx, wy, s=3, c="#4fc3f7", alpha=0.55, zorder=2,
                       label=f"Wall hits ({len(wall_points)})")

        # --- takeoff point (bigger red dot) ---
        if takeoff:
            ax.scatter(
                [takeoff["x"]], [takeoff["y"]],
                s=60, c="#ff4444", edgecolors="#ffffff", linewidths=0.8,
                zorder=4, label="Takeoff",
            )

        # --- styling ---
        ax.set_title("Mapped Area — Annotated", color="white",
                     fontsize=14, fontweight="bold", pad=12)
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
