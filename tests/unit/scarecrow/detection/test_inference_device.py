"""Inference device selection.

YOLO ran on the CPU while an idle GPU sat next to it. Measured on this
machine with yolov8s at the imgsz=1280 the mission actually uses: 200ms/frame
on CPU, 41ms on MPS -- same model, same input size, same thresholds. That load
was competing with the simulator for the exact cores it needs.

The ordering matters for delivery: the customer's laptops are NVIDIA, this
development machine is Apple silicon, and the Raspberry Pi has neither.
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scarecrow.detection.yolo import select_inference_device


def _torch(cuda=False, mps=False, cuda_raises=False, mps_raises=False):
    def cuda_available():
        if cuda_raises:
            raise RuntimeError("driver mismatch")
        return cuda

    def mps_available():
        if mps_raises:
            raise RuntimeError("no mps")
        return mps

    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=cuda_available),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=mps_available)),
    )


def _with_torch(mod, env=None):
    """Run selection against a fake torch and a clean environment."""
    patches = {"torch": mod} if mod is not None else {}
    ctx_env = patch.dict("os.environ", env or {}, clear=False)
    if mod is None:
        # Simulate torch being absent entirely (the Pi without a torch build).
        ctx_mod = patch.dict(sys.modules, {"torch": None})
    else:
        ctx_mod = patch.dict(sys.modules, patches)
    with ctx_env, ctx_mod:
        return select_inference_device()


class TestDeviceSelection:
    def test_prefers_cuda_when_present(self):
        """The delivery laptops are RTX 5090/5080."""
        assert _with_torch(_torch(cuda=True, mps=False), {"SCARECROW_YOLO_DEVICE": ""}) == "cuda"

    def test_prefers_cuda_over_mps(self):
        assert _with_torch(_torch(cuda=True, mps=True), {"SCARECROW_YOLO_DEVICE": ""}) == "cuda"

    def test_uses_mps_on_apple_silicon(self):
        assert _with_torch(_torch(cuda=False, mps=True), {"SCARECROW_YOLO_DEVICE": ""}) == "mps"

    def test_falls_back_to_cpu_with_no_accelerator(self):
        """The Raspberry Pi path."""
        assert _with_torch(_torch(cuda=False, mps=False), {"SCARECROW_YOLO_DEVICE": ""}) == "cpu"

    def test_cpu_when_torch_is_not_importable(self):
        assert _with_torch(None, {"SCARECROW_YOLO_DEVICE": ""}) == "cpu"

    def test_a_raising_cuda_probe_does_not_crash(self):
        """A broken CUDA install must degrade, not abort the flight."""
        assert _with_torch(
            _torch(cuda_raises=True, mps=True), {"SCARECROW_YOLO_DEVICE": ""}
        ) == "mps"

    def test_a_raising_mps_probe_does_not_crash(self):
        assert _with_torch(
            _torch(cuda=False, mps_raises=True), {"SCARECROW_YOLO_DEVICE": ""}
        ) == "cpu"


class TestOverride:
    def test_environment_override_wins(self):
        """MPS has operator-coverage gaps; recovery must not need a code change."""
        assert _with_torch(
            _torch(cuda=True, mps=True), {"SCARECROW_YOLO_DEVICE": "cpu"}
        ) == "cpu"

    def test_override_is_honoured_even_with_no_torch(self):
        assert _with_torch(None, {"SCARECROW_YOLO_DEVICE": "cuda:1"}) == "cuda:1"

    def test_blank_override_is_ignored(self):
        assert _with_torch(
            _torch(cuda=False, mps=True), {"SCARECROW_YOLO_DEVICE": "   "}
        ) == "mps"


class TestDetectorWiring:
    def test_explicit_device_is_not_overridden(self):
        from scarecrow.detection.yolo import YoloDetector

        det = YoloDetector(model_path="x.pt", output_dir="/tmp/x", device="cpu")

        assert det._device == "cpu"

    def test_device_is_auto_selected_when_not_given(self):
        from scarecrow.detection import yolo

        with patch.object(yolo, "select_inference_device", return_value="cuda"):
            det = yolo.YoloDetector(model_path="x.pt", output_dir="/tmp/x")

        assert det._device == "cuda"
