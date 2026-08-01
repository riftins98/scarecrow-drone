"""The seam that lets the same mission fly in Gazebo and on the Raspberry Pi.

The point of these tests is that mission code never learns which backend it
got. If the mission can tell them apart, it will eventually branch on it, and
the "install it on the Pi and it runs" property is lost.
"""
import os
from unittest.mock import patch

import pytest

from scarecrow.platform import (
    GazeboSensorSuite,
    HardwareSensorSuite,
    SensorSuite,
    detect_platform,
    sensor_suite_for,
)
from scarecrow.platform.base import WorldServices


class TestSuiteSelection:
    def test_explicit_simulation(self):
        suite = sensor_suite_for("simulation", repo_root="/tmp")
        assert isinstance(suite, GazeboSensorSuite)
        assert suite.name == "gazebo"

    def test_explicit_hardware(self):
        suite = sensor_suite_for("hardware")
        assert isinstance(suite, HardwareSensorSuite)
        assert suite.name == "hardware"

    def test_unknown_platform_raises(self):
        """A typo must not silently select a backend that drives real motors."""
        with pytest.raises(ValueError):
            sensor_suite_for("raspberrypi")

    def test_simulation_requires_repo_root(self):
        with pytest.raises(ValueError):
            sensor_suite_for("simulation")

    def test_env_var_overrides_detection(self):
        with patch.dict(os.environ, {"SCARECROW_PLATFORM": "hardware"}):
            assert detect_platform() == "hardware"

    def test_detection_defaults_to_simulation(self):
        """Hardware requires positive evidence; ambiguity must mean simulation."""
        with patch.dict(os.environ, {}, clear=True), \
                patch("builtins.open", side_effect=OSError):
            assert detect_platform() == "simulation"

    def test_detection_recognises_a_raspberry_pi(self):
        from unittest.mock import mock_open

        with patch.dict(os.environ, {}, clear=True), \
                patch("builtins.open", mock_open(read_data=b"Raspberry Pi 5 Model B\x00")):
            assert detect_platform() == "hardware"


class TestInterfaceParity:
    """Both suites must satisfy the same contract, or the mission breaks."""

    @pytest.mark.parametrize(
        "suite",
        [GazeboSensorSuite(repo_root="/tmp"), HardwareSensorSuite()],
        ids=["gazebo", "hardware"],
    )
    def test_implements_sensor_suite(self, suite):
        assert isinstance(suite, SensorSuite)
        assert isinstance(suite.world, WorldServices)
        for method in (
            "prepare",
            "await_prepared",
            "describe_environment",
            "start_lidar",
            "start_ceiling_rangefinder",
            "start_camera",
            "stop",
        ):
            assert callable(getattr(suite, method)), method

    @pytest.mark.parametrize(
        "suite",
        [GazeboSensorSuite(repo_root="/tmp"), HardwareSensorSuite()],
        ids=["gazebo", "hardware"],
    )
    def test_stop_is_safe_before_anything_started(self, suite):
        """Teardown runs in a finally block that may execute after an early abort."""
        suite.stop()
        suite.stop()


class TestHardwareWorldServices:
    """Sim-only capabilities must report themselves unsupported, not fake success."""

    def test_frame_calibration_returns_none(self):
        world = HardwareSensorSuite().world
        assert world.calibrate_frame(local_x=1.0, local_y=2.0, local_yaw_deg=30.0) is None

    def test_target_removal_is_unsupported_not_failed(self):
        outcome = HardwareSensorSuite().world.remove_target(
            x=1.0, y=2.0, name_prefixes=("pigeon",), uri_keywords=("pigeon",)
        )
        # supported=False is the load-bearing part: the mission logs this as
        # "target dispersed", not as a removal failure worth investigating.
        assert outcome.supported is False
        assert outcome.success is False
        assert "simulation-only" in outcome.message


class TestMissionIsPlatformAgnostic:
    def test_mission_source_never_imports_gazebo(self):
        """The regression guard for this whole change.

        The mission used to construct GazeboLidar/GazeboCamera/GazeboRangefinder
        directly, which made it unrunnable on the Pi without editing it. If a
        Gazebo import reappears here, that property is silently gone again.
        """
        from scarecrow.missions.hangar_circuit import mission

        with open(mission.__file__) as fh:
            source = fh.read()

        offenders = [
            line.strip()
            for line in source.splitlines()
            if line.startswith(("import ", "from "))
            and ("gazebo" in line.lower() or "gz_" in line)
        ]
        assert offenders == [], f"mission.py must not import Gazebo: {offenders}"

    def test_mission_accepts_either_suite(self):
        from scarecrow.missions.hangar_circuit import (
            HangarCircuitConfig,
            HangarCircuitPursuitMission,
        )

        config = HangarCircuitConfig(flight_id="test")
        for suite in (GazeboSensorSuite(repo_root="/tmp"), HardwareSensorSuite()):
            mission = HangarCircuitPursuitMission(config, sensors=suite)
            assert mission.sensors is suite
