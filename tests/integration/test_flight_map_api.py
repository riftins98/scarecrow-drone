"""Integration tests for mission map static serving."""
from repositories import FlightRepository


def test_mission_map_serves_saved_png(api_client, tmp_path, monkeypatch):
    output_root = (tmp_path / "webapp" / "output").resolve()
    monkeypatch.setattr(
        "controllers.static_controller.OUTPUT_ROOT",
        str(output_root),
    )

    flight = FlightRepository().create()
    out = output_root / flight.id
    out.mkdir(parents=True)
    png = out / "map_annotated.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    repo = FlightRepository()
    repo.end_flight(
        flight.id,
        pigeons=0,
        frames=0,
        map_path=str(png.resolve()),
    )

    detail = api_client.get(f"/api/flights/{flight.id}")
    assert detail.json()["mapPath"] == str(png.resolve())

    response = api_client.get(f"/mission_maps/{flight.id}/map_annotated.png")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG")


def test_mission_map_404_without_file(api_client, tmp_path, monkeypatch):
    output_root = (tmp_path / "webapp" / "output").resolve()
    monkeypatch.setattr(
        "controllers.static_controller.OUTPUT_ROOT",
        str(output_root),
    )
    flight = FlightRepository().create()
    response = api_client.get(f"/mission_maps/{flight.id}/map_annotated.png")
    assert response.status_code == 404
