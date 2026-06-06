"""Integration tests for mission map image endpoint."""
import json

from repositories import FlightRepository


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


def test_flight_map_image_renders_png(api_client, tmp_path, monkeypatch):
    output_root = tmp_path / "webapp" / "output"
    monkeypatch.setattr(
        "webapp.backend.services.mission_map_service.OUTPUT_ROOT",
        output_root.resolve(),
    )

    repo = FlightRepository()
    flight = repo.create()
    flight_dir = output_root / flight.id
    flight_dir.mkdir(parents=True)
    map_path = flight_dir / "map.json"
    map_path.write_text(json.dumps(MINIMAL_MAP))
    repo.end_flight(
        flight.id,
        pigeons=0,
        frames=0,
        map_json_path=str(map_path.resolve()),
    )

    detail = api_client.get(f"/api/flights/{flight.id}")
    assert detail.status_code == 200
    assert detail.json()["mapJsonPath"] == str(map_path.resolve())

    image = api_client.get(f"/api/flights/{flight.id}/map/image")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_flight_map_image_404_without_map(api_client):
    repo = FlightRepository()
    flight = repo.create()
    repo.end_flight(flight.id, pigeons=0, frames=0)

    response = api_client.get(f"/api/flights/{flight.id}/map/image")
    assert response.status_code == 404
