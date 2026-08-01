"""Pi Camera colour handling.

picamera2 delivers RGB; everything downstream (YOLO, OpenCV, the frame writer)
expects BGR, which is what Gazebo already provides. Getting this wrong is
silent -- detection accuracy drops and nothing logs an error -- so the
conversion is pure and tested.
"""
import numpy as np

from scarecrow.sensors.camera.picamera import PiCameraSource


def test_rgb_is_converted_to_bgr():
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[:, :, 0] = 10   # R
    rgb[:, :, 1] = 20   # G
    rgb[:, :, 2] = 30   # B

    bgr = PiCameraSource._to_bgr(rgb)

    assert bgr[0, 0, 0] == 30   # B first
    assert bgr[0, 0, 1] == 20   # G unchanged
    assert bgr[0, 0, 2] == 10   # R last


def test_conversion_returns_a_contiguous_copy():
    """A reversed view would alias the capture buffer the next frame overwrites."""
    rgb = np.arange(12, dtype=np.uint8).reshape(2, 2, 3)

    bgr = PiCameraSource._to_bgr(rgb)
    rgb[:] = 0

    assert bgr.any()
    assert bgr.flags["C_CONTIGUOUS"]


def test_matches_the_simulated_camera_geometry():
    """bbox-width range estimation in the entry planner is calibrated to this width."""
    camera = PiCameraSource()

    assert camera.topic.startswith("picamera3(1280x720")
