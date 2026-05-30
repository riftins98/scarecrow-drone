"""Integration tests for /api/sim/* routes."""
from unittest.mock import MagicMock, patch


def test_sim_status_when_disconnected(api_client):
    response = api_client.get("/api/sim/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["launching"] is False
    assert "log" in data
    assert "progress" in data


def test_sim_connect_triggers_launch(api_client):
    with patch("services.sim_service.SimService.launch") as mock_launch:
        mock_launch.return_value = True
        response = api_client.post("/api/sim/connect")
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_launch.assert_called_once()


def test_sim_connect_handles_exception(api_client):
    with patch("services.sim_service.SimService.launch", side_effect=RuntimeError("boom")):
        response = api_client.post("/api/sim/connect")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "boom" in data["error"]


def test_sim_disconnect(api_client):
    with patch("services.sim_service.SimService.stop") as mock_stop:
        response = api_client.delete("/api/sim/connect")
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_stop.assert_called_once()


def test_sim_reset_fails_when_not_connected(api_client):
    response = api_client.post("/api/sim/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not running" in data["error"].lower()


def test_sim_reset_orchestrates_kill_disarm_teleport(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.kill", return_value=True) as mock_kill, \
         patch("services.drone_service.DroneService.force_disarm", return_value=True) as mock_disarm, \
         patch("services.sim_service.SimService.reset_drone_pose",
               return_value={"success": True, "model": "holybro_x500_0"}) as mock_teleport:
        response = api_client.post("/api/sim/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["killedFlight"] is True
        assert data["disarmed"] is True
        assert data["teleport"]["model"] == "holybro_x500_0"
        mock_kill.assert_called_once()
        mock_disarm.assert_called_once()
        mock_teleport.assert_called_once()


def test_sim_reset_reports_teleport_failure(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.kill", return_value=False), \
         patch("services.drone_service.DroneService.force_disarm", return_value=False), \
         patch("services.sim_service.SimService.reset_drone_pose",
               return_value={"success": False, "error": "drone model not found in Gazebo"}):
        response = api_client.post("/api/sim/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"]
