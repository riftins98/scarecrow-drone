"""RecordingService tests."""
from services import RecordingService


class TestRecordingService:
    def test_initial_state(self):
        svc = RecordingService()
        status = svc.get_status()
        assert status["recording"] is False
        assert status["flightId"] is None
        assert status["videoPath"] is None

    def test_on_flight_started_sets_recording(self):
        svc = RecordingService()
        svc.on_flight_started("f1")
        status = svc.get_status()
        assert status["recording"] is True
        assert status["flightId"] == "f1"

    def test_on_video_ready_clears_recording(self):
        svc = RecordingService()
        svc.on_flight_started("f1")
        svc.on_video_ready("/tmp/flight.mp4")
        status = svc.get_status()
        assert status["recording"] is False
        assert status["videoPath"] == "/tmp/flight.mp4"

    def test_on_flight_ended_without_video(self):
        svc = RecordingService()
        svc.on_flight_started("f1")
        svc.on_flight_ended()
        status = svc.get_status()
        assert status["recording"] is False
        assert status["videoPath"] is None
