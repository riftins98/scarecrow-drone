"""UT-14: TelemetryRepository tests."""
from dtos import TelemetryCreateDTO
from repositories import TelemetryRepository


class TestTelemetryRepository:
    def test_create_and_retrieve(self, repo_db):
        repo = TelemetryRepository()
        repo.create(TelemetryCreateDTO(flight_id="flight-1", battery_level=85.0, distance=12.5, detections=3))
        fetched = repo.get_by_flight_id("flight-1")
        assert fetched is not None
        assert fetched.battery_level == 85.0
        assert fetched.distance == 12.5
        assert fetched.detections == 3

    def test_create_with_defaults(self, repo_db):
        repo = TelemetryRepository()
        repo.create(TelemetryCreateDTO(flight_id="flight-default"))
        fetched = repo.get_by_flight_id("flight-default")
        assert fetched.battery_level is None
        assert fetched.distance == 0
        assert fetched.detections == 0

    def test_get_nonexistent_returns_none(self, repo_db):
        repo = TelemetryRepository()
        assert repo.get_by_flight_id("no-such") is None

    def test_update_increments_values(self, repo_db):
        repo = TelemetryRepository()
        repo.create(TelemetryCreateDTO(flight_id="f1"))
        repo.update("f1", battery_level=70.5, distance=5.0, detections=2)
        updated = repo.get_by_flight_id("f1")
        assert updated.battery_level == 70.5
        assert updated.distance == 5.0
        assert updated.detections == 2

    def test_update_ignores_invalid_columns(self, repo_db):
        repo = TelemetryRepository()
        repo.create(TelemetryCreateDTO(flight_id="f1"))
        repo.update("f1", malicious="DROP TABLE", distance=3.0)
        fetched = repo.get_by_flight_id("f1")
        assert fetched.distance == 3.0
