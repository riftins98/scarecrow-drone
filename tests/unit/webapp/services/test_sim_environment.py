"""Tests for the environment-portability behaviour of SimService.

These cover the two things that made the webapp unusable on the pixi (macOS)
track:

1. Pressing "Connect" rebuilt PX4 through launch.sh, which invokes CMake with
   none of the flags pixi.toml's `build` task passes. That did not merely waste
   time -- it destroyed a working build (protobuf 35 deprecates
   RepeatedField::Resize and PX4 builds with -Werror).
2. The camera-switch path shelled out to `ss`, which is iproute2 and therefore
   Linux-only, so every swap raised FileNotFoundError on macOS.
"""
import os
import socket
from unittest.mock import patch

from services import sim_service as sim_mod


class TestSkipPx4Build:
    """--no-build is passed whenever there is already a binary to run."""

    def test_skips_build_when_binary_exists(self):
        with patch.object(os.path, "isfile", return_value=True):
            assert sim_mod._skip_px4_build() is True

    def test_builds_when_binary_missing(self):
        """A fresh clone must still build, or Connect has nothing to launch."""
        with patch.object(os.path, "isfile", return_value=False):
            assert sim_mod._skip_px4_build() is False

    def test_force_build_env_overrides(self):
        with patch.dict(os.environ, {"SCARECROW_FORCE_BUILD": "1"}), \
                patch.object(os.path, "isfile", return_value=True):
            assert sim_mod._skip_px4_build() is False

    def test_launch_appends_no_build_flag(self):
        """The flag reaches the launcher argv, not just the helper."""
        svc = sim_mod.SimService()
        with patch.object(sim_mod, "_skip_px4_build", return_value=True), \
                patch.object(svc, "stop"), \
                patch.object(sim_mod.time, "sleep"), \
                patch.object(sim_mod.os.path, "exists", return_value=True), \
                patch.object(sim_mod.subprocess, "Popen") as popen, \
                patch.object(sim_mod.threading, "Thread"):
            svc.launch(world="hangar_small", headless=True, camera="fixed")

        argv = popen.call_args[0][0]
        assert "--no-build" in argv
        assert argv[0] == "bash"

    def test_launch_omits_flag_when_build_needed(self):
        svc = sim_mod.SimService()
        with patch.object(sim_mod, "_skip_px4_build", return_value=False), \
                patch.object(svc, "stop"), \
                patch.object(sim_mod.time, "sleep"), \
                patch.object(sim_mod.os.path, "exists", return_value=True), \
                patch.object(sim_mod.subprocess, "Popen") as popen, \
                patch.object(sim_mod.threading, "Thread"):
            svc.launch(world="hangar_small", headless=True, camera="fixed")

        assert "--no-build" not in popen.call_args[0][0]


class TestPortInUse:
    """Portable replacement for `ss -tln` (absent on macOS and Windows)."""

    def test_reports_listening_port(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        try:
            assert sim_mod._port_in_use(port) is True
        finally:
            sock.close()

    def test_reports_free_port(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        assert sim_mod._port_in_use(port) is False
