"""Gazebo sensor suite -- the simulation backend.

This is the existing behaviour, moved behind the `SensorSuite` interface with
nothing changed: same discovery order, same timeouts, same log lines. The
simulation path must stay byte-identical, because it is the one that has
actually been flown.
"""
from __future__ import annotations

import os

from scarecrow.platform.base import (
    SensorSuite,
    TargetDispersalOutcome,
    WorldServices,
)
from scarecrow.sensors.camera.gazebo import GazeboCamera
from scarecrow.sensors.gz_entities import (
    BANISH_POSE,
    GzPx4FrameTransform,
    discover_model_name,
    discover_world_name,
    find_model_pose,
    get_world_model_poses,
    remove_nearest_model,
    teleport_model,
)
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.sensors.rangefinder.gazebo import GazeboRangefinder

DRONE_MODEL_CONTAINS = "holybro_x500"


def find_drone_camera_topic(topics: str) -> str | None:
    """Pick the drone's own camera from the Gazebo topic list.

    Must match the camera link *and* the drone model: worlds carry fixed
    monitoring cameras on the same link path, and pointing YOLO at one of those
    detects birds the drone cannot possibly reach.
    """
    return next(
        (
            line.strip()
            for line in topics.splitlines()
            if "camera_link/sensor/camera/image" in line
            and f"/model/{DRONE_MODEL_CONTAINS}" in line
        ),
        None,
    )


class GazeboWorldServices(WorldServices):
    """World truth and model removal via the `gz` CLI."""

    def __init__(self, suite: "GazeboSensorSuite", *, perches=()) -> None:
        self._suite = suite
        # Where a chased bird goes next, in order. Each entry is
        # (x, y, z, yaw_rad). After the last one it leaves the arena.
        self.perches = tuple(perches)
        self._dispersal_count = 0

    @property
    def name(self) -> str:
        return "gazebo"

    def calibrate_frame(self, *, local_x: float, local_y: float, local_yaw_deg: float):
        world = self._suite.world_name
        if not world:
            return None
        live_poses = get_world_model_poses(world_name=world, env=self._suite.env)
        gz_drone_pose = find_model_pose(
            live_poses,
            name=self._suite.drone_model_name,
            contains=DRONE_MODEL_CONTAINS,
        )
        if gz_drone_pose is None:
            print("  WARNING: live Gazebo drone pose not found; target removal will be skipped")
            return None

        transform = GzPx4FrameTransform(
            px4_origin_x=local_x,
            px4_origin_y=local_y,
            px4_origin_yaw_deg=local_yaw_deg,
            gz_origin_x=gz_drone_pose.x,
            gz_origin_y=gz_drone_pose.y,
            gz_origin_yaw_deg=gz_drone_pose.yaw_deg,
        )
        print(
            "  PX4/Gazebo frame calibrated: "
            f"px4=({transform.px4_origin_x:.2f},{transform.px4_origin_y:.2f},"
            f"{transform.px4_origin_yaw_deg:.1f}deg) "
            f"gz=({transform.gz_origin_x:.2f},{transform.gz_origin_y:.2f},"
            f"{transform.gz_origin_yaw_deg:.1f}deg) "
            f"yaw_offset={transform.yaw_offset_deg:.1f}deg"
        )
        return transform

    def disperse_target(
        self,
        *,
        x: float,
        y: float,
        name_prefixes: tuple[str, ...],
        uri_keywords: tuple[str, ...],
    ) -> TargetDispersalOutcome:
        """Chase the nearest target to its next destination.

        The bird is moved, never deleted -- deleting crashes gz-rendering 8.2.2
        (see gz_entities.teleport_model). Destinations come from
        ``self.perches`` in order; once they are exhausted the bird leaves the
        arena for good.
        """
        index = self._dispersal_count
        self._dispersal_count += 1

        if index < len(self.perches):
            px, py, pz, pyaw = self.perches[index]
            departed = False
        else:
            px, py, pz, pyaw = BANISH_POSE
            departed = True

        def action(*, world_name, model_name, env, timeout_ms):
            return teleport_model(
                world_name=world_name,
                model_name=model_name,
                x=px,
                y=py,
                z=pz,
                yaw_rad=pyaw,
                env=env,
                timeout_ms=timeout_ms,
            )

        result = remove_nearest_model(
            world_name=self._suite.world_name,
            x=x,
            y=y,
            env=self._suite.env,
            worlds_dir=os.path.join(self._suite.repo_root, "worlds"),
            model_names=None,
            name_prefixes=name_prefixes,
            uri_keywords=uri_keywords,
            max_distance_m=None,
            action=action,
        )
        return TargetDispersalOutcome(
            supported=True,
            success=result.success,
            message=result.message,
            model_name=result.model_name,
            world_name=result.world_name,
            distance_m=result.distance_m,
            departed=departed,
            destination=(px, py, pz),
        )


class GazeboSensorSuite(SensorSuite):
    """Sensors backed by Gazebo topics."""

    def __init__(self, *, repo_root: str, perches=()) -> None:
        self.repo_root = repo_root
        self.env: dict = {}
        self.topics: str = ""
        self.world_name: str | None = None
        self.drone_model_name: str = DRONE_MODEL_CONTAINS
        self._prefetch_thread = None
        self._prefetch_result = None
        self._lidar: GazeboLidar | None = None
        self._rangefinder: GazeboRangefinder | None = None
        self._camera: GazeboCamera | None = None
        self._world = GazeboWorldServices(self, perches=perches)

    @property
    def name(self) -> str:
        return "gazebo"

    @property
    def world(self) -> WorldServices:
        return self._world

    def prepare(self) -> None:
        """Start Gazebo env + topic discovery on a thread.

        Slow and independent of the MAVSDK connection, so it overlaps with it
        rather than adding seconds before every flight.
        """
        self._prefetch_thread, self._prefetch_result = prefetch_gz_env_async()

    def await_prepared(self, *, timeout_s: float = 10.0) -> None:
        if self._prefetch_thread is not None:
            self._prefetch_thread.join(timeout=timeout_s)
        self.env = (self._prefetch_result.env if self._prefetch_result else None) or {}
        self.topics = self._prefetch_result.topics if self._prefetch_result else ""

    def describe_environment(self) -> None:
        self.world_name = discover_world_name(self.topics)
        self.drone_model_name = (
            discover_model_name(self.topics, contains=DRONE_MODEL_CONTAINS)
            or DRONE_MODEL_CONTAINS
        )
        if self.world_name:
            print(f"  Gazebo world: {self.world_name}")
        else:
            print("  WARNING: Gazebo world name not found; target removal will be skipped")
        print(f"  Gazebo drone model: {self.drone_model_name}")

    def start_lidar(self) -> GazeboLidar:
        print("\nStarting 2D lidar...")
        self._lidar = GazeboLidar(env=self.env, num_threads=3)
        self._lidar._topic = self._lidar._discover_topic(topic_list=self.topics)
        self._lidar.start()
        print(f"  Lidar topic: {self._lidar.topic}")
        return self._lidar

    def start_ceiling_rangefinder(self) -> GazeboRangefinder:
        print("Starting upward ceiling rangefinder...")
        self._rangefinder = GazeboRangefinder(env=self.env)
        try:
            # Do not reuse the prefetched topic list here — the upward sensor
            # topic often appears a few seconds after the 2D lidar.
            self._rangefinder.start(discover_timeout_s=30.0)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}\n  Hint: confirm model://tf_luna_up is on the drone "
                "(gz topic -l | grep ceiling_rangefinder)"
            ) from exc
        print(f"  Ceiling topic: {self._rangefinder.topic}")
        return self._rangefinder

    def start_camera(self) -> GazeboCamera:
        cam_topic = find_drone_camera_topic(self.topics)
        if cam_topic is None:
            raise RuntimeError("drone camera topic not found")
        self._camera = GazeboCamera(topic=cam_topic, env=self.env)
        self._camera.start()
        print(f"  Camera topic: {self._camera.topic}")
        return self._camera

    def stop(self) -> None:
        if self._camera is not None:
            self._camera.stop()
        if self._rangefinder is not None:
            self._rangefinder.stop()
        if self._lidar is not None:
            self._lidar.stop()
