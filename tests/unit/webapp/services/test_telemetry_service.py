"""TelemetryService tests."""
from services import TelemetryService


class TestTelemetryService:
    def test_init_telemetry_creates_row(self, repo_db):
        svc = TelemetryService()
        telem = svc.init_telemetry("f1")
        assert telem.flight_id == "f1"
        assert telem.battery_level is None
        assert telem.distance == 0

    def test_init_telemetry_idempotent(self, repo_db):
        svc = TelemetryService()
        first = svc.init_telemetry("f1")
        second = svc.init_telemetry("f1")
        assert first.flight_id == second.flight_id

    def test_update_only_provided_fields(self, repo_db):
        svc = TelemetryService()
        svc.init_telemetry("f1")
        svc.update_telemetry("f1", battery_level=85.0)
        t1 = svc.get_telemetry("f1")
        assert t1.battery_level == 85.0
        assert t1.distance == 0

        svc.update_telemetry("f1", distance=12.5)
        t2 = svc.get_telemetry("f1")
        # battery preserved
        assert t2.battery_level == 85.0
        assert t2.distance == 12.5

    def test_update_with_no_args_is_noop(self, repo_db):
        svc = TelemetryService()
        svc.init_telemetry("f1")
        svc.update_telemetry("f1")
        t = svc.get_telemetry("f1")
        assert t.battery_level is None

    def test_get_nonexistent_returns_none(self, repo_db):
        svc = TelemetryService()
        assert svc.get_telemetry("no-flight") is None
