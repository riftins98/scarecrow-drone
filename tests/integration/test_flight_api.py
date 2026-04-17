"""Integration tests for /api/flights/* routes (ADD A.4)."""
from unittest.mock import patch

from repositories import FlightRepository, TelemetryRepository
from dtos import TelemetryCreateDTO


def test_list_flights_empty(api_client):
    response = api_client.get("/api/flights")
    assert response.status_code == 200
    assert response.json() == []


def test_get_nonexistent_flight_returns_404(api_client):
    response = api_client.get("/api/flights/no-such-id")
    assert response.status_code == 404


def test_list_flights_returns_camelcase(api_client):
    FlightRepository().create()
    response = api_client.get("/api/flights")
    assert response.status_code == 200
    flights = response.json()
    assert len(flights) == 1
    f = flights[0]
    # Frontend expects camelCase
    assert "pigeonsDetected" in f
    assert "framesProcessed" in f
    assert "startTime" in f
    assert "endTime" in f
    assert "videoPath" in f
    assert "areaMapId" in f


def test_get_flight_detail(api_client):
    flight = FlightRepository().create()
    response = api_client.get(f"/api/flights/{flight.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == flight.id
    assert data["status"] == "in_progress"


def test_get_flight_summary(api_client):
    flight = FlightRepository().create()
    response = api_client.get(f"/api/flights/{flight.id}/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["flight_id"] == flight.id
    assert data["total_detections"] == 0


def test_get_summary_nonexistent_returns_404(api_client):
    response = api_client.get("/api/flights/no-such/summary")
    assert response.status_code == 404


def test_get_flight_telemetry(api_client):
    flight = FlightRepository().create()
    TelemetryRepository().create(TelemetryCreateDTO(
        flight_id=flight.id, battery_level=80.0, distance=12.5, detections=3
    ))
    response = api_client.get(f"/api/flights/{flight.id}/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert data["battery_level"] == 80.0
    assert data["distance"] == 12.5
    assert data["detections"] == 3


def test_get_telemetry_nonexistent_returns_404(api_client):
    response = api_client.get("/api/flights/no-such/telemetry")
    assert response.status_code == 404


def test_get_flight_images_empty(api_client):
    flight = FlightRepository().create()
    response = api_client.get(f"/api/flights/{flight.id}/images")
    assert response.status_code == 200
    assert response.json() == {"images": []}


def test_get_flight_recording(api_client):
    flight = FlightRepository().create()
    response = api_client.get(f"/api/flights/{flight.id}/recording")
    assert response.status_code == 200
    # video_path is None until flight completes
    assert response.json()["recording"] is None


def test_delete_flight(api_client):
    flight = FlightRepository().create()
    response = api_client.delete(f"/api/flights/{flight.id}")
    assert response.status_code == 200
    assert response.json()["success"] is True
    # Now 404
    assert api_client.get(f"/api/flights/{flight.id}").status_code == 404


def test_delete_nonexistent_returns_404(api_client):
    response = api_client.delete("/api/flights/no-such")
    assert response.status_code == 404


# Legacy endpoints (kept for current frontend compatibility)


def test_legacy_flight_start_without_sim_fails(api_client):
    response = api_client.post("/api/flight/start")
    assert response.status_code == 400


def test_legacy_flight_start_with_mocked_sim(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start", return_value=True):
        response = api_client.post("/api/flight/start")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_legacy_flight_stop_without_active_flight(api_client):
    response = api_client.post("/api/flight/stop")
    assert response.status_code == 400


def test_legacy_flight_status(api_client):
    response = api_client.get("/api/flight/status")
    assert response.status_code == 200
    data = response.json()
    assert "isFlying" in data
    assert "isConnected" in data
