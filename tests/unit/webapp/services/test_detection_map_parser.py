"""Unit tests for MAP_RESULT stdout parsing."""
from webapp.backend.services.detection_service import (
    parse_map_result_line,
    resolve_map_json_path_for_flight,
)


class TestParseMapResultLine:
    def test_parses_map_path(self):
        line = 'MAP_RESULT:{"map_path": "/tmp/flight/map.json"}'
        assert parse_map_result_line(line) == "/tmp/flight/map.json"

    def test_parses_map_json_path_alias(self):
        line = 'MAP_RESULT:{"map_json_path": "/data/map.json"}'
        assert parse_map_result_line(line) == "/data/map.json"

    def test_ignores_invalid_json(self):
        assert parse_map_result_line("MAP_RESULT:not-json") is None

    def test_ignores_unrelated_lines(self):
        assert parse_map_result_line("VIDEO_PATH:/tmp/v.mp4") is None


class TestResolveMapJsonPathForFlight:
    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "webapp.backend.services.detection_service.REPO_ROOT",
            str(tmp_path),
        )
        assert resolve_map_json_path_for_flight("abc123") is None

    def test_finds_map_json_on_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "webapp.backend.services.detection_service.REPO_ROOT",
            str(tmp_path),
        )
        flight_dir = tmp_path / "webapp" / "output" / "flight1"
        flight_dir.mkdir(parents=True)
        map_file = flight_dir / "map.json"
        map_file.write_text("{}")
        resolved = resolve_map_json_path_for_flight("flight1")
        assert resolved == str(map_file.resolve())
