"""UT-12: FlightRepository CRUD tests."""
from repositories import FlightRepository


class TestFlightRepository:
    def test_create_returns_flight_with_id(self, repo_db):
        repo = FlightRepository()
        flight = repo.create()
        assert flight.id is not None
        assert len(flight.id) == 8  # UUID prefix
        assert flight.status == "in_progress"
        assert flight.area_map_id is None

    def test_create_with_area_map_id(self, repo_db):
        repo = FlightRepository()
        flight = repo.create(area_map_id=42)
        assert flight.area_map_id == 42

    def test_get_by_id_returns_flight(self, repo_db):
        repo = FlightRepository()
        created = repo.create()
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_by_id_nonexistent_returns_none(self, repo_db):
        repo = FlightRepository()
        assert repo.get_by_id("no-such-id") is None

    def test_get_all_returns_all_flights(self, repo_db):
        repo = FlightRepository()
        f1 = repo.create()
        f2 = repo.create()
        all_flights = repo.get_all()
        ids = {f.id for f in all_flights}
        assert f1.id in ids
        assert f2.id in ids

    def test_update_changes_status(self, repo_db):
        repo = FlightRepository()
        flight = repo.create()
        repo.update(flight.id, status="completed")
        updated = repo.get_by_id(flight.id)
        assert updated.status == "completed"

    def test_update_ignores_invalid_columns(self, repo_db):
        """Passing a random kwarg shouldn't cause SQL injection or error."""
        repo = FlightRepository()
        flight = repo.create()
        repo.update(flight.id, malicious_field="DROP TABLE")
        # Flight should still exist
        assert repo.get_by_id(flight.id) is not None

    def test_delete_removes_flight(self, repo_db):
        repo = FlightRepository()
        flight = repo.create()
        assert repo.delete(flight.id) is True
        assert repo.get_by_id(flight.id) is None

    def test_delete_nonexistent_returns_false(self, repo_db):
        repo = FlightRepository()
        assert repo.delete("no-such-id") is False

    def test_end_flight_sets_completed_and_counts(self, repo_db):
        repo = FlightRepository()
        flight = repo.create()
        repo.end_flight(flight.id, pigeons=5, frames=100, video_path="/tmp/v.mp4")
        updated = repo.get_by_id(flight.id)
        assert updated.status == "completed"
        assert updated.pigeons_detected == 5
        assert updated.frames_processed == 100
        assert updated.video_path == "/tmp/v.mp4"
        assert updated.end_time is not None

    def test_fail_flight_sets_failed(self, repo_db):
        repo = FlightRepository()
        flight = repo.create()
        repo.fail_flight(flight.id)
        updated = repo.get_by_id(flight.id)
        assert updated.status == "failed"
        assert updated.end_time is not None
