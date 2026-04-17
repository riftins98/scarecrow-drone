"""UT-15: ChaseEventRepository tests."""
from dtos import ChaseEventCreateDTO
from repositories import ChaseEventRepository


class TestChaseEventRepository:
    def test_create_returns_chase_with_start_time(self, repo_db):
        repo = ChaseEventRepository()
        chase = repo.create(ChaseEventCreateDTO(
            flight_id="f1", counter_measure_type="pursuit"
        ))
        assert chase.id > 0
        assert chase.flight_id == "f1"
        assert chase.counter_measure_type == "pursuit"
        assert chase.start_time is not None
        assert chase.end_time is None
        assert chase.outcome is None

    def test_create_with_detection_image_id(self, repo_db):
        repo = ChaseEventRepository()
        chase = repo.create(ChaseEventCreateDTO(
            flight_id="f1", detection_image_id=42, counter_measure_type="movement"
        ))
        assert chase.detection_image_id == 42

    def test_get_by_id(self, repo_db):
        repo = ChaseEventRepository()
        chase = repo.create(ChaseEventCreateDTO(flight_id="f1", counter_measure_type="pursuit"))
        fetched = repo.get_by_id(chase.id)
        assert fetched is not None
        assert fetched.id == chase.id

    def test_get_by_id_nonexistent(self, repo_db):
        repo = ChaseEventRepository()
        assert repo.get_by_id(9999) is None

    def test_get_by_flight_id_orders_by_start_time(self, repo_db):
        repo = ChaseEventRepository()
        c1 = repo.create(ChaseEventCreateDTO(flight_id="f1", counter_measure_type="pursuit"))
        c2 = repo.create(ChaseEventCreateDTO(flight_id="f1", counter_measure_type="movement"))
        repo.create(ChaseEventCreateDTO(flight_id="f2", counter_measure_type="pursuit"))
        chases = repo.get_by_flight_id("f1")
        assert len(chases) == 2
        assert chases[0].id == c1.id
        assert chases[1].id == c2.id

    def test_update_sets_outcome_and_end_time(self, repo_db):
        repo = ChaseEventRepository()
        chase = repo.create(ChaseEventCreateDTO(flight_id="f1", counter_measure_type="pursuit"))
        repo.update(chase.id, outcome="dispersed", end_time="2026-04-17T12:00:00")
        updated = repo.get_by_id(chase.id)
        assert updated.outcome == "dispersed"
        assert updated.end_time == "2026-04-17T12:00:00"

    def test_update_ignores_invalid_columns(self, repo_db):
        repo = ChaseEventRepository()
        chase = repo.create(ChaseEventCreateDTO(flight_id="f1", counter_measure_type="pursuit"))
        repo.update(chase.id, flight_id="hijacked", outcome="lost")
        updated = repo.get_by_id(chase.id)
        # flight_id not in allowed list -- should not change
        assert updated.flight_id == "f1"
        assert updated.outcome == "lost"
