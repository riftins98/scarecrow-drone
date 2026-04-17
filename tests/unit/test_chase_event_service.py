"""ChaseEventService tests."""
import pytest

from services import ChaseEventService


class TestChaseEventService:
    def test_start_chase_with_valid_measure(self, repo_db):
        svc = ChaseEventService()
        chase = svc.start_chase("f1", counter_measure_type="pursuit")
        assert chase.flight_id == "f1"
        assert chase.counter_measure_type == "pursuit"
        assert chase.outcome is None

    def test_start_chase_rejects_invalid_measure(self, repo_db):
        svc = ChaseEventService()
        with pytest.raises(ValueError):
            svc.start_chase("f1", counter_measure_type="smoke_bomb")

    def test_end_chase_with_valid_outcome(self, repo_db):
        svc = ChaseEventService()
        chase = svc.start_chase("f1", counter_measure_type="pursuit")
        ended = svc.end_chase(chase.id, outcome="dispersed")
        assert ended.outcome == "dispersed"
        assert ended.end_time is not None

    def test_end_chase_rejects_invalid_outcome(self, repo_db):
        svc = ChaseEventService()
        chase = svc.start_chase("f1", counter_measure_type="pursuit")
        with pytest.raises(ValueError):
            svc.end_chase(chase.id, outcome="vaporized")

    def test_get_chases_for_flight(self, repo_db):
        svc = ChaseEventService()
        svc.start_chase("f1", counter_measure_type="pursuit")
        svc.start_chase("f1", counter_measure_type="movement")
        svc.start_chase("f2", counter_measure_type="pursuit")
        chases = svc.get_chases_for_flight("f1")
        assert len(chases) == 2
