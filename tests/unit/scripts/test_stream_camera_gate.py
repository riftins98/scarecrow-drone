"""The WebRTC streamer only runs the camera while somebody is watching.

The camera used to start with the server and poll forever, so an unattended
mission paid for a video feed nobody would see -- in CPU, and in GPU too, since
an unsubscribed gz-sensors camera is not rendered at all.

The failure these guard against is the expensive direction in both senses: a
camera left running when the last viewer left, and a camera stopped out from
under a viewer who is still connected.
"""
import asyncio
import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _load_streamer():
    path = os.path.join(REPO_ROOT, "scripts", "stream_camera_webrtc.py")
    spec = importlib.util.spec_from_file_location("stream_camera_webrtc", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["stream_camera_webrtc"] = module
    spec.loader.exec_module(module)
    return module


try:
    streamer = _load_streamer()
except Exception as exc:  # pragma: no cover - depends on optional stream deps
    pytest.skip(f"stream deps unavailable: {exc}", allow_module_level=True)

CameraGate = streamer.CameraGate


class FakeCamera:
    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.running = False

    def start(self):
        self.starts += 1
        self.running = True

    def stop(self):
        self.stops += 1
        self.running = False


@pytest.mark.asyncio
async def test_camera_does_not_run_until_a_viewer_connects():
    camera = FakeCamera()
    CameraGate(camera)

    assert camera.starts == 0
    assert camera.running is False


@pytest.mark.asyncio
async def test_first_viewer_starts_the_camera():
    camera = FakeCamera()
    gate = CameraGate(camera, grace_s=0.01)

    await gate.acquire()

    assert camera.running is True
    assert camera.starts == 1


@pytest.mark.asyncio
async def test_second_viewer_does_not_restart_the_camera():
    camera = FakeCamera()
    gate = CameraGate(camera, grace_s=0.01)

    await gate.acquire()
    await gate.acquire()

    assert camera.starts == 1


@pytest.mark.asyncio
async def test_camera_keeps_running_while_one_viewer_remains():
    """The expensive-to-get-wrong direction: never stop under a live viewer."""
    camera = FakeCamera()
    gate = CameraGate(camera, grace_s=0.01)

    await gate.acquire()
    await gate.acquire()
    gate.release()
    await asyncio.sleep(0.05)

    assert camera.running is True
    assert camera.stops == 0


@pytest.mark.asyncio
async def test_camera_stops_after_the_last_viewer_leaves():
    camera = FakeCamera()
    gate = CameraGate(camera, grace_s=0.01)

    await gate.acquire()
    gate.release()
    await asyncio.sleep(0.05)

    assert camera.running is False
    assert camera.stops == 1


@pytest.mark.asyncio
async def test_a_reconnect_within_the_grace_period_keeps_the_camera_warm():
    """A browser refresh drops one connection and opens another.

    Without the grace period that round-trips through topic discovery on every
    reload, and the viewer stares at a black frame for it.
    """
    camera = FakeCamera()
    gate = CameraGate(camera, grace_s=5.0)

    await gate.acquire()
    gate.release()
    await gate.acquire()
    await asyncio.sleep(0.05)

    assert camera.running is True
    assert camera.starts == 1
    assert camera.stops == 0


@pytest.mark.asyncio
async def test_release_never_drives_the_count_negative():
    """aiortc reports more than one terminal state per connection.

    A stray extra release must not leave the gate owing a start, or the next
    viewer connects to a camera that never spins up.
    """
    camera = FakeCamera()
    gate = CameraGate(camera, grace_s=0.01)

    gate.release()
    gate.release()
    await gate.acquire()

    assert camera.running is True
    assert camera.starts == 1


@pytest.mark.asyncio
async def test_shutdown_stops_the_camera_even_with_viewers_attached():
    camera = FakeCamera()
    gate = CameraGate(camera, grace_s=60.0)

    await gate.acquire()
    await gate.shutdown()

    assert camera.running is False
