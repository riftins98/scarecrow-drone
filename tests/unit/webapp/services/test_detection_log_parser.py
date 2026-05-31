"""Unit tests for DetectionService's stdout log parser.

The subprocess machinery in DetectionService is intentionally not unit-tested
(see tests/CLAUDE.md), but `_parse_log_extras` and `_phase_label` are pure
functions over a single string — exactly the kind of logic that should be
covered. These guard the regexes against drift in the flight scripts' log
wording, which is the whole contract the telemetry rail depends on.
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
        assert _parse("  [descent] agl=1.83m  (no lidar)")["agl"] == 1.83

    def test_ceiling_clearance_variants(self):
        assert _parse("  Target ceiling clearance reached: 1.50m")["ceiling"] == 1.5
        assert _parse("ceiling clearance 1.20 m")["ceiling"] == 1.2

    def test_leg_complete_only(self):
        # Per design, only "Leg N complete" counts; the v2 start-of-leg banner
        # "--- Leg 1/4 ---" is intentionally NOT matched.
        assert _parse("  Leg 2 complete (31.4s)")["leg"] == 2
        assert "leg" not in _parse("--- Leg 1/4 (speed=0.30 m/s) ---")


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
        tel = _parse("  [ 8.0s] fwd=+0.30 lat=-0.10 yaw=+5.0")
        assert tel["fwd"] == 0.3
        assert tel["lat"] == -0.1
        assert tel["yaw"] == 5.0


class TestOutcomes:
    def test_target_reached_with_distance(self):
        tel = _parse("  *** TARGET REACHED! Front distance: 1.45m ***")
        assert tel["target"] == "REACHED"
        assert tel["target_dist"] == 1.45

    def test_pursuit_ended_reason(self):
        assert _parse("  Pursuit ended: target_lost")["target"] == "TARGET LOST"

    def test_wall_follow_stop_reason(self):
        assert _parse("Wall follow stopped: front_wall")["stop_reason"] == "FRONT WALL"

    def test_fps(self):
        assert _parse("  FPS: 12.34")["fps"] == 12.3


class TestParseDist:
    def test_inf_group_wins(self):
        assert _parse_dist("inf", None) is None

    def test_numeric_group(self):
        assert _parse_dist(None, "2.5") == 2.5

    def test_nothing_usable(self):
        assert _parse_dist(None, None) is None
