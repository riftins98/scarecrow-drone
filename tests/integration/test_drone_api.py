"""Integration tests for /api/drone/* routes (ADD A.3)."""
from unittest.mock import patch


def test_drone_status_when_idle(api_client):
    response = api_client.get("/api/drone/status")
    assert response.status_code == 200
    data = response.json()
    assert data["isFlying"] is False
    assert data["mode"] == "idle"


def test_drone_start_fails_when_sim_not_running(api_client):
    response = api_client.post("/api/drone/start")
    assert response.status_code == 400
    assert "Simulation not running" in response.json()["detail"]


def test_drone_start_succeeds_with_mocked_sim(api_client):
    # Pretend sim is connected and detection.start succeeds
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start", return_value=True):
        response = api_client.post("/api/drone/start")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "flightId" in data


def test_drone_start_with_area_map_id(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start", return_value=True):
        response = api_client.post("/api/drone/start", json={"areaMapId": 5})
    assert response.status_code == 200


def test_drone_start_returns_500_when_detection_fails(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start", return_value=False):
        response = api_client.post("/api/drone/start")
    assert response.status_code == 500


def test_drone_stop_without_active_flight(api_client):
    response = api_client.post("/api/drone/stop")
    assert response.status_code == 400


def test_drone_abort_without_active_flight(api_client):
    response = api_client.post("/api/drone/abort")
    assert response.status_code == 400


def test_drone_return_home_returns_success(api_client):
    with patch("services.detection_service.DetectionService.stop"):
        response = api_client.post("/api/drone/return-home")
    assert response.status_code == 200


def test_drone_telemetry_returns_dict(api_client):
    response = api_client.get("/api/drone/telemetry")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
