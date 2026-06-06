"""Unit tests for on-demand mission map rendering."""
import json

import pytest

from scarecrow.navigation.map_unit import MapUnit
from webapp.backend.services.mission_map_service import (
    render_flight_map_png,
    validate_map_json_path,
)


MINIMAL_MAP = {
    "boundaries": [
        {"x": 0.0, "y": 0.0},
        {"x": 10.0, "y": 0.0},
        {"x": 10.0, "y": 8.0},
        {"x": 0.0, "y": 8.0},
    ],
    "route": [],
    "points": [],
    "wall_points": [],
    "takeoff_point": {"x": 1.0, "y": 1.0},
}


class TestMapUnitRenderBytes:
    def test_render_annotated_png_bytes_returns_png(self, tmp_path):
        map_path = tmp_path / "map.json"
        map_path.write_text(json.dumps(MINIMAL_MAP))
        data = MapUnit.render_annotated_png_bytes(map_path)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"


class TestMissionMapService:
    def test_validate_rejects_path_outside_flight_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "webapp.backend.services.mission_map_service.OUTPUT_ROOT",
            tmp_path / "webapp" / "output",
        )
        outside = tmp_path / "evil" / "map.json"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}")
        with pytest.raises(ValueError):
            validate_map_json_path("flight1", str(outside))

    def test_render_flight_map_png(self, tmp_path, monkeypatch):
        output_root = tmp_path / "webapp" / "output"
        monkeypatch.setattr(
            "webapp.backend.services.mission_map_service.OUTPUT_ROOT",
            output_root.resolve(),
        )
        flight_dir = output_root / "abc"
        flight_dir.mkdir(parents=True)
        map_path = flight_dir / "map.json"
        map_path.write_text(json.dumps(MINIMAL_MAP))
        png = render_flight_map_png("abc", str(map_path))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
