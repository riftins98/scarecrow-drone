"""Unit tests for DetectionService's stdout log parser.

The subprocess machinery in DetectionService is intentionally not unit-tested
(see tests/CLAUDE.md), but `_parse_log_extras` and `_phase_label` are pure
functions over a single string — exactly the kind of logic that should be
covered. Cases here match log lines still emitted by the remaining flight
scripts (`hangar_circuit_pursuit.py`, `sensor_check.py`, `room_circuit_map.py`).
"""
from services.detection_service import DetectionService, _phase_label, _parse_dist


def _parse(line: str) -> dict:
    """Run one line through the parser and return the resulting telemetry."""
    svc = DetectionService()
    svc._parse_log_extras(line)
    return svc.latest_telemetry


class TestPhaseLabel:
    def test_skips_filler_to_reach_the_noun(self):
        assert _phase_label("stabilize before hover") == "STABILIZE"
        assert _phase_label("hover near ceiling for 5.0s") == "HOVER"
        assert _phase_label("lidar-locked landing") == "LANDING"
        assert _phase_label("climb until ceiling clearance is 1.50m") == "CLIMB"

    def test_phase_banner_sets_phase_and_stops(self):
        tel = _parse("--- Phase 3: stabilize before landing ---")
        assert tel == {"phase": "STABILIZE"}


class TestVerticalReadouts:
    def test_agl(self):
        assert _parse("  [landing] descending agl=1.83m")["agl"] == 1.83


class TestLidarDistances:
    def test_labeled_family(self):
        tel = _parse("  Front: 1.2m  Left: 0.6m  Right: 0.8m")
        assert tel["front"] == 1.2
        assert tel["left"] == 0.6
        assert tel["right"] == 0.8

    def test_key_value_family(self):
        tel = _parse("  [descent] agl=1.83m  rear=0.50m  right=0.62m")
        assert tel["rear"] == 0.5
        assert tel["right"] == 0.62

    def test_wall_numeric_and_inf(self):
        assert _parse("  [  8.0s] wall=2.50m front=1.20m")["wall"] == 2.5
        # "inf" means no wall on that side -> None (rail hides it).
        assert _parse("  [ 12.5s] wall=inf descending alt=1.20m")["wall"] is None


class TestVelocity:
    def test_signed_components(self):
        tel = _parse("  [return] err=0.42m fwd=+0.30 right=-0.10")
        assert tel["fwd"] == 0.3


class TestParseDist:
    def test_inf_group_wins(self):
        assert _parse_dist("inf", None) is None

    def test_numeric_group(self):
        assert _parse_dist(None, "2.5") == 2.5

    def test_nothing_usable(self):
        assert _parse_dist(None, None) is None
