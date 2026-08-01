"""Hardware sensor suite -- the real drone on a Raspberry Pi.

Same physical sensors the simulation models:

    2D lidar          RPLidar A1M8      USB serial   (/dev/ttyUSB0)
    Up rangefinder    TF-Luna           UART         (/dev/serial0)
    Camera            Pi Camera 3       CSI          (picamera2)
    Optical flow      MTF-01            -> PX4 directly, never read here

Optical flow and the downward rangefinder are wired into PX4 and feed its EKF;
the flight code consumes their effect through position and velocity estimates,
which is why there is no driver for them here. That is true in simulation too,
so nothing changes between environments.

WHAT IS NOT SUPPORTED, HONESTLY
There is no world model to query or edit. `calibrate_frame` returns None and
`remove_target` reports `supported=False`. On a real drone a reached pigeon
disperses on its own -- the deterrence is the point, and there is nothing to
delete. The mission logs that outcome differently from a failed removal,
because only the latter is a fault.
"""
from __future__ import annotations

from scarecrow.platform.base import SensorSuite, TargetRemovalOutcome, WorldServices
from scarecrow.sensors.camera.base import CameraSource
from scarecrow.sensors.camera.picamera import PiCameraSource
from scarecrow.sensors.lidar.base import LidarSource
from scarecrow.sensors.lidar.rplidar import RPLidarSource
from scarecrow.sensors.rangefinder.base import RangefinderSource
from scarecrow.sensors.rangefinder.tfluna import TFLunaRangefinder

DEFAULT_LIDAR_PORT = "/dev/ttyUSB0"
DEFAULT_RANGEFINDER_PORT = "/dev/serial0"

# The TF-Luna publishes at 100Hz once powered, so a reading should appear
# almost immediately. A long wait here means it is unwired, not merely slow.
RANGEFINDER_WARMUP_TIMEOUT_S = 5.0


class NoWorldServices(WorldServices):
    """Stand-in for capabilities that exist only in a simulator."""

    @property
    def name(self) -> str:
        return "hardware"

    def calibrate_frame(self, *, local_x: float, local_y: float, local_yaw_deg: float):
        # No external truth on hardware. PX4's local frame is the only frame,
        # so there is nothing to calibrate against and nothing to report.
        return None

    def remove_target(
        self,
        *,
        x: float,
        y: float,
        name_prefixes: tuple[str, ...],
        uri_keywords: tuple[str, ...],
    ) -> TargetRemovalOutcome:
        return TargetRemovalOutcome(
            supported=False,
            success=False,
            message="target removal is simulation-only; on hardware the target disperses",
        )


class HardwareSensorSuite(SensorSuite):
    """Sensors on the physical drone."""

    def __init__(
        self,
        *,
        lidar_port: str = DEFAULT_LIDAR_PORT,
        rangefinder_port: str = DEFAULT_RANGEFINDER_PORT,
        camera_width: int = 1280,
        camera_height: int = 720,
        camera_fps: int = 15,
    ) -> None:
        self._lidar_port = lidar_port
        self._rangefinder_port = rangefinder_port
        self._camera_width = camera_width
        self._camera_height = camera_height
        self._camera_fps = camera_fps
        self._lidar: RPLidarSource | None = None
        self._rangefinder: TFLunaRangefinder | None = None
        self._camera: PiCameraSource | None = None
        self._world = NoWorldServices()

    @property
    def name(self) -> str:
        return "hardware"

    @property
    def world(self) -> WorldServices:
        return self._world

    def describe_environment(self) -> None:
        print("  Platform: hardware (Raspberry Pi)")
        print(f"  Lidar port: {self._lidar_port}")
        print(f"  Rangefinder port: {self._rangefinder_port}")
        print("  Target removal: not applicable on hardware")

    def start_lidar(self) -> LidarSource:
        print("\nStarting 2D lidar...")
        self._lidar = RPLidarSource(port=self._lidar_port)
        try:
            self._lidar.start()
        except Exception as exc:
            raise RuntimeError(
                f"could not start RPLidar on {self._lidar_port}: {exc}. "
                "Check the USB adapter is connected and the user is in the "
                "'dialout' group."
            ) from exc
        print(f"  Lidar topic: {self._lidar_port}")
        return self._lidar

    def start_ceiling_rangefinder(self) -> RangefinderSource:
        print("Starting upward ceiling rangefinder...")
        self._rangefinder = TFLunaRangefinder(port=self._rangefinder_port)
        try:
            self._rangefinder.start()
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}\n  Hint: confirm the upward TF-Luna is wired to the Pi "
                "UART and the serial console is disabled (raspi-config)."
            ) from exc
        print(f"  Ceiling topic: {self._rangefinder.topic}")
        return self._rangefinder

    def start_camera(self) -> CameraSource:
        self._camera = PiCameraSource(
            width=self._camera_width,
            height=self._camera_height,
            fps=self._camera_fps,
        )
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
