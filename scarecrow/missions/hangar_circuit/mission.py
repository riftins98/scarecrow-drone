"""The hangar circuit pursuit mission.

Flies a wall-following circuit of a hangar while watching for a pigeon. On a
confident detection it stops, plans an approach geometry from the image, yaws
onto the target, pursues it to a set distance, removes it from the world, then
returns to exactly where it broke off and resumes the leg.

STRUCTURE
This was one 1147-line `run()` whose phases communicated through ~20 mutable
locals and six nested closures. Each phase is now a method and the shared state
is on `self`, so a reader can follow one phase without holding the rest of the
mission in their head, and a phase can be tested by constructing the mission
with fakes.

Behaviour is deliberately unchanged, including every log line -- the webapp
parses them. See `scarecrow/missions/hangar_circuit/reporting.py`.
"""
from __future__ import annotations

import asyncio
import math
import os
import subprocess
import time
from enum import Enum

from scarecrow.controllers.corner_stabilizer import (
    approach_start_corner,
    stabilize_corner,
)
from scarecrow.controllers.point_navigator import fly_to_point
from scarecrow.controllers.pursuit import (
    PursuitEntryAction,
    TargetPursuitConfig,
    TargetPursuitResult,
)
from scarecrow.controllers.pursuit.entry_executor import (
    advance_left_wall_by_local_distance,
    rotate_to_yaw_until_target_observed,
    wait_for_fresh_target_observation,
)
from scarecrow.controllers.pursuit.entry_planner import (
    bbox_width_px,
    camera_bearing_deg,
    plan_from_observation,
)
from scarecrow.controllers.rotation import rotate_relative_90, rotate_to_yaw
from scarecrow.controllers.wall_follow import VelocityCommand
from scarecrow.detection.session import DetectionSession, TargetSuppressor
from scarecrow.detection.tracking import TargetTracker
from scarecrow.detection.yolo import YoloDetector
from scarecrow.drone import Drone
from scarecrow.flight.altitude import (
    DEFAULT_CEILING_CLEARANCE_M,
    altitude_hold_down_speed,
    target_alt_from_ceiling_distance,
)
from scarecrow.flight.landing import safe_land, wait_for_rangefinder
from scarecrow.missions.hangar_circuit.config import REPO_ROOT, HangarCircuitConfig
from scarecrow.missions.hangar_circuit.reporting import (
    LandingReporter,
    PursuitReporter,
    WallFollowReporter,
    report_planner_decision,
    report_search_status,
)
from scarecrow.navigation.arena import arena_boundary_from_start
from scarecrow.navigation.mission_recorder import MissionRecorder, RouteRecorder
from scarecrow.navigation.navigation_unit import NavigationUnit
from scarecrow.platform import SensorSuite, sensor_suite_for
from scarecrow.sensors.camera.base import CameraSource
from scarecrow.sensors.lidar.base import LidarSource
from scarecrow.sensors.lidar.validation import current_landing_targets, valid_distance
from scarecrow.sensors.rangefinder.base import RangefinderSource
from scarecrow.util.formatting import format_meters
from scarecrow.util.math_utils import normalize_angle


class LegOutcome(Enum):
    """What ended a circuit leg, and therefore what the mission does next."""

    CORNER_REACHED = "corner_reached"
    TARGET_HANDLED = "target_handled"
    CIRCUIT_COMPLETE = "circuit_complete"
    ABORT = "abort"


class HangarCircuitPursuitMission:
    """Orchestrates the hangar circuit pursuit flight."""

    def __init__(
        self,
        config: HangarCircuitConfig,
        *,
        sensors: SensorSuite | None = None,
    ) -> None:
        self.config = config
        # The suite is what makes this mission runnable on the real drone: it
        # supplies the sensors and hides whether they are Gazebo topics or
        # serial ports. Defaults to auto-detection so a caller that does not
        # care gets the right one.
        self.sensors: SensorSuite = sensors or sensor_suite_for(
            config.platform, repo_root=REPO_ROOT, perches=config.target_perches
        )

        self.drone = Drone(system_address=config.system_address)
        self.nav: NavigationUnit | None = None
        self.lidar: LidarSource | None = None
        self.camera: CameraSource | None = None
        self.ceiling_sensor: RangefinderSource | None = None
        self.session: DetectionSession | None = None
        self.detector: YoloDetector | None = None
        self.tracker = TargetTracker(image_width=config.image_width_px)

        # Mission state.
        self.recorder = MissionRecorder()
        self.route: RouteRecorder | None = None
        self.suppressor = TargetSuppressor()
        self.target_alt_m: float | None = None
        self.arena_boundary: list[dict] | None = None
        self.frame_transform = None
        self.pursuit_count = 0
        self.target_dispersal_event: dict | None = None

    # -- helpers --------------------------------------------------------

    @property
    def _altitude_ref(self) -> dict:
        """Live altitude reference for status lines, empty before takeoff."""
        return self.route.altitude if self.route is not None else {}

    def _set_phase(self, phase: str) -> None:
        if self.route is not None:
            self.route.set_phase(phase)

    # ==================================================================
    # Setup
    # ==================================================================

    def print_banner(self) -> None:
        cfg = self.config
        print("\n" + "=" * 64)
        print("  SCARECROW DRONE - HANGAR CIRCUIT PURSUIT")
        print("=" * 64)
        print(f"Flight ID:         {cfg.flight_id}")
        print(f"Output:            {cfg.output_dir}")
        if cfg.target_alt_m is None:
            print(
                "Takeoff altitude:  auto "
                f"(ceiling - {DEFAULT_CEILING_CLEARANCE_M:.1f}m)"
            )
        else:
            print(f"Takeoff altitude:  {cfg.target_alt_m:.2f}m AGL (manual)")
        print(f"Wall distance:     {cfg.wall_distance_m:.2f}m")
        print(f"Target distance:   {cfg.target_distance_m:.2f}m")
        print(f"Max legs:          {cfg.max_legs}")
        print("Camera recording:  disabled (live YOLO frames only)")
        if cfg.ceiling_clearance_m is not None:
            print(f"Min ceiling clear: {cfg.ceiling_clearance_m:.2f}m")

    def _build_detector(self):
        """Create the detector and start loading the YOLO model in background.

        Model loading is slow and independent of the MAVSDK connection, so it
        overlaps with it rather than adding seconds before every flight. The
        sensor suite warms up its own environment in parallel via prepare().
        """
        cfg = self.config
        self.detector = YoloDetector(
            model_path=cfg.yolo_model_path,
            output_dir=cfg.output_dir,
            confidence=cfg.scan_confidence,
            on_detection_data=self.tracker.update_from_yolo,
            target_classes=cfg.target_classes,
        )
        self.detector.configure_saving(save_detections=False, save_no_detections=False)
        return self.detector.preload_async()

    async def _connect(self) -> bool:
        print("\nConnecting to drone...")
        if not await self.drone.connect():
            print("ERROR: could not connect to drone")
            return False
        print("Connected.")

        await self.drone.set_ekf_origin()

        print("Waiting for position estimate...")
        if not await self.drone.wait_for_health():
            print("ERROR: position estimate timed out")
            return False
        print("Position OK.")

        print("\n--- Sensor verification ---")
        if not await self.drone.verify_gps_denied_params(verbose=True):
            print("Sensor config mismatch -- aborting")
            return False
        return True

    def _start_lidar(self) -> None:
        self.lidar = self.sensors.start_lidar()

    async def _start_ceiling_sensor(self) -> bool:
        """Bring up the upward rangefinder and wait for a first reading.

        Fatal on failure: the mission derives its flight altitude from this
        sensor, so continuing without it would fly at an unverified height
        under a ceiling.

        Started is not the same as publishing -- a Gazebo topic or a serial
        port can be open seconds before the first sample arrives, and reading
        too early looks identical to a missing sensor.
        """
        try:
            self.ceiling_sensor = self.sensors.start_ceiling_rangefinder()
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return False
        if not await wait_for_rangefinder(self.ceiling_sensor):
            print("ERROR: no upward rangefinder data -- aborting")
            return False
        return True

    def _resolve_target_altitude(self) -> bool:
        """Set the hold altitude from the ceiling sensor, or the manual value."""
        cfg = self.config
        ceiling_distance = self.ceiling_sensor.get_distance_m()
        if ceiling_distance is None:
            print("ERROR: no upward rangefinder distance for auto altitude -- aborting")
            return False

        if cfg.target_alt_m is None:
            try:
                self.target_alt_m = target_alt_from_ceiling_distance(ceiling_distance)
            except ValueError as exc:
                print(f"ERROR: cannot compute takeoff altitude: {exc}")
                return False
            print(
                "  Auto takeoff altitude: "
                f"ceiling={ceiling_distance:.2f}m - "
                f"clearance={DEFAULT_CEILING_CLEARANCE_M:.2f}m -> "
                f"{self.target_alt_m:.2f}m AGL"
            )
        else:
            if cfg.target_alt_m <= 0.0:
                print("ERROR: --target-alt must be greater than 0")
                return False
            self.target_alt_m = cfg.target_alt_m
            ceiling_margin = ceiling_distance - self.target_alt_m
            print(
                "  Manual takeoff altitude: "
                f"{self.target_alt_m:.2f}m AGL "
                f"(upward ceiling margin {ceiling_margin:.2f}m)"
            )
        return True

    async def _await_lidar_data(self) -> bool:
        for _ in range(30):
            await asyncio.sleep(0.1)
            scan = self.lidar.get_scan()
            if scan is not None:
                print(
                    f"  Lidar ready: rear={scan.rear_distance():.1f}m "
                    f"left={scan.left_distance():.1f}m "
                    f"front={scan.front_distance():.1f}m "
                    f"right={scan.right_distance():.1f}m"
                )
                return True
        print("ERROR: no lidar data -- aborting")
        return False

    async def _takeoff(self):
        print(f"\nSetting takeoff altitude to {self.target_alt_m:.2f}m...")
        takeoff_origin = await self.drone.prepare_takeoff(self.target_alt_m)

        print("Arming...")
        await self.drone.arm()
        print("Armed.")

        print(f"Taking off to {self.target_alt_m:.2f}m with PX4...")
        if not await self.drone.takeoff(altitude=self.target_alt_m):
            print("ERROR: takeoff failed")
            return None

        if not await self.drone.start_offboard():
            print("ERROR: offboard start failed")
            return None
        return takeoff_origin

    # ==================================================================
    # Phase 1: start corner
    # ==================================================================

    async def _approach_start(self) -> bool:
        cfg = self.config
        print("\n--- Phase 1: approach circuit start corner ---")
        start_side = await approach_start_corner(
            self.drone,
            self.lidar,
            wall_distance=cfg.wall_distance_m,
            target_alt_m=self.target_alt_m,
            start_side=cfg.start_side,
        )
        if start_side is None:
            print("ERROR: start stabilization failed. Landing safely.")
            return False

        # A right-hand start corner is legitimate but the circuit is written
        # for a left wall, so normalise by rotating left rather than teaching
        # every downstream phase about handedness.
        if start_side == "right":
            current_yaw = await self.drone.get_yaw()
            normalized_start_yaw = normalize_angle(current_yaw - 90.0)
            print(
                "  [hangar-circuit-start] right-side corner selected; "
                "rotating left to normalize left-wall scan "
                f"yaw={normalized_start_yaw:.1f}deg"
            )
            heading_result = await rotate_to_yaw(
                self.drone,
                normalized_start_yaw,
                timeout_s=cfg.rotate_timeout_s,
                tolerance_deg=cfg.rotate_tolerance_deg,
            )
            if not heading_result["ok"]:
                print("ERROR: start heading normalization failed. Landing safely.")
                return False
            print("  [hangar-circuit-start] stabilizing normalized rear-left corner")
            if not await stabilize_corner(
                self.drone,
                self.lidar,
                wall_distance=cfg.wall_distance_m,
                target_alt_m=self.target_alt_m,
            ):
                print("ERROR: normalized start stabilization failed. Landing safely.")
                return False
        return True

    async def _calibrate_frame_transform(self) -> None:
        """Tie the PX4 local frame to world coordinates, where that exists.

        Needed only to localise a reached target for removal. In simulation the
        world knows the drone's true pose; on hardware there is no such truth,
        the suite returns None, and the mission simply cannot remove targets --
        which is correct, because on a real drone the bird disperses by itself.
        """
        pos = await self.drone.get_position()
        yaw = await self.drone.get_yaw()
        self.frame_transform = self.sensors.world.calibrate_frame(
            local_x=pos.position.north_m,
            local_y=pos.position.east_m,
            local_yaw_deg=yaw,
        )

    async def _record_circuit_start(self) -> None:
        """Record the start pose and seed the arena boundary from it."""
        cfg = self.config
        pos = await self.drone.get_position()
        yaw = await self.drone.get_yaw()
        self.recorder.record_corner(pos.position.north_m, pos.position.east_m)
        self.recorder.add_event(
            {
                "type": "circuit_start",
                "label": "Circuit start",
                "x": pos.position.north_m,
                "y": pos.position.east_m,
                "yaw_deg": yaw,
                "timestamp": time.time(),
            }
        )

        scan = self.lidar.get_scan()
        if scan is not None:
            front_distance = scan.front_distance()
            right_distance = scan.right_distance()
            # Rear and left are the commanded stabilisation targets, so use
            # those rather than the measurement. Front and right are genuinely
            # unknown until measured, and fall back to the wall distance when
            # the reading is unusable.
            if not valid_distance(front_distance):
                front_distance = cfg.wall_distance_m
            if not valid_distance(right_distance):
                right_distance = cfg.wall_distance_m
            self.arena_boundary = arena_boundary_from_start(
                x=pos.position.north_m,
                y=pos.position.east_m,
                yaw_deg=yaw,
                rear_distance=cfg.wall_distance_m,
                left_distance=cfg.wall_distance_m,
                front_distance=front_distance,
                right_distance=right_distance,
            )
        await self.recorder.record_sample(self.drone, self.lidar)

    # ==================================================================
    # Phase 2: ceiling safety
    # ==================================================================

    def _ceiling_blocked_reason(self) -> str | None:
        """None when ceiling clearance is fine or unchecked; else the reason."""
        if self.config.ceiling_clearance_m is None:
            return None
        result = self.nav.check_ceiling_clearance(
            ceiling_sensor=self.ceiling_sensor,
            min_clearance_m=self.config.ceiling_clearance_m,
        )
        return None if result.done else result.reason

    def _check_ceiling_once(self) -> bool:
        if self.config.ceiling_clearance_m is None:
            return True
        print("\n--- Phase 2: ceiling safety check ---")
        result = self.nav.check_ceiling_clearance(
            ceiling_sensor=self.ceiling_sensor,
            min_clearance_m=self.config.ceiling_clearance_m,
        )
        if not result.done:
            print(f"  Ceiling safety check failed: {result.reason}")
            return False
        print(f"  Ceiling clearance safe: {result.clearance_m:.2f}m")
        return True

    # ==================================================================
    # Phase 4: pursuit
    # ==================================================================

    async def _pursue_once(self, leg: int, attempt: int) -> TargetPursuitResult:
        """Run one pursuit attempt to the configured target distance."""
        cfg = self.config
        self.target_dispersal_event = None
        self.pursuit_count += 1
        pursuit_label = (
            f"leg{leg:02d}_Pursuit{self.pursuit_count:02d}_attermpt_{attempt:02d}"
        )
        self._set_phase("pursuit")
        print(
            f"\n--- Phase 4: pursue pigeon to {cfg.target_distance_m:.2f}m "
            f"(attempt {attempt}/{cfg.max_pursuit_attempts}) ---"
        )
        self.session.use_pursuit_confidence()
        self.session.configure_capture(pursuit_label)
        self.session.capture_next(f"{pursuit_label}_start")
        print(
            f"  Detection threshold: {cfg.pursuit_confidence:.0%} "
            "for pursuit/relocalization"
        )

        reporter = PursuitReporter(
            self.session,
            pursuit_label=pursuit_label,
            altitude_ref=self._altitude_ref,
        )
        pursuit_result = await self.nav.pursue_target(
            tracker=self.tracker,
            config=TargetPursuitConfig(
                target_distance_m=cfg.target_distance_m,
                max_forward_speed_m_s=0.40,
                min_forward_speed_m_s=0.10,
                kp_forward=0.40,
                yaw_kp=22.0,
                max_yaw_speed_deg_s=32.0,
                vertical_kp=0.50,
                max_vertical_speed_m_s=0.32,
                pursuit_timeout_s=cfg.pursuit_timeout_s,
                center_enter_ratio=0.50,
                center_exit_ratio=0.60,
                vertical_center_enter_ratio=0.10,
                vertical_center_exit_ratio=0.16,
                detection_miss_timeout_s=2.5,
                detection_miss_count_required=3,
            ),
            on_status=reporter,
            on_search_status=report_search_status,
        )

        if not pursuit_result.reached_target:
            print(f"  Pursuit ended without reaching target: {pursuit_result.reason}")
            await self.recorder.record_pose_event(
                self.drone,
                event_type="pursuit_attempt_failed",
                label=(
                    f"Pursuit attempt {attempt}/{cfg.max_pursuit_attempts} "
                    f"failed on leg {leg}"
                ),
                leg=leg,
                reason=pursuit_result.reason,
                attempt=attempt,
                max_attempts=cfg.max_pursuit_attempts,
                success=False,
            )
            return pursuit_result

        print(
            "  Target reached at "
            f"{pursuit_result.front_distance_m:.2f}m. "
            f"Hovering {cfg.hover_seconds:.1f}s."
        )
        self.session.capture_next(f"{pursuit_label}_reached")

        target_pos = await self.drone.get_position()
        target_yaw = await self.drone.get_yaw()
        if self.frame_transform is not None:
            world_x, world_y = self.frame_transform.estimate_target_gz_xy(
                local_x=target_pos.position.north_m,
                local_y=target_pos.position.east_m,
                yaw_deg=target_yaw,
                range_m=pursuit_result.front_distance_m,
            )
            self.target_dispersal_event = {
                "x": world_x,
                "y": world_y,
                "local_x": target_pos.position.north_m,
                "local_y": target_pos.position.east_m,
                "yaw_deg": target_yaw,
                "range_m": pursuit_result.front_distance_m,
                "leg": leg,
            }

        self.recorder.add_event(
            {
                "type": "target_reached",
                "label": f"Target reached at {cfg.target_distance_m:.2f}m",
                "x": target_pos.position.north_m,
                "y": target_pos.position.east_m,
                "yaw_deg": target_yaw,
                "distance_m": pursuit_result.front_distance_m,
                "success": True,
                "attempt": attempt,
                "timestamp": time.time(),
                "leg": leg,
            }
        )
        await self.nav.hover(cfg.hover_seconds)
        return pursuit_result

    def _disperse_reached_target(self) -> None:
        """Chase the reached target to its next destination.

        Four distinct outcomes, logged differently on purpose:
          - no frame transform -> we never knew where the target was
          - unsupported        -> hardware; the bird leaves by itself
          - moved              -> it relocated to another perch
          - departed           -> it left the arena for good
        """
        if self.target_dispersal_event is None:
            print("  WARNING: target dispersal skipped: PX4/Gazebo frame transform unavailable")
            return

        event = self.target_dispersal_event
        outcome = self.sensors.world.disperse_target(
            x=float(event["x"]),
            y=float(event["y"]),
            name_prefixes=self.config.target_model_prefixes,
            uri_keywords=self.config.target_uri_keywords,
        )
        self.recorder.add_event(
            {
                "type": "target_dispersed",
                "label": (
                    "Target left the arena" if outcome.departed else "Target moved to another perch"
                ),
                "supported": outcome.supported,
                "success": outcome.success,
                "departed": outcome.departed,
                "destination": outcome.destination,
                "world": outcome.world_name,
                "model": outcome.model_name,
                "distance_m": outcome.distance_m,
                "target_estimate_x": event["x"],
                "target_estimate_y": event["y"],
                "target_local_x": event["local_x"],
                "target_local_y": event["local_y"],
                "target_range_m": event["range_m"],
                "message": outcome.message,
                "timestamp": time.time(),
                "leg": event["leg"],
            }
        )
        if not outcome.supported:
            print(f"  Target dispersed ({outcome.message})")
        elif not outcome.success:
            print(f"  WARNING: target dispersal failed: {outcome.message}")
        elif outcome.departed:
            print(f"  Target {outcome.model_name!r} left the arena for good")
        else:
            dx, dy, dz = outcome.destination
            print(
                f"  Target {outcome.model_name!r} moved to another perch "
                f"({dx:.2f},{dy:.2f},{dz:.2f}) -- it will be found again"
            )

    # ==================================================================
    # Phases 5-6: return to entry
    # ==================================================================

    async def _return_to_pursuit_entry(
        self, entry_point: dict, leg: int, attempt: int, outcome: str
    ) -> tuple[dict, dict] | None:
        """Fly back to the pursuit entry pose and restore its heading.

        None means the drone could not get back, which is terminal for the
        mission -- it no longer knows where on the circuit it is.
        """
        cfg = self.config
        print("\n--- Phase 5: return to pursuit entry ---")
        self._set_phase("return_entry")
        entry_return_result = await fly_to_point(
            self.drone, self.lidar, entry_point, label="return-entry"
        )
        self.recorder.add_event(
            {
                "type": "pursuit_entry_returned",
                "label": f"Returned to pursuit entry on leg {leg}",
                "target_x": entry_point["x"],
                "target_y": entry_point["y"],
                "target_yaw_deg": entry_point["yaw_deg"],
                "x": entry_return_result["x"],
                "y": entry_return_result["y"],
                "yaw_deg": entry_return_result["yaw_deg"],
                "position_error_m": entry_return_result["error_m"],
                "return_ok": entry_return_result["ok"],
                "return_reason": entry_return_result["reason"],
                "elapsed_s": entry_return_result["elapsed_s"],
                "attempt": attempt,
                "outcome": outcome,
                "timestamp": time.time(),
                "leg": leg,
            }
        )
        if not entry_return_result["ok"]:
            print("  WARNING: could not return to pursuit entry; landing at current position")
            return None

        print("\n--- Phase 6: restore pre-pursuit heading ---")
        self._set_phase("restore_heading")
        heading_result = await rotate_to_yaw(
            self.drone,
            float(entry_point["yaw_deg"]),
            timeout_s=cfg.rotate_timeout_s,
            tolerance_deg=cfg.rotate_tolerance_deg,
        )
        self.recorder.add_event(
            {
                "type": "pursuit_heading_restored",
                "label": f"Restored pursuit entry heading on leg {leg}",
                "x": entry_return_result["x"],
                "y": entry_return_result["y"],
                "yaw_deg": heading_result["yaw_deg"],
                "target_yaw_deg": heading_result["target_yaw_deg"],
                "yaw_error_deg": heading_result["yaw_error_deg"],
                "heading_ok": heading_result["ok"],
                "heading_reason": heading_result["reason"],
                "elapsed_s": heading_result["elapsed_s"],
                "attempt": attempt,
                "outcome": outcome,
                "timestamp": time.time(),
                "leg": leg,
            }
        )
        # A heading that did not fully restore is survivable: the wall-follow
        # controller re-aligns to the wall within a few metres.
        if not heading_result["ok"]:
            print("  WARNING: heading restore timed out; resuming scan from current heading")
        return entry_return_result, heading_result

    # ==================================================================
    # Pursuit entry planning
    # ==================================================================

    async def _plan_pursuit_entry(self, leg: int, leg_start_yaw: float):
        """Decide whether the geometry supports a pursuit, and set it up.

        Returns the planner decision on success, or None when the mission
        should suppress this target and resume scanning.

        The planner exists because pursuing from wherever the target happened
        to be spotted usually fails: the bird is off to the side, and turning
        to face it puts the drone's flank into a wall.
        """
        cfg = self.config
        self._set_phase("pursuit_entry_planner")

        observation = self.tracker.latest(max_age_s=2.5)
        if observation is None:
            self.suppressor.suppress()
            print(
                "  [planner] not entering pursuit: "
                "reason=no_fresh_target_observation max_age=2.5s"
            )
            return None

        decision = plan_from_observation(observation, cfg.entry_planner)
        report_planner_decision(decision, advance_scale=cfg.entry_advance_scale)

        if decision.action == PursuitEntryAction.REJECT:
            self.suppressor.suppress()
            print(
                "  [planner] not entering pursuit: "
                f"reason=planner_reject:{decision.reason} "
                f"bbox_w={decision.bbox_width_px:.0f}px "
                f"bearing={decision.camera_bearing_deg:+.1f}deg "
                f"range_est={format_meters(decision.range_estimate_m)} "
                f"side_est={format_meters(decision.side_estimate_m)} "
                f"required_advance={format_meters(decision.required_advance_m)}"
            )
            return None

        if decision.action == PursuitEntryAction.ADVANCE:
            if not await self._advance_to_entry(decision, leg_start_yaw):
                return None
        else:
            print("  [planner] target already has sufficient entry bearing")
        return decision

    async def _advance_to_entry(self, decision, leg_start_yaw: float) -> bool:
        """Move along the wall so the target sits at a workable bearing."""
        cfg = self.config
        advance_m = decision.advance_m
        self.session.use_scan_confidence()
        self.session.clear_tracker()

        print("  [planner] restoring wall-follow heading")
        heading_result = await rotate_to_yaw(
            self.drone,
            leg_start_yaw,
            timeout_s=cfg.rotate_timeout_s,
            tolerance_deg=cfg.rotate_tolerance_deg,
        )
        if not heading_result["ok"]:
            print("  WARNING: planner heading restore timed out")

        self._set_phase("pursuit_entry_advance")
        print(
            "  [planner] advancing along wall "
            f"{advance_m:.1f}m before original pursuit"
        )
        advance_reason, advanced_m = await advance_left_wall_by_local_distance(
            self.drone,
            self.lidar,
            advance_m,
            cfg.wall_distance_m,
            self.target_alt_m,
            heading_yaw_deg=leg_start_yaw,
            timeout_s=cfg.planner_advance_timeout_s,
            forward_speed=cfg.wall_follow_speed_m_s,
            wall_follow_kp=cfg.wall_follow_kp,
            wall_follow_kd=cfg.wall_follow_kd,
            wall_follow_max_lateral=cfg.wall_follow_max_lateral_m_s,
            wall_follow_yaw_kp=cfg.wall_follow_yaw_kp,
            wall_follow_max_yaw=cfg.wall_follow_max_yaw_deg_s,
            altitude_down_speed_fn=altitude_hold_down_speed,
        )
        print(
            f"  [planner] advance ended: {advance_reason} "
            f"(advanced={advanced_m:.2f}m)"
        )
        self.session.clear_tracker()

        if advance_reason == "distance_reached":
            return True

        # Hitting the front wall means the room ran out before the geometry
        # became workable -- the target is simply not reachable from this leg.
        reason = (
            "entry_advance_front_wall"
            if advance_reason == "front_wall"
            else f"entry_advance_{advance_reason}"
        )
        print(
            f"  [planner] not entering pursuit: reason={reason} "
            f"advanced={advanced_m:.2f}m required={advance_m:.2f}m"
        )
        return False

    async def _acquire_target_for_pursuit(self, decision, leg_start_yaw: float):
        """Yaw onto the planned view and confirm the target is still usable."""
        cfg = self.config
        self.session.use_pursuit_confidence()
        self.session.configure_capture(None)
        self.session.clear_tracker()
        self.session.set_enabled(True, "planner entry-yaw detection")
        # Let a frame or two arrive at the new threshold before rotating.
        await asyncio.sleep(0.30)

        observation = None
        entry_yaw_delta_deg = decision.entry_yaw_delta_deg
        if math.isfinite(entry_yaw_delta_deg):
            planned_entry_yaw_deg = normalize_angle(leg_start_yaw + entry_yaw_delta_deg)
            self._set_phase("pursuit_entry_yaw")
            print(
                "  [planner] rotating slowly to planned pursuit view "
                f"yaw={planned_entry_yaw_deg:.1f}deg "
                f"(delta={entry_yaw_delta_deg:+.1f}deg, "
                f"speed={cfg.planner_entry_yaw_speed_deg_s:.1f}deg/s)"
            )
            try:
                heading_result = await rotate_to_yaw_until_target_observed(
                    self.drone,
                    self.tracker,
                    planned_entry_yaw_deg,
                    timeout_s=cfg.rotate_timeout_s,
                    tolerance_deg=cfg.rotate_tolerance_deg,
                    max_yaw_speed_deg_s=cfg.planner_entry_yaw_speed_deg_s,
                    min_yaw_speed_deg_s=cfg.planner_entry_yaw_min_speed_deg_s,
                    centered_bearing_deg=cfg.planner_entry_yaw_center_bearing_deg,
                )
            except Exception as exc:
                await self.drone.set_velocity(VelocityCommand())
                self.session.set_enabled(False, "planner entry-yaw error")
                self.suppressor.suppress()
                print(
                    "  [planner] entry-yaw detection failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                return None

            observation = heading_result.get("observation")
            if observation is not None:
                print(
                    "  [planner] target usable during entry yaw "
                    f"yaw={heading_result['yaw_deg']:.1f}deg "
                    f"target={planned_entry_yaw_deg:.1f}deg "
                    f"bearing={heading_result.get('target_bearing_deg', math.nan):+.1f}deg"
                )
            elif not heading_result["ok"]:
                print("  WARNING: planner entry yaw rotation timed out")
            else:
                print(
                    "  [planner] planned yaw reached without target; "
                    "waiting for post-yaw frames"
                )
        else:
            print("  WARNING: planner entry yaw unavailable; starting pursuit at current heading")

        if observation is None:
            print(
                "  [planner] waiting for post-yaw target detection "
                f"({cfg.planner_reacquire_timeout_s:.1f}s)"
            )
            observation = await wait_for_fresh_target_observation(
                self.tracker,
                timeout_s=cfg.planner_reacquire_timeout_s,
                centered_bearing_deg=cfg.planner_entry_yaw_center_bearing_deg,
            )

        if observation is None:
            self.session.set_enabled(False, "planner post-yaw target not usable")
            self.suppressor.suppress()
            print(
                "  [planner] not entering pursuit: "
                "reason=post_yaw_target_not_usable "
                f"timeout={cfg.planner_reacquire_timeout_s:.1f}s "
                f"max_bearing={cfg.planner_entry_yaw_center_bearing_deg:.1f}deg"
            )
            return None

        print(
            "  [planner] post-yaw target usable: "
            f"conf={observation.confidence:.0%} "
            f"bearing={camera_bearing_deg(observation):+.1f}deg "
            f"bbox_w={bbox_width_px(observation):.0f}px"
        )
        return observation

    # ==================================================================
    # Phase 3: the circuit
    # ==================================================================

    async def _handle_target_detection(self, leg: int, leg_start_yaw: float) -> LegOutcome:
        """Plan, pursue (with retries), return to entry, resume the leg."""
        cfg = self.config
        await self.recorder.drain_pending()
        self.session.set_enabled(False, "target acquired; planning pursuit entry")

        decision = await self._plan_pursuit_entry(leg, leg_start_yaw)
        if decision is None:
            self._set_phase("wall_follow")
            return LegOutcome.TARGET_HANDLED

        if await self._acquire_target_for_pursuit(decision, leg_start_yaw) is None:
            self._set_phase("wall_follow")
            return LegOutcome.TARGET_HANDLED

        entry_point = await self.recorder.record_pose_event(
            self.drone,
            event_type="pursuit_entry",
            label=f"Pursuit entry on leg {leg}",
            leg=leg,
        )
        print(
            "  Pursuit entry recorded: "
            f"x={entry_point['x']:.2f} y={entry_point['y']:.2f} "
            f"yaw={entry_point['yaw_deg']:.1f}"
        )

        final_return = None
        final_heading = None
        final_pursuit = None
        pursuit_success = False

        for attempt in range(1, cfg.max_pursuit_attempts + 1):
            self.session.set_enabled(True, f"pursuit attempt {attempt}")
            pursuit_result = await self._pursue_once(leg, attempt)
            final_pursuit = pursuit_result
            self.session.set_enabled(False, "return to pursuit entry")

            if pursuit_result.reached_target:
                self._disperse_reached_target()

            await self.drone.set_velocity(VelocityCommand())
            returned = await self._return_to_pursuit_entry(
                entry_point, leg, attempt, pursuit_result.reason
            )
            if returned is None:
                return LegOutcome.ABORT
            final_return, final_heading = returned

            if pursuit_result.reached_target:
                pursuit_success = True
                break

            if attempt < cfg.max_pursuit_attempts:
                print(
                    "  Pursuit attempt "
                    f"{attempt}/{cfg.max_pursuit_attempts} failed "
                    f"({pursuit_result.reason}); retrying from pursuit entry."
                )
            else:
                print(
                    "  Pursuit failed after "
                    f"{cfg.max_pursuit_attempts} attempts ({pursuit_result.reason}); "
                    "resuming leg scan."
                )
                # Suppress so the resumed scan does not immediately re-trigger
                # on the same unreachable bird.
                self.suppressor.suppress()
                self.recorder.add_event(
                    {
                        "type": "pursuit_failed",
                        "label": f"Pursuit failed on leg {leg}",
                        "x": final_return["x"],
                        "y": final_return["y"],
                        "yaw_deg": final_heading["yaw_deg"],
                        "reason": pursuit_result.reason,
                        "attempts": cfg.max_pursuit_attempts,
                        "success": False,
                        "timestamp": time.time(),
                        "leg": leg,
                    }
                )
                print("  Failed target will be ignored until it is no longer visible.")

        if final_return is None or final_heading is None:
            return LegOutcome.ABORT

        print("\n--- Phase 7: resume interrupted leg scan ---")
        self._set_phase("wall_follow")
        self.recorder.add_event(
            {
                "type": "scan_resumed",
                "label": f"Resumed scan on leg {leg} after pursuit",
                "x": final_return["x"],
                "y": final_return["y"],
                "yaw_deg": final_heading["yaw_deg"],
                "pursuit_success": pursuit_success,
                "pursuit_reason": None if final_pursuit is None else final_pursuit.reason,
                "timestamp": time.time(),
                "leg": leg,
            }
        )
        return LegOutcome.TARGET_HANDLED

    async def _fly_leg(self, leg: int) -> LegOutcome:
        """Follow the left wall watching for a target, until a corner or a bird."""
        cfg = self.config
        self._set_phase("wall_follow")
        print(f"\n--- Leg {leg}/{cfg.max_legs}: follow left wall and watch for pigeon ---")

        leg_start_pos = await self.drone.get_position()
        leg_start_yaw = await self.drone.get_yaw()
        leg_start_point = {
            "type": "leg_start",
            "label": f"Leg {leg} start",
            "x": leg_start_pos.position.north_m,
            "y": leg_start_pos.position.east_m,
            "yaw_deg": leg_start_yaw,
            "timestamp": time.time(),
            "leg": leg,
        }
        self.recorder.record_corner(leg_start_point["x"], leg_start_point["y"])
        self.recorder.add_event(leg_start_point)

        self.session.use_scan_confidence()
        self.session.configure_capture(None)
        self.session.capture_next(
            f"leg{leg:02d}_Pursuit{self.pursuit_count + 1:02d}_attermpt_01_trigger"
        )
        print(f"  Detection threshold: {cfg.scan_confidence:.0%} for wall-follow trigger")
        self.session.clear_tracker()
        self.session.set_enabled(True, "wall-follow leg")

        stop_reason = "target_detected"

        def stop_condition() -> bool:
            nonlocal stop_reason
            now = time.time()
            latest_target = self.tracker.latest(max_age_s=1.5, now=now)
            if self.suppressor.active:
                self.suppressor.update(
                    latest_target is not None,
                    confidence=None if latest_target is None else latest_target.confidence,
                    now=now,
                )
            elif latest_target is not None:
                stop_reason = "target_detected"
                print(
                    "  [target candidate] acquired "
                    f"confidence={latest_target.confidence:.0%}; "
                    "stopping XY for pre-pursuit planner"
                )
                return True

            safety_reason = self._ceiling_blocked_reason()
            if safety_reason is not None:
                stop_reason = safety_reason
                return True
            return False

        wall_result = await self.nav.wall_follow_until(
            side="left",
            target_distance=cfg.wall_distance_m,
            forward_speed=cfg.wall_follow_speed_m_s,
            front_stop_distance=cfg.wall_distance_m,
            timeout=cfg.leg_timeout_s,
            stop_condition=stop_condition,
            on_status=WallFollowReporter(
                leg=leg,
                recorder=self.recorder,
                drone=self.drone,
                lidar=self.lidar,
                altitude_ref=self._altitude_ref,
                record_every=cfg.map_record_every,
            ),
            kp=cfg.wall_follow_kp,
            kd=cfg.wall_follow_kd,
            max_lateral_speed=cfg.wall_follow_max_lateral_m_s,
            yaw_kp=cfg.wall_follow_yaw_kp,
            max_yaw_speed=cfg.wall_follow_max_yaw_deg_s,
            target_alt_m=self.target_alt_m,
            altitude_kp=cfg.altitude_hold_kp,
            altitude_tolerance_m=cfg.altitude_hold_tolerance_m,
            max_vertical_speed_m_s=cfg.altitude_hold_max_down_speed_m_s,
        )
        print(
            f"  Leg {leg} ended: {wall_result.reason} "
            f"(left={format_meters(wall_result.wall_distance_m)}, "
            f"front={format_meters(wall_result.front_distance_m)}, "
            f"raw_front={format_meters(wall_result.raw_front_distance_m)})"
        )

        if wall_result.reason == "interrupted":
            if stop_reason == "target_detected":
                return await self._handle_target_detection(leg, leg_start_yaw)
            print(f"  Stopped for safety: {stop_reason}. Landing safely.")
            return LegOutcome.ABORT

        if wall_result.reason != "front_wall":
            print(f"  Leg did not reach a corner ({wall_result.reason}). Landing safely.")
            return LegOutcome.ABORT

        return await self._turn_corner(leg)

    async def _turn_corner(self, leg: int) -> LegOutcome:
        cfg = self.config
        self.session.set_enabled(False, "corner turn/stabilization")
        self._set_phase("corner_turn")
        turn_label = "final right turn" if leg == cfg.max_legs else "right turn"
        print(f"  Turning {turn_label}...")
        if not await rotate_relative_90(self.drone, self.lidar, 90.0):
            print("  ERROR: rotation failed. Landing safely.")
            return LegOutcome.ABORT

        print("  Stabilizing corner...")
        if not await stabilize_corner(
            self.drone,
            self.lidar,
            wall_distance=cfg.wall_distance_m,
            target_alt_m=self.target_alt_m,
        ):
            print("  WARNING: corner stabilization timed out -- continuing")

        if leg == cfg.max_legs:
            print("\n--- Full circuit completed after final turn. Landing safely. ---")
            return LegOutcome.CIRCUIT_COMPLETE
        return LegOutcome.CORNER_REACHED

    # ==================================================================
    # Teardown
    # ==================================================================

    async def _land(self) -> None:
        """Land, preferring the lidar-held descent, always reaching a disarm."""
        if not self.drone.is_armed:
            return
        try:
            if self.nav is None:
                await safe_land(self.drone)
                return

            self._set_phase("landing")
            print("\nLanding with lidar hold...")
            result = await self.nav.land_with_lidar_hold(
                targets=current_landing_targets(
                    self.lidar, fallback_wall_distance=self.config.wall_distance_m
                ),
                stabilize_first=False,
                on_status=LandingReporter(),
            )
            # The lidar landing can touch down without disarming; finish the
            # job rather than leaving the drone armed on the ground.
            if not result.disarmed and self.drone.is_armed:
                await safe_land(self.drone)
        except Exception as exc:
            print(f"[SAFETY] landing cleanup failed: {exc}")
            try:
                await asyncio.wait_for(self.drone.disarm(), timeout=5.0)
            except Exception:
                pass

    def _stop_sensors(self) -> None:
        """Stop every sensor. The suite owns them, so it does the shutdown."""
        self.sensors.stop()

    # ==================================================================
    # Entry point
    # ==================================================================

    async def run(self) -> None:
        cfg = self.config
        os.makedirs(cfg.output_dir, exist_ok=True)
        self.print_banner()

        # A leftover mavsdk_server from a crashed run squats on udp 14540 and
        # this flight would never connect.
        subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)

        yolo_thread = self._build_detector()
        # Environment discovery runs alongside the MAVSDK connect. In
        # simulation that is Gazebo topic enumeration; on hardware it is a
        # no-op, so the same call is correct on both.
        self.sensors.prepare()

        try:
            if not await self._connect():
                return

            yolo_thread.join(timeout=30)
            self.sensors.await_prepared(timeout_s=10.0)
            self.sensors.describe_environment()

            self._start_lidar()
            if not await self._start_ceiling_sensor():
                return
            if not self._resolve_target_altitude():
                return
            if not await self._await_lidar_data():
                return

            takeoff_origin = await self._takeoff()
            if takeoff_origin is None:
                return

            self.nav = NavigationUnit(self.drone, self.lidar)

            if not await self._approach_start():
                return

            self.recorder.start()
            self.route = RouteRecorder(
                self.drone,
                self.lidar,
                self.recorder,
                interval_s=cfg.route_sample_interval_s,
                target_alt_m=self.target_alt_m,
                warning_error_m=cfg.altitude_warning_error_m,
            )
            self.route.start()
            self.recorder.set_takeoff_point(
                takeoff_origin.position.north_m,
                takeoff_origin.position.east_m,
            )

            await self._calibrate_frame_transform()
            await self._record_circuit_start()

            if not self._check_ceiling_once():
                return

            try:
                self.camera = self.sensors.start_camera()
            except RuntimeError as exc:
                print(f"ERROR: {exc}")
                return

            self.session = DetectionSession(
                self.camera,
                self.detector,
                self.tracker,
                scan_confidence=cfg.scan_confidence,
                pursuit_confidence=cfg.pursuit_confidence,
            )

            print("\n--- Phase 3: circuit wall-follow with detection ---")
            leg = 1
            while leg <= cfg.max_legs:
                outcome = await self._fly_leg(leg)
                if outcome in (LegOutcome.ABORT, LegOutcome.CIRCUIT_COMPLETE):
                    return
                if outcome == LegOutcome.CORNER_REACHED:
                    leg += 1
                # TARGET_HANDLED resumes the same leg.

        finally:
            if self.session is not None:
                self.session.stop()
            elif self.detector is not None:
                self.detector.stop()
            await self._land()
            if self.route is not None:
                await self.route.stop()
            if not self.recorder.saved and self.recorder.has_content:
                await self.recorder.save(
                    cfg.output_dir,
                    wall_distance=cfg.wall_distance_m,
                    boundary_override=self.arena_boundary,
                )
            self._stop_sensors()

        print("\nHangar circuit pursuit complete.")
