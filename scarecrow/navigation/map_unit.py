"""Area mapping unit -- records boundaries during mapping flights.

Stub implementation for UC1 Map Area. Collects lidar-derived distance
measurements at each position and computes a bounding box as the area map.

Not full SLAM -- it just records "drone was at (x,y) and saw walls at these
distances" for each sample point, then produces a rectangular envelope.
Full SLAM is out of scope for the university project.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from ..sensors.lidar.base import LidarScan


@dataclass
class MappingPoint:
    """A single measurement recorded during mapping."""
    x: float          # north_m (NED)
    y: float          # east_m (NED)
    front_dist: float
    rear_dist: float
    left_dist: float
    right_dist: float


class MapUnit:
    """Records area boundaries during a mapping flight.

    Typical use:
        mapper = MapUnit()
        mapper.start_mapping()
        # at each waypoint during flight:
        mapper.record_position(scan, north_m=pos.north, east_m=pos.east)
        # after last waypoint:
        result = mapper.finish_mapping()
        # result -> {"boundaries": "[{...}]", "area_size": 42.5}
    """

    def __init__(self) -> None:
        self.points: list[MappingPoint] = []
        self.active: bool = False

    def start_mapping(self) -> None:
        """Begin recording. Clears any previous points."""
        self.points = []
        self.active = True

    def record_position(
        self,
        scan: LidarScan,
        north_m: float,
        east_m: float,
    ) -> Optional[MappingPoint]:
        """Record a measurement at the current position. No-op if not active
        or if the scan is empty. Returns the point that was recorded."""
        if not self.active or scan is None or scan.num_samples == 0:
            return None
        point = MappingPoint(
            x=north_m,
            y=east_m,
            front_dist=scan.front_distance(),
            rear_dist=scan.rear_distance(),
            left_dist=scan.left_distance(),
            right_dist=scan.right_distance(),
        )
        self.points.append(point)
        return point

    def finish_mapping(self) -> dict:
        """Compute bounding box from recorded points. Returns area_map-compatible dict.

        Each point contributes (x ± front/rear_dist, y ± left/right_dist) to
        the envelope. The final polygon is the smallest axis-aligned rectangle
        that contains all walls observed from all sampled positions.
        """
        self.active = False
        if not self.points:
            return {"boundaries": "[]", "area_size": 0.0}

        min_x = min(p.x - p.rear_dist for p in self.points)
        max_x = max(p.x + p.front_dist for p in self.points)
        min_y = min(p.y - p.left_dist for p in self.points)
        max_y = max(p.y + p.right_dist for p in self.points)

        boundaries = [
            {"x": min_x, "y": min_y},
            {"x": max_x, "y": min_y},
            {"x": max_x, "y": max_y},
            {"x": min_x, "y": max_y},
        ]
        area_size = (max_x - min_x) * (max_y - min_y)

        return {
            "boundaries": json.dumps(boundaries),
            "area_size": round(area_size, 2),
        }
