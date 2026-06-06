"""Unit tests for the canonical stream camera enum."""
from services.stream_cameras import (
    StreamCamera,
    is_stream_camera,
    list_stream_cameras,
    stream_camera_names,
)


def test_stream_camera_enum_values():
    assert [c.value for c in StreamCamera] == [
        "fixed", "center", "drone_cam", "drone_view",
    ]


def test_list_stream_cameras_returns_labels_and_models():
    cameras = list_stream_cameras()
    assert [c.name for c in cameras] == stream_camera_names()
    fixed = cameras[0]
    assert fixed.name == "fixed"
    assert fixed.label == "Fixed"
    assert fixed.model == "mono_cam_hd"
    assert cameras[-1].name == "drone_view"
    assert cameras[-1].label == "Drone View"


def test_is_stream_camera():
    assert is_stream_camera("fixed") is True
    assert is_stream_camera("drone_view") is True
    assert is_stream_camera("bogus") is False
    assert is_stream_camera(None) is False
