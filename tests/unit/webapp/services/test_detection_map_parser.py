"""Unit tests for MAP_RESULT stdout parsing."""
from webapp.backend.services.detection_service import (
    parse_map_result_line,
    resolve_map_path_for_flight,
)


class TestParseMapResultLine:
    def test_parses_map_path_png(self):
        line = 'MAP_RESULT:{"map_path": "/tmp/flight/map_annotated.png"}'
        assert parse_map_result_line(line) == "/tmp/flight/map_annotated.png"

    def test_ignores_json_map_path(self):
        line = 'MAP_RESULT:{"map_path": "/data/map.json"}'
        assert parse_map_result_line(line) is None

    def test_ignores_invalid_json(self):
        assert parse_map_result_line("MAP_RESULT:not-json") is None


class TestResolveMapPathForFlight:
    def test_missing_file_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "webapp.backend.services.detection_service.REPO_ROOT",
            "/nonexistent",
        )
        assert resolve_map_path_for_flight("abc123") is None

    def test_finds_png_on_disk(self, tmp_path, monkeypatch):
        flight_dir = tmp_path / "webapp" / "output" / "flight1"
        flight_dir.mkdir(parents=True)
        png = flight_dir / "map_annotated.png"
        png.write_bytes(b"\x89PNG\r\n")

        monkeypatch.setattr(
            "webapp.backend.services.detection_service.REPO_ROOT",
            str(tmp_path),
        )
        resolved = resolve_map_path_for_flight("flight1")
        assert resolved == str(png.resolve())
