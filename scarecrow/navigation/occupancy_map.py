"""2D occupancy grid map built from lidar scans in a NED coordinate frame.

Coordinate system:
    NED frame — north = +row, east = +col.
    Grid origin is at (origin_n, origin_e) in meters.
    Default: 24m x 24m at 0.1m/cell = 240x240 cells,
    centered on the 20m indoor room with a 2m margin.

Cell values:
    UNKNOWN  = 0    (never observed)
    FREE     = 50   (ray passed through — no obstacle)
    OCCUPIED = 100  (ray endpoint — obstacle detected)
"""
from __future__ import annotations

import math

import numpy as np

from ..sensors.lidar.base import LidarScan


class OccupancyMap:
    """Incremental 2D occupancy grid map.

    Args:
        resolution: Meters per cell. Default 0.1m.
        size_m: Total map side length in meters. Default 24m.
        origin_n: North coordinate of the map's bottom-left corner (meters).
        origin_e: East coordinate of the map's bottom-left corner (meters).
    """

    UNKNOWN = 0
    FREE = 50
    OCCUPIED = 100

    def __init__(
        self,
        resolution: float = 0.1,
        size_m: float = 24.0,
        origin_n: float = -12.0,
        origin_e: float = -12.0,
    ):
        self.resolution = resolution
        self.size_m = size_m
        self.origin_n = origin_n
        self.origin_e = origin_e
        self._cells = int(round(size_m / resolution))
        self.grid = np.full((self._cells, self._cells), self.UNKNOWN, dtype=np.uint8)

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _to_grid(self, north_m: float, east_m: float) -> tuple[int, int]:
        """Convert NED world coordinates to (row, col) grid indices."""
        row = math.floor((north_m - self.origin_n) / self.resolution)
        col = math.floor((east_m - self.origin_e) / self.resolution)
        return row, col

    def _in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self._cells and 0 <= col < self._cells

    # ------------------------------------------------------------------
    # Ray tracing (Bresenham)
    # ------------------------------------------------------------------

    def _trace_ray(self, r0: int, c0: int, r1: int, c1: int) -> None:
        """Mark FREE along the ray r0,c0 → r1,c1 and OCCUPIED at endpoint."""
        dr = abs(r1 - r0)
        dc = abs(c1 - c0)
        sr = 1 if r1 > r0 else -1
        sc = 1 if c1 > c0 else -1
        err = dr - dc
        r, c = r0, c0

        while True:
            if not self._in_bounds(r, c):
                break
            if r == r1 and c == c1:
                self.grid[r, c] = self.OCCUPIED
                break
            # Mark free only if not already occupied (don't erase obstacles)
            if self.grid[r, c] != self.OCCUPIED:
                self.grid[r, c] = self.FREE
            e2 = 2 * err
            if e2 > -dc:
                err -= dc
                r += sr
            if e2 < dr:
                err += dr
                c += sc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        scan: LidarScan,
        north_m: float,
        east_m: float,
        yaw_rad: float,
        stride: int = 4,
    ) -> None:
        """Integrate one lidar scan into the grid.

        Args:
            scan: Full 360° lidar scan.
            north_m: Drone north position in NED (meters).
            east_m: Drone east position in NED (meters).
            yaw_rad: Drone heading in radians (0 = north, positive = clockwise).
            stride: Process every Nth ray. Default 4 → 360 rays per scan.
        """
        drone_row, drone_col = self._to_grid(north_m, east_m)
        angles = scan.angles
        ranges = scan.ranges

        for i in range(0, scan.num_samples, stride):
            r = ranges[i]
            if not (0.15 < r < 25.0):
                continue
            # Lidar angle in body frame → world frame (NED: 0=north, CW positive)
            # LidarScan: 0=forward, positive=left (CCW) → negate for NED CW convention
            world_angle = yaw_rad - angles[i]
            end_north = north_m + r * math.cos(world_angle)
            end_east = east_m + r * math.sin(world_angle)
            end_row, end_col = self._to_grid(end_north, end_east)
            self._trace_ray(drone_row, drone_col, end_row, end_col)

    def save_pdf(
        self,
        path: str,
        trajectory: list[tuple[float, float]] | None = None,
    ) -> None:
        """Render the occupancy grid as a PDF with optional drone trajectory.

        Args:
            path: Output file path (e.g. "output/room_map.pdf").
            trajectory: List of (north_m, east_m) poses to overlay as a path.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import os

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        # Build a display image: UNKNOWN=light gray, FREE=white, OCCUPIED=black
        display = np.zeros((*self.grid.shape, 3), dtype=np.uint8)
        display[self.grid == self.UNKNOWN] = [200, 200, 200]   # light gray
        display[self.grid == self.FREE] = [245, 245, 245]       # near-white
        display[self.grid == self.OCCUPIED] = [30, 30, 30]      # near-black

        fig, ax = plt.subplots(figsize=(10, 10))

        # imshow: row=0 is top → flip so north is up
        extent = [
            self.origin_e,
            self.origin_e + self.size_m,
            self.origin_n,
            self.origin_n + self.size_m,
        ]
        ax.imshow(
            np.flipud(display),
            extent=extent,
            origin="upper",
            interpolation="nearest",
            aspect="equal",
        )

        # Drone trajectory
        if trajectory and len(trajectory) > 1:
            ns = [p[0] for p in trajectory]
            es = [p[1] for p in trajectory]
            ax.plot(es, ns, color="#E74C3C", linewidth=1.5, label="Drone path", zorder=3)
            ax.plot(es[0], ns[0], "g^", markersize=10, label="Start", zorder=4)
            ax.plot(es[-1], ns[-1], "rs", markersize=10, label="End", zorder=4)

        ax.set_xlim(self.origin_e, self.origin_e + self.size_m)
        ax.set_ylim(self.origin_n, self.origin_n + self.size_m)
        ax.set_xlabel("East (m)")
        ax.set_ylabel("North (m)")
        ax.set_title("Scarecrow Drone — Room Occupancy Map", fontsize=14)
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.2)

        # Legend patches
        patches = [
            mpatches.Patch(color=[c / 255 for c in [200, 200, 200]], label="Unknown"),
            mpatches.Patch(color=[c / 255 for c in [245, 245, 245]], label="Free"),
            mpatches.Patch(color=[c / 255 for c in [30, 30, 30]], label="Occupied"),
        ]
        legend2 = ax.legend(handles=patches, loc="upper left", fontsize=9, title="Grid cells")
        ax.add_artist(legend2)
        if trajectory:
            ax.legend(loc="upper right", fontsize=9)

        # Stats
        total = self.grid.size
        occupied_pct = 100.0 * np.sum(self.grid == self.OCCUPIED) / total
        free_pct = 100.0 * np.sum(self.grid == self.FREE) / total
        traj_pts = len(trajectory) if trajectory else 0
        ax.text(
            0.02, 0.02,
            f"Resolution: {self.resolution}m/cell  |  Grid: {self._cells}×{self._cells}"
            f"\nFree: {free_pct:.1f}%  Occupied: {occupied_pct:.1f}%"
            f"\nPose samples: {traj_pts}",
            transform=ax.transAxes,
            fontsize=8,
            verticalalignment="bottom",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
        )

        fig.savefig(path, bbox_inches="tight", dpi=150)
        plt.close(fig)
        print(f"  Map PDF saved: {path}")

    def save_npz(
        self,
        path: str,
        trajectory: list[tuple[float, float]] | None = None,
    ) -> None:
        """Serialize map to numpy .npz for Phase 2 (pigeon detection).

        Saved arrays:
            grid        — uint8 occupancy grid (UNKNOWN/FREE/OCCUPIED values)
            origin      — [origin_n, origin_e] in meters
            resolution  — scalar, meters per cell
            trajectory  — Nx2 float array of (north, east) poses, or empty

        Args:
            path: Output file path (e.g. "output/room_map.npz").
            trajectory: List of (north_m, east_m) poses recorded during flight.
        """
        import os
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        traj_arr = np.array(trajectory, dtype=np.float32) if trajectory else np.empty((0, 2), dtype=np.float32)
        np.savez_compressed(
            path,
            grid=self.grid,
            origin=np.array([self.origin_n, self.origin_e], dtype=np.float32),
            resolution=np.float32(self.resolution),
            trajectory=traj_arr,
        )
        print(f"  Map NPZ saved:  {path}")

    @classmethod
    def load(cls, path: str) -> "OccupancyMap":
        """Load a saved map from an .npz file (for Phase 2).

        Args:
            path: Path to a .npz file saved by save_npz().

        Returns:
            OccupancyMap with grid, origin, and resolution restored.
        """
        data = np.load(path)
        origin_n, origin_e = float(data["origin"][0]), float(data["origin"][1])
        resolution = float(data["resolution"])
        grid = data["grid"]
        size_m = grid.shape[0] * resolution
        obj = cls(resolution=resolution, size_m=size_m, origin_n=origin_n, origin_e=origin_e)
        obj.grid = grid
        return obj
