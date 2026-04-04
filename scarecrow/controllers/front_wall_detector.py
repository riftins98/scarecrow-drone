"""Front-wall detection controller for wall-follow missions.

Separates front-structure interpretation from wall-follow control so behavior
is more consistent across maps with different obstacles and floor textures.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class FrontWallState:
    """Result of front-wall interpretation for one lidar scan."""

    raw_front_min_m: float
    robust_front_m: float
    center_front_m: float
    front_wall_visible: bool
    stop_confirmed: bool


class FrontWallDetector:
    """Detect if front wall is truly ahead and if stop threshold is reached.

    Design goals:
    - Keep flight speed command unchanged (controller responsibility).
    - Ignore off-axis nearby obstacles when deciding front-wall stop.
    - Require short temporal confirmation before declaring stop.
    """

    def __init__(
        self,
        stop_distance_m: float,
        front_sector_half_width_rad: float = 0.15,
        robust_percentile: float = 35.0,
        center_half_width_rad: float = math.radians(3.0),
        cluster_half_width_rad: float = math.radians(45.0),
        center_tolerance_rad: float = math.radians(8.0),
        min_cluster_points: int = 8,
        min_cluster_width_rad: float = math.radians(10.0),
        confirm_cycles: int = 4,
    ):
        self.stop_distance_m = stop_distance_m
        self.front_sector_half_width_rad = front_sector_half_width_rad
        self.robust_percentile = robust_percentile
        self.center_half_width_rad = center_half_width_rad
        self.cluster_half_width_rad = cluster_half_width_rad
        self.center_tolerance_rad = center_tolerance_rad
        self.min_cluster_points = min_cluster_points
        self.min_cluster_width_rad = min_cluster_width_rad
        self.confirm_cycles = max(1, confirm_cycles)

        self._stop_counter = 0

    def reset(self) -> None:
        self._stop_counter = 0

    def update(self, scan) -> FrontWallState:
        if scan is None or scan.num_samples == 0:
            self._stop_counter = 0
            return FrontWallState(
                raw_front_min_m=float("inf"),
                robust_front_m=float("inf"),
                center_front_m=float("inf"),
                front_wall_visible=False,
                stop_confirmed=False,
            )

        raw_front_min = scan.front_distance(self.front_sector_half_width_rad)

        robust_front = self._robust_front_distance(scan)
        center_front = self._center_front_distance(scan)
        front_wall_visible = self._front_wall_candidate(scan)

        stop_candidate = front_wall_visible and robust_front <= self.stop_distance_m
        if stop_candidate:
            self._stop_counter += 1
        else:
            self._stop_counter = 0

        return FrontWallState(
            raw_front_min_m=raw_front_min,
            robust_front_m=robust_front,
            center_front_m=center_front,
            front_wall_visible=front_wall_visible,
            stop_confirmed=self._stop_counter >= self.confirm_cycles,
        )

    def _robust_front_distance(self, scan) -> float:
        angles = scan.angles
        ranges = scan.ranges
        mask = (
            (angles >= -self.front_sector_half_width_rad)
            & (angles <= self.front_sector_half_width_rad)
            & (ranges > 0.1)
            & (ranges < 30.0)
        )
        values = ranges[mask]
        if values.size == 0:
            return float("inf")
        return float(np.percentile(values, self.robust_percentile))

    def _center_front_distance(self, scan) -> float:
        angles = scan.angles
        ranges = scan.ranges
        mask = (
            (angles >= -self.center_half_width_rad)
            & (angles <= self.center_half_width_rad)
            & (ranges > 0.1)
            & (ranges < 30.0)
        )
        values = ranges[mask]
        if values.size == 0:
            return float("inf")
        return float(np.median(values))

    def _front_wall_candidate(self, scan) -> bool:
        angles = scan.angles
        ranges = scan.ranges

        clusters: list[list[tuple[float, float]]] = []
        active: list[tuple[float, float]] = []
        prev_angle: float | None = None
        prev_range: float | None = None

        for angle, dist in zip(angles, ranges):
            angle = float(angle)
            dist = float(dist)
            in_front = -self.cluster_half_width_rad <= angle <= self.cluster_half_width_rad
            valid = 0.1 < dist < 30.0

            if not (in_front and valid):
                if active:
                    clusters.append(active)
                    active = []
                prev_angle = None
                prev_range = None
                continue

            if not active:
                active = [(angle, dist)]
            else:
                angle_gap = abs(angle - prev_angle) if prev_angle is not None else 0.0
                range_jump = abs(dist - prev_range) if prev_range is not None else 0.0

                if angle_gap > 0.06 or range_jump > 0.7:
                    clusters.append(active)
                    active = [(angle, dist)]
                else:
                    active.append((angle, dist))

            prev_angle = angle
            prev_range = dist

        if active:
            clusters.append(active)

        if not clusters:
            return True

        nearest = min(clusters, key=lambda c: min(d for _, d in c))
        if len(nearest) < self.min_cluster_points:
            return False

        start_angle = nearest[0][0]
        end_angle = nearest[-1][0]
        width = abs(end_angle - start_angle)
        center = sum(a for a, _ in nearest) / len(nearest)

        return abs(center) <= self.center_tolerance_rad and width >= self.min_cluster_width_rad
