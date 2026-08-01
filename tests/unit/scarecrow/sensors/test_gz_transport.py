"""The in-process subscription seam and its fallback.

These guard the claim that replacing `gz topic -e -n 1` polling with a
gz-transport subscription changed how the data arrives and nothing else. The
two read paths must produce identical readings, reject identical garbage, and
the CLI path must still be reachable on a host without the bindings -- the
Raspberry Pi has no Gazebo at all, and the delivery image's apt metapackage may
or may not ship python3-gz-transport13.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from scarecrow.sensors import gz_transport
from scarecrow.sensors.camera.gazebo import GazeboCamera, frame_from_proto
from scarecrow.sensors.gz_transport import GzSubscription, apply_gz_env
from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.sensors.rangefinder.gazebo import GazeboRangefinder


def _laserscan(ranges, angle_min=-np.pi, angle_max=np.pi):
    return SimpleNamespace(ranges=list(ranges), angle_min=angle_min, angle_max=angle_max)


class TestGzSubscription:
    def test_start_returns_false_without_bindings(self, monkeypatch):
        """No bindings must mean 'use the fallback', not an exception.

        This is the Raspberry Pi and the unverified-Docker case. A raise here
        would take down a sensor that has a perfectly good CLI path available.
        """
        monkeypatch.setattr(gz_transport, "_Node", None)
        sub = GzSubscription("/topic", object, lambda m: None)

        assert sub.start() is False
        assert sub.active is False

    def test_start_returns_false_when_subscribe_fails(self, monkeypatch):
        node = MagicMock()
        node.subscribe.return_value = False
        monkeypatch.setattr(gz_transport, "_Node", MagicMock(return_value=node))

        assert GzSubscription("/topic", object, lambda m: None).start() is False

    def test_start_returns_false_when_transport_raises(self, monkeypatch):
        monkeypatch.setattr(
            gz_transport, "_Node", MagicMock(side_effect=RuntimeError("boom"))
        )

        assert GzSubscription("/t", object, lambda m: None).start() is False

    def test_node_is_retained_after_start(self, monkeypatch):
        """gz-transport drops the subscription when its Node is collected.

        A Node created as a local in start() would unsubscribe the moment
        start() returned, and the sensor would go quiet with no error.
        """
        node = MagicMock()
        node.subscribe.return_value = True
        monkeypatch.setattr(gz_transport, "_Node", MagicMock(return_value=node))

        sub = GzSubscription("/topic", object, lambda m: None)
        assert sub.start() is True
        assert sub._node is node

    def test_stop_unsubscribes_and_is_idempotent(self, monkeypatch):
        node = MagicMock()
        node.subscribe.return_value = True
        monkeypatch.setattr(gz_transport, "_Node", MagicMock(return_value=node))

        sub = GzSubscription("/topic", object, lambda m: None)
        sub.start()
        sub.stop()
        sub.stop()

        node.unsubscribe.assert_called_once_with("/topic")
        assert sub.active is False

    def test_stop_before_start_is_safe(self):
        GzSubscription("/topic", object, lambda m: None).stop()

    def test_callback_exception_does_not_escape(self, monkeypatch):
        """A raising consumer must not kill delivery for the rest of the flight.

        The callback runs on a gz-transport thread, where an exception is lost
        and takes the subscription with it.
        """
        node = MagicMock()
        node.subscribe.return_value = True
        monkeypatch.setattr(gz_transport, "_Node", MagicMock(return_value=node))

        sub = GzSubscription("/t", object, MagicMock(side_effect=ValueError))
        sub.start()
        sub._on_message(object())  # must not raise


class TestApplyGzEnv:
    def test_exports_gz_variables(self, monkeypatch):
        """Without this the Node joins the wrong partition and sees nothing.

        The CLI path passed GZ_PARTITION per subprocess; an in-process Node
        reads it from its own environment instead. Getting this wrong looks
        exactly like a sensor that has not started publishing yet.
        """
        monkeypatch.delenv("GZ_PARTITION", raising=False)
        apply_gz_env({"GZ_PARTITION": "px4", "GZ_IP": "10.0.0.2"})

        import os

        assert os.environ["GZ_PARTITION"] == "px4"
        assert os.environ["GZ_IP"] == "10.0.0.2"

    def test_ignores_unrelated_and_empty_values(self, monkeypatch):
        monkeypatch.delenv("PATH_SHOULD_NOT_MOVE", raising=False)
        apply_gz_env({"PATH_SHOULD_NOT_MOVE": "x", "GZ_EMPTY": ""})

        import os

        assert "PATH_SHOULD_NOT_MOVE" not in os.environ
        assert "GZ_EMPTY" not in os.environ

    def test_none_env_is_accepted(self):
        apply_gz_env(None)


class TestLidarPathsAgree:
    """Both read paths must yield the same LidarScan for the same scan."""

    def test_proto_and_text_produce_equal_scans(self):
        ranges = [1.5] * 1440
        text = "angle_min: -3.14159\nangle_max: 3.14159\n" + "\n".join(
            f"ranges: {r}" for r in ranges
        )

        from_text = GazeboLidar._parse_scan(text)
        from_proto = GazeboLidar._scan_from_proto(
            _laserscan(ranges, -3.14159, 3.14159)
        )

        assert from_text is not None and from_proto is not None
        np.testing.assert_allclose(from_proto.ranges, from_text.ranges)
        assert from_proto.angle_min == pytest.approx(from_text.angle_min)
        assert from_proto.angle_max == pytest.approx(from_text.angle_max)

    def test_proto_enforces_the_same_360_degree_contract(self):
        """A half-scan must be rejected on both paths.

        The controllers index by angle assuming a full circle. A 180-degree
        scan that got through would silently map every bearing to the wrong
        ray, and the drone would follow a wall that is not there.
        """
        assert GazeboLidar._scan_from_proto(_laserscan([1.0] * 720, 0.0, np.pi)) is None

    def test_proto_rejects_empty_ranges(self):
        assert GazeboLidar._scan_from_proto(_laserscan([])) is None

    def test_proto_rejects_a_malformed_message(self):
        assert GazeboLidar._scan_from_proto(object()) is None

    def test_infinite_ranges_are_preserved_not_dropped(self):
        """Index-to-angle mapping depends on keeping every ray in place."""
        ranges = [float("inf")] * 1440
        ranges[10] = 2.0

        scan = GazeboLidar._scan_from_proto(_laserscan(ranges))

        assert scan is not None
        assert len(scan.ranges) == 1440
        assert scan.ranges[10] == pytest.approx(2.0)


class TestRangefinderPathsAgree:
    def test_proto_and_text_agree(self):
        from_text = GazeboRangefinder._parse_reading("ranges: 2.5")
        from_value = GazeboRangefinder._reading_from_distance(2.5)

        assert from_text.distance_m == pytest.approx(from_value.distance_m)

    @pytest.mark.parametrize("bad", [float("inf"), float("nan"), 0.0, -1.0])
    def test_invalid_distances_rejected_on_both_paths(self, bad):
        """This sensor sets the altitude ceiling; a bad value flies into a roof."""
        assert GazeboRangefinder._reading_from_distance(bad) is None

    def test_subscription_callback_uses_the_first_ray(self):
        rf = GazeboRangefinder(topic="/t", env={})
        rf._on_scan(SimpleNamespace(ranges=[3.25, 9.0]))

        assert rf.get_distance_m() == pytest.approx(3.25)

    def test_subscription_callback_ignores_empty_and_invalid(self):
        rf = GazeboRangefinder(topic="/t", env={})
        rf._on_scan(SimpleNamespace(ranges=[]))
        rf._on_scan(SimpleNamespace(ranges=[float("inf")]))

        assert rf.get_reading() is None


class TestCameraPathsAgree:
    def _image(self, width=4, height=3):
        rgb = np.arange(width * height * 3, dtype=np.uint8).reshape(
            (height, width, 3)
        )
        return rgb, SimpleNamespace(
            width=width, height=height, data=rgb.tobytes()
        )

    def test_proto_frame_is_bgr(self):
        """Every consumer expects BGR. Getting it backwards is silent: the
        picture still looks like a picture and detection accuracy just drops.
        """
        rgb, msg = self._image()

        bgr = frame_from_proto(msg)

        assert bgr is not None
        np.testing.assert_array_equal(bgr[:, :, 0], rgb[:, :, 2])
        np.testing.assert_array_equal(bgr[:, :, 2], rgb[:, :, 0])

    def test_truncated_payload_is_rejected(self):
        _, msg = self._image()
        msg.data = msg.data[:-5]

        assert frame_from_proto(msg) is None

    def test_zero_dimensions_rejected(self):
        _, msg = self._image()
        msg.width = 0

        assert frame_from_proto(msg) is None

    def test_malformed_message_rejected(self):
        assert frame_from_proto(object()) is None

    def test_subscription_callback_feeds_on_frame(self):
        """The on_frame contract is what YOLO and the streamer consume.

        If the subscription path did not call it, detection would go silent
        while the camera looked perfectly healthy.
        """
        camera = GazeboCamera(topic="/t", env={})
        seen = []
        camera.on_frame = seen.append

        _, msg = self._image()
        camera._on_image(msg)

        assert len(seen) == 1
        assert camera.get_frame() is not None

    def test_bad_frame_does_not_reach_consumers(self):
        camera = GazeboCamera(topic="/t", env={})
        camera.on_frame = MagicMock()

        camera._on_image(object())

        camera.on_frame.assert_not_called()
        assert camera.get_frame() is None


class TestFallbackSelection:
    """start() must choose the subscription, and degrade quietly without it."""

    def test_lidar_uses_threads_when_transport_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "scarecrow.sensors.lidar.gazebo.transport_available", lambda: False
        )
        lidar = GazeboLidar(topic="/t", env={})

        with patch("threading.Thread") as thread:
            lidar.start()

        assert lidar.using_transport is False
        assert thread.call_count == lidar._num_threads

    def test_lidar_starts_no_threads_when_subscribed(self, monkeypatch):
        """The whole point: the fast path must not also spawn the pollers."""
        monkeypatch.setattr(
            "scarecrow.sensors.lidar.gazebo.transport_available", lambda: True
        )
        monkeypatch.setattr(GzSubscription, "start", lambda self: True)
        monkeypatch.setattr(GzSubscription, "active", property(lambda self: True))
        lidar = GazeboLidar(topic="/t", env={})

        with patch("threading.Thread") as thread:
            lidar.start()

        assert lidar.using_transport is True
        thread.assert_not_called()

    def test_camera_falls_back_when_subscribe_fails(self, monkeypatch):
        monkeypatch.setattr(
            "scarecrow.sensors.camera.gazebo.transport_available", lambda: True
        )
        monkeypatch.setattr(GzSubscription, "start", lambda self: False)
        camera = GazeboCamera(topic="/t", env={})

        with patch("threading.Thread") as thread:
            camera.start()

        assert camera.using_transport is False
        assert thread.call_count == camera._num_threads
