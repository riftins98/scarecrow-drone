"""UT-17: DroneService tests."""
from unittest.mock import MagicMock

from services import DroneService


class TestDroneService:
    def test_status_when_no_detection_service(self):
        svc = DroneService(detection_service=None)
        status = svc.get_status()
        assert status["isConnected"] is False
        assert status["isFlying"] is False
        assert status["mode"] == "idle"

    def test_status_when_flying(self):
        mock_ds = MagicMock()
        mock_ds.running = True
        svc = DroneService(detection_service=mock_ds)
        status = svc.get_status()
        assert status["isFlying"] is True
        assert status["mode"] == "offboard"

    def test_start_flight_delegates(self):
        mock_ds = MagicMock()
        mock_ds.start.return_value = True
        svc = DroneService(detection_service=mock_ds)
        assert svc.start_flight("f1") is True
        mock_ds.start.assert_called_once()

    def test_start_flight_without_detection_service_returns_false(self):
        svc = DroneService(detection_service=None)
        assert svc.start_flight("f1") is False

    def test_abort_calls_stop(self):
        mock_ds = MagicMock()
        svc = DroneService(detection_service=mock_ds)
        assert svc.abort() is True
        mock_ds.stop.assert_called_once()

    def test_update_telemetry_stores_data(self):
        svc = DroneService()
        svc.update_telemetry({"battery": 80.0, "distance": 12.5})
        telem = svc.get_telemetry()
        assert telem["battery"] == 80.0
        assert telem["distance"] == 12.5

    def test_current_flight_id_tracks_detection_service(self):
        mock_ds = MagicMock()
        mock_ds.flight_id = "flight-xyz"
        svc = DroneService(detection_service=mock_ds)
        assert svc.current_flight_id == "flight-xyz"
