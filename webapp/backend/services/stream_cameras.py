"""Canonical stream camera flags accepted by launch_with_stream.sh.

The webapp droplist and SimService validation both read from this module so
new cameras are added in one place instead of parsing the shell script.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Optional


class StreamCamera(str, Enum):
    """Launcher flag stems (``--<value>``) for headless stream cameras."""

    FIXED = "fixed"
    DRONE_CAM = "drone_cam"
    DRONE_VIEW = "drone_view"


_STREAM_CAMERA_LABELS: dict[StreamCamera, str] = {
    StreamCamera.FIXED: "Fixed",
    StreamCamera.DRONE_CAM: "Drone Camera",
    StreamCamera.DRONE_VIEW: "Drone View",
}

# Underlying Gazebo model for each camera. World-mounted cameras use mono_cam*
# variants from the SDF; drone-mounted cameras use the drone or overlay model.
_STREAM_CAMERA_MODELS: dict[StreamCamera, str] = {
    StreamCamera.FIXED: "mono_cam_hd",
    StreamCamera.DRONE_CAM: "holybro_x500",
    StreamCamera.DRONE_VIEW: "drone_view_cam",
}


@dataclass
class StreamCameraInfo:
    """One selectable stream camera for the webapp droplist."""

    name: str
    label: str
    model: str


def list_stream_cameras() -> list[StreamCameraInfo]:
    """Return every stream camera, in launcher flag order."""
    return [
        StreamCameraInfo(
            name=cam.value,
            label=_STREAM_CAMERA_LABELS[cam],
            model=_STREAM_CAMERA_MODELS[cam],
        )
        for cam in StreamCamera
    ]


def stream_camera_names() -> list[str]:
    return [cam.value for cam in StreamCamera]


def is_stream_camera(name: Optional[str]) -> bool:
    if not name:
        return False
    try:
        StreamCamera(name)
        return True
    except ValueError:
        return False


def stream_camera_info_to_dict(info: StreamCameraInfo) -> dict:
    return asdict(info)
