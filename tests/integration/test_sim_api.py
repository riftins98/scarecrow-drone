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
