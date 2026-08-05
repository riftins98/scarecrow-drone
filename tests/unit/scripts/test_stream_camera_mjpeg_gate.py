"""The MJPEG streamer runs its cameras only while a client is connected.

This is the only stream path, on every platform. Without the gate a camera
nobody is watching still costs CPU, and GPU too -- gz-sensors skips rendering
a camera with no subscribers, so an ungated stream keeps every camera live for
the whole session.
"""
import importlib.util
import os
import sys
import threading
import time

import pytest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _load():
    path = os.path.join(REPO_ROOT, "scripts", "stream_camera.py")
    spec = importlib.util.spec_from_file_location("stream_camera_mjpeg", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["stream_camera_mjpeg"] = module
    spec.loader.exec_module(module)
    return module


try:
    streamer = _load()
except Exception as exc:  # pragma: no cover - depends on optional deps
    pytest.skip(f"stream deps unavailable: {exc}", allow_module_level=True)

CameraGate = streamer.CameraGate


class FakeCamera:
    def __init__(self, fail_on_start=False):
        self.starts = 0
        self.stops = 0
        self.running = False
        self._fail = fail_on_start

    def start(self):
        self.starts += 1
        if self._fail:
            raise RuntimeError("topic not found")
        self.running = True

    def stop(self):
        self.stops += 1
        self.running = False


def _settle(gate, timeout=2.0):
    """Wait for the idle timer to fire rather than sleeping a fixed amount."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not gate.watching and gate._timer is None and not gate._started:
            return True
        time.sleep(0.01)
    return False


class TestGate:
    def test_cameras_do_not_run_before_a_viewer_arrives(self):
        cam = FakeCamera()
        gate = CameraGate([cam])

        assert cam.starts == 0
        assert gate.watching is False

    def test_first_viewer_starts_every_camera(self):
        cams = [FakeCamera(), FakeCamera()]
        gate = CameraGate(cams, grace_s=0.05)

        gate.acquire()

        assert all(c.running for c in cams)
        assert gate.watching is True

    def test_second_viewer_does_not_restart_cameras(self):
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=0.05)

        gate.acquire()
        gate.acquire()

        assert cam.starts == 1

    def test_cameras_keep_running_while_one_viewer_remains(self):
        """The expensive mistake: stopping under a client that is still there."""
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=0.05)

        gate.acquire()
        gate.acquire()
        gate.release()
        time.sleep(0.15)

        assert cam.running is True
        assert cam.stops == 0

    def test_cameras_stop_after_the_last_viewer_leaves(self):
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=0.05)

        gate.acquire()
        gate.release()

        assert _settle(gate), "idle timer never stopped the camera"
        assert cam.running is False

    def test_reconnect_within_grace_keeps_the_camera_warm(self):
        """A browser refresh drops one connection before opening the next."""
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=5.0)

        gate.acquire()
        gate.release()
        gate.acquire()
        time.sleep(0.1)

        assert cam.running is True
        assert cam.starts == 1
        assert cam.stops == 0

    def test_release_without_acquire_never_goes_negative(self):
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=0.05)

        gate.release()
        gate.release()
        gate.acquire()

        assert cam.running is True
        assert cam.starts == 1

    def test_shutdown_stops_cameras_even_with_viewers_attached(self):
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=60.0)

        gate.acquire()
        gate.shutdown()

        assert cam.running is False

    def test_shutdown_cancels_a_pending_idle_stop(self):
        """A timer firing after shutdown would touch already-stopped cameras."""
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=0.05)

        gate.acquire()
        gate.release()
        gate.shutdown()
        time.sleep(0.15)

        assert gate._timer is None
        assert cam.running is False

    def test_a_camera_that_fails_to_start_does_not_break_the_server(self):
        """Topic discovery can fail; the HTTP server must survive it."""
        bad, good = FakeCamera(fail_on_start=True), FakeCamera()
        gate = CameraGate([bad, good], grace_s=0.05)

        gate.acquire()

        assert good.running is True
        assert gate.watching is True

    def test_concurrent_viewers_are_counted_correctly(self):
        """ThreadedHTTPServer means acquire/release really do race."""
        cam = FakeCamera()
        gate = CameraGate([cam], grace_s=0.05)

        def viewer():
            gate.acquire()
            time.sleep(0.02)
            gate.release()

        threads = [threading.Thread(target=viewer) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert _settle(gate), "viewer count leaked; cameras left running"
        assert cam.starts == 1, "cameras restarted mid-session"


class TestGateContract:
    def test_the_gate_exposes_its_whole_contract(self):
        """launch_with_stream.sh and switch_camera() both depend on all three."""
        for name in ("acquire", "release", "shutdown"):
            assert hasattr(CameraGate, name), f"MJPEG gate is missing {name}()"

    def test_jpeg_quality_default_is_not_bandwidth_limited(self):
        """The stream is loopback-only; 68 was sized for a budget it lacks."""
        import re

        src = open(os.path.join(REPO_ROOT, "scripts", "stream_camera.py")).read()
        m = re.search(r"--quality.*?default=(\d+)", src, re.S)
        assert m and int(m.group(1)) >= 85
