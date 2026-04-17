"""UT-16: FlightService tests."""
from unittest.mock import MagicMock

from repositories import FlightRepository, TelemetryRepository, DetectionImageRepository
from services import FlightService


class TestFlightService:
    def test_create_flight_creates_flight_and_telemetry(self, repo_db):
        svc = FlightService()
        flight = svc.create_flight()
        # Telemetry row should also exist
        tel = svc.telemetry_repo.get_by_flight_id(flight.id)
        assert tel is not None
        assert tel.flight_id == flight.id

    def test_create_flight_with_area_map(self, repo_db):
        svc = FlightService()
        flight = svc.create_flight(area_map_id=42)
        assert flight.area_map_id == 42

    def test_start_detection_without_service_returns_false(self, repo_db):
        svc = FlightService(detection_service=None)
        assert svc.start_detection("any-id") is False

    def test_start_detection_delegates_to_service(self, repo_db):
        mock_ds = MagicMock()
        mock_ds.start.return_value = True
        svc = FlightService(detection_service=mock_ds)
        result = svc.start_detection("flight-1")
        assert result is True
        mock_ds.start.assert_called_once()

    def test_stop_flight_marks_completed(self, repo_db):
        mock_ds = MagicMock()
        mock_ds.stop.return_value = {
            "pigeons_detected": 5,
            "frames_processed": 100,
            "video_path": "/tmp/v.mp4",
        }
        svc = FlightService(detection_service=mock_ds)
        flight = svc.create_flight()
        updated = svc.stop_flight(flight.id)
        assert updated.status == "completed"
        assert updated.pigeons_detected == 5
        assert updated.frames_processed == 100
        assert updated.video_path == "/tmp/v.mp4"

    def test_abort_flight_sets_aborted_status(self, repo_db):
        svc = FlightService()
        flight = svc.create_flight()
        aborted = svc.abort_flight(flight.id)
        assert aborted.status == "aborted"
        assert aborted.end_time is not None

    def test_abort_already_completed_flight_is_noop(self, repo_db):
        svc = FlightService()
        flight = svc.create_flight()
        svc.flight_repo.update(flight.id, status="completed")
        result = svc.abort_flight(flight.id)
        # Should not change status
        assert result.status == "completed"

    def test_get_flight_summary(self, repo_db):
        svc = FlightService()
        flight = svc.create_flight()
        # Add 3 detection images
        for i in range(3):
            svc.detection_image_repo.create(flight.id, f"/tmp/det_{i}.png")
        summary = svc.get_flight_summary(flight.id)
        assert summary.flight_id == flight.id
        assert summary.total_detections == 3

    def test_get_flight_summary_nonexistent_returns_none(self, repo_db):
        svc = FlightService()
        assert svc.get_flight_summary("no-such") is None

    def test_delete_flight(self, repo_db):
        svc = FlightService()
        flight = svc.create_flight()
        assert svc.delete_flight(flight.id) is True
        assert svc.get_flight(flight.id) is None
