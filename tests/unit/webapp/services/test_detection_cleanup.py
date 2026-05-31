"""Unit tests for DetectionService process-cleanup hardening.

These guard the orphan-reaping logic added after a panic reset left stray
flight scripts / mavsdk_servers squatting on the MAVSDK port (udp 14540),
which blocked every subsequent flight from connecting to PX4. The subprocess
calls are mocked — we assert *which* patterns get swept and that kill() returns
to a clean pre-flight state, without touching real processes.
"""
from unittest.mock import MagicMock, patch

from services.detection_service import DetectionService, _sweep_flight_processes


class TestSweepFlightProcesses:
    def test_noop_on_non_posix(self):
        with patch("services.detection_service.os.name", "nt"), \
             patch("services.detection_service.subprocess.run") as mock_run:
            assert _sweep_flight_processes() == 0
            mock_run.assert_not_called()

    def test_sweeps_flight_scripts_and_mavsdk_on_posix(self):
        with patch("services.detection_service.os.name", "posix"), \
             patch("services.detection_service.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _sweep_flight_processes()
            patterns = [call.args[0] for call in mock_run.call_args_list]
            # Both pkill invocations are -9 -f with a pattern.
            assert all(p[:3] == ["pkill", "-9", "-f"] for p in patterns)
            joined = " ".join(p[3] for p in patterns)
            assert "scripts" in joined and "flight" in joined
            assert "mavsdk_server" in joined

    def test_missing_pkill_is_tolerated(self):
        with patch("services.detection_service.os.name", "posix"), \
             patch("services.detection_service.subprocess.run",
                   side_effect=FileNotFoundError):
            # No pkill binary (non-WSL Windows) -> bails cleanly, returns 0.
            assert _sweep_flight_processes() == 0


class TestKillClearsState:
    def test_kill_resets_flight_state_and_sweeps(self):
        svc = DetectionService()
        # Simulate an in-progress flight.
        svc.flight_id = "abc123"
        svc.running = True
        svc.pigeons_detected = 4
        svc.frames_processed = 99
        svc.latest_telemetry = {"phase": "HOVER", "altitude": 2.5}
        svc.detection_images = ["/x/y.png"]
        svc.process = None  # no real subprocess to kill

        with patch("services.detection_service._sweep_flight_processes") as mock_sweep:
            svc.kill()
            mock_sweep.assert_called_once()

        assert svc.running is False
        assert svc.flight_id is None
        assert svc.pigeons_detected == 0
        assert svc.frames_processed == 0
        assert svc.latest_telemetry == {}
        assert svc.detection_images == []
