"""Owns everything a mission records for its customer-facing map.

Before this existed the hangar mission carried five parallel pieces of state --
a MapUnit, an events list, a route-sample list, a phase dict and a list of
in-flight sampling tasks -- and passed some subset of them into every helper.
Any function that appended to the wrong one, or forgot to await the pending
tasks, produced a map that was quietly incomplete.

Grouping them here makes the map a single object with one lifecycle:
`start()` -> record during flight -> `save()`.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import asdict
from typing import Any

from scarecrow.navigation.arena import refine_boundary_from_route_samples
from scarecrow.navigation.map_unit import MapUnit
from scarecrow.sensors.lidar.validation import (
    DEFAULT_MAX_DISTANCE_M,
    DEFAULT_MIN_DISTANCE_M,
    scan_valid_for_map,
)

# Record one map sample every N wall-follow status callbacks. Every callback is
# far more resolution than a boundary estimate needs and each sample costs two
# awaits on the MAVSDK link.
DEFAULT_MAP_RECORD_EVERY = 10


class MissionRecorder:
    """Collects map points, named events and a time-series route.

    Three kinds of record, deliberately separate:

    - **map samples** -- lidar wall hits, the raw material for the boundary.
    - **events** -- named moments ("Pursuit entry on leg 2"), what a reader of
      the map actually wants to see.
    - **route samples** -- a once-per-second pose trace, which both draws the
      flown path and supplies the evidence that refines the boundary.
    """

    def __init__(
        self,
        *,
        min_distance_m: float = DEFAULT_MIN_DISTANCE_M,
        max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    ) -> None:
        self.mapper = MapUnit()
        self.events: list[dict] = []
        self.route_samples: list[dict] = []
        self._min_distance_m = min_distance_m
        self._max_distance_m = max_distance_m
        # Map sampling is fired off as background tasks so it never stalls the
        # control loop. They must be awaited before the map is built, or the
        # last samples are lost.
        self._pending: list[asyncio.Task] = []
        self._saved = False

    # -- lifecycle ------------------------------------------------------

    def start(self) -> None:
        self.mapper.start_mapping()

    def set_takeoff_point(self, north_m: float, east_m: float) -> None:
        self.mapper.set_takeoff_point(north_m, east_m)

    @property
    def has_content(self) -> bool:
        return bool(self.mapper.active or self.mapper.points or self.events)

    @property
    def saved(self) -> bool:
        return self._saved

    # -- recording ------------------------------------------------------

    async def record_sample(self, drone, lidar) -> bool:
        """Record one pose + lidar sample. Returns False if the scan is unusable."""
        scan = lidar.get_scan()
        if not scan_valid_for_map(
            scan, min_m=self._min_distance_m, max_m=self._max_distance_m
        ):
            return False

        pos = await drone.get_position()
        yaw_deg = await drone.get_yaw()
        self.mapper.record_position(
            scan, pos.position.north_m, pos.position.east_m, yaw_deg
        )
        self.mapper.record_wall_hits(
            scan,
            pos.position.north_m,
            pos.position.east_m,
            yaw_deg,
            min_m=self._min_distance_m,
            max_m=self._max_distance_m,
        )
        return True

    def record_sample_soon(self, drone, lidar) -> None:
        """Schedule a sample without blocking the caller's control loop."""
        self._pending.append(asyncio.create_task(self.record_sample(drone, lidar)))

    async def drain_pending(self) -> None:
        """Await scheduled samples. Must run before building the map."""
        if not self._pending:
            return
        await asyncio.gather(*self._pending, return_exceptions=True)
        self._pending.clear()

    async def record_pose_event(
        self,
        drone,
        *,
        event_type: str,
        label: str,
        leg: int | None = None,
        **extra: Any,
    ) -> dict:
        """Record a named event at the drone's current pose."""
        pos = await drone.get_position()
        yaw_deg = await drone.get_yaw()
        event = {
            "type": event_type,
            "label": label,
            "x": pos.position.north_m,
            "y": pos.position.east_m,
            "yaw_deg": yaw_deg,
            "timestamp": time.time(),
        }
        if leg is not None:
            event["leg"] = leg
        event.update(extra)
        self.events.append(event)
        return event

    def add_event(self, event: dict) -> dict:
        """Record a pre-built event (one whose pose is already known)."""
        self.events.append(event)
        return event

    def record_corner(self, x: float, y: float, *, min_separation_m: float = 0.05) -> bool:
        """Record a circuit corner, ignoring near-duplicates.

        A leg can start effectively where the last one ended; without this the
        corner list grows a cluster of coincident points that the rendered map
        draws as a blob.
        """
        if self.mapper.corners:
            last = self.mapper.corners[-1]
            if (
                abs(last["x"] - x) <= min_separation_m
                and abs(last["y"] - y) <= min_separation_m
            ):
                return False
        self.mapper.record_corner(x, y)
        return True

    # -- output ---------------------------------------------------------

    def build_payload(
        self,
        *,
        boundary_override: list[dict] | None = None,
        wall_distance: float,
    ) -> dict:
        result = self.mapper.finish_mapping()
        boundaries_json = result.get("boundaries", "[]")
        try:
            boundaries = json.loads(boundaries_json)
        except json.JSONDecodeError:
            boundaries = []
        if boundary_override:
            boundaries = boundary_override
        boundaries = refine_boundary_from_route_samples(
            boundaries,
            self.route_samples,
            wall_distance=wall_distance,
        )
        return {
            "boundaries": boundaries,
            "boundaries_json": json.dumps(boundaries),
            "route": result.get("route", []),
            "route_json": json.dumps(result.get("route", [])),
            "takeoff_point": self.mapper.takeoff_point,
            "points": [asdict(p) for p in self.mapper.points],
            "route_samples": self.route_samples,
            "wall_points": result.get("wall_points", []),
            "events": self.events,
            "area_size": round(MapUnit._polygon_area(boundaries), 2),
        }

    async def save(
        self,
        output_dir: str,
        *,
        wall_distance: float,
        boundary_override: list[dict] | None = None,
    ) -> str | None:
        """Write map.json, render the annotated map, emit ``MAP_RESULT:``.

        Best-effort by design: this runs in mission teardown, after the drone
        is already down. A rendering failure must not mask the flight's own
        outcome, so it reports and returns None instead of raising.

        ``MAP_RESULT:`` is parsed by the webapp -- keep the prefix exact.
        """
        await self.drain_pending()
        try:
            payload = self.build_payload(
                boundary_override=boundary_override,
                wall_distance=wall_distance,
            )
            map_path = os.path.join(output_dir, "map.json")
            with open(map_path, "w") as fh:
                json.dump(payload, fh, indent=2)
            annotated_path = MapUnit.annotate_map(map_path, center_origin=True)
            self._saved = True
            print(f"\nMap saved: {map_path}")
            print(f"Annotated map: {annotated_path}")
            print(
                f"MAP_RESULT:{json.dumps({'map_path': str(annotated_path)})}",
                flush=True,
            )
            return map_path
        except Exception as exc:
            print(f"  WARNING: map save/annotation failed: {exc}")
            return None


class RouteRecorder:
    """Background once-per-second pose trace with a mission phase label.

    Also the single source of the live altitude reference that status lines
    read, so every phase reports altitude the same way without each one
    querying the drone.
    """

    def __init__(
        self,
        drone,
        lidar,
        recorder: MissionRecorder,
        *,
        interval_s: float = 1.0,
        target_alt_m: float | None = None,
        warning_error_m: float = 0.20,
    ) -> None:
        self._drone = drone
        self._lidar = lidar
        self._recorder = recorder
        self._interval_s = interval_s
        self._target_alt_m = target_alt_m
        self._warning_error_m = warning_error_m
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.phase: dict[str, str] = {"phase": "wall_follow"}
        self.altitude: dict[str, Any] = {
            "agl_m": None,
            "target_alt_m": target_alt_m,
            "error_m": None,
        }

    def set_phase(self, phase: str) -> None:
        self.phase["phase"] = phase

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self, *, timeout_s: float = 2.0) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout_s)
        except Exception:
            pass
        self._task = None

    async def _loop(self) -> None:
        from scarecrow.flight.altitude import agl_from_position

        while not self._stop.is_set():
            # Swallow per-tick failures: this is telemetry. A dropped MAVSDK
            # read must never take down a flight that is otherwise fine.
            try:
                pos = await self._drone.get_position()
                yaw_deg = await self._drone.get_yaw()
                phase = self.phase.get("phase", "unknown")
                agl = agl_from_position(pos, self._drone.ground_z)
                alt_error = None if self._target_alt_m is None else agl - self._target_alt_m
                sample: dict[str, Any] = {
                    "x": pos.position.north_m,
                    "y": pos.position.east_m,
                    "yaw_deg": yaw_deg,
                    "phase": phase,
                    "agl_m": agl,
                    "timestamp": time.time(),
                }
                if self._target_alt_m is not None:
                    sample["target_alt_m"] = self._target_alt_m
                    sample["alt_error_m"] = alt_error
                self.altitude["agl_m"] = agl
                self.altitude["target_alt_m"] = self._target_alt_m
                self.altitude["error_m"] = alt_error
                self.altitude["phase"] = phase
                if (
                    alt_error is not None
                    and math.isfinite(alt_error)
                    and abs(alt_error) >= self._warning_error_m
                ):
                    print(
                        "  [altitude] WARNING "
                        f"phase={phase} agl={agl:.2f}m "
                        f"target={self._target_alt_m:.2f}m err={alt_error:+.2f}m"
                    )
                scan = self._lidar.get_scan()
                if scan is not None:
                    sample.update(
                        {
                            "front_dist": scan.front_distance(),
                            "rear_dist": scan.rear_distance(),
                            "left_dist": scan.left_distance(),
                            "right_dist": scan.right_distance(),
                        }
                    )
                self._recorder.route_samples.append(sample)
            except Exception:
                pass

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval_s)
            except asyncio.TimeoutError:
                pass
