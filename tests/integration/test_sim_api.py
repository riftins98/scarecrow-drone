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
         patch("services.sim_service.SimService.disarm_via_console", return_value=True) as mock_disarm, \
         patch("services.sim_service.SimService.reset_drone_pose",
               return_value={"success": True, "model": "holybro_x500_0"}) as mock_teleport, \
         patch("services.sim_service.SimService.reset_drone_values_via_console",
               return_value={"ekfOrigin": True, "heading": True,
                             "disarmed": True}) as mock_values:
        response = api_client.post("/api/sim/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["killedFlight"] is True
        assert data["disarmed"] is True
        assert data["teleport"]["model"] == "holybro_x500_0"
        assert data["droneValues"] == {
            "ekfOrigin": True, "heading": True, "disarmed": True,
        }
        mock_kill.assert_called_once()
        mock_disarm.assert_called_once()
        mock_teleport.assert_called_once()
        mock_values.assert_called_once()


def test_sim_options_includes_spawn_bounds(api_client):
    response = api_client.get("/api/sim/options")
    assert response.status_code == 200
    data = response.json()

    assert "spawnMaps" in data
    assert "drone_garage_pigeon_3d" in data["spawnMaps"]
    assert "hangar_1" in data["spawnMaps"]
    assert "hangar_lite" in data["spawnMaps"]

    hangar_lite = next(w for w in data["worlds"] if w["name"] == "hangar_lite")
    assert hangar_lite["spawn"]["bounds"] == {
        "xMin": 3.0, "xMax": 9.0, "yMin": -4.5, "yMax": -2.5,
    }

    assert data["spawnWorld"] == "drone_garage_pigeon_3d"
    b = data["spawnBounds"]
    assert b["xMin"] == -9.0 and b["xMax"] == 9.0
    assert b["yMin"] == -4.5 and b["yMax"] == 4.5


def test_sim_connect_passes_spawn_to_launch(api_client):
    with patch("services.sim_service.SimService.launch") as mock_launch:
        mock_launch.return_value = True
        response = api_client.post("/api/sim/connect", json={
            "world": "drone_garage_pigeon_3d", "spawn": {"x": 2.0, "y": 1.0},
        })
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert mock_launch.call_args.kwargs["spawn"] == {"x": 2.0, "y": 1.0}


def test_sim_connect_invalid_spawn_reports_error(api_client):
    # The real launch() validates; a bad spawn should surface as success:false.
    with patch("services.sim_service.SimService.stop"):
        response = api_client.post("/api/sim/connect", json={
            "world": "drone_garage_pigeon_3d", "spawn": {"x": 50, "y": 0},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "too close to a wall" in data["error"]


def test_sim_spawn_fails_when_not_connected(api_client):
    response = api_client.post("/api/sim/spawn", json={"x": 1.0, "y": 1.0})
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "not running" in response.json()["error"].lower()


def test_sim_spawn_teleports_when_connected(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.sim_service.SimService.set_spawn",
               return_value={"success": True, "spawn": {"x": 1.0, "y": 1.0},
                             "model": "holybro_x500_0"}) as mock_set:
        response = api_client.post("/api/sim/spawn", json={"x": 1.0, "y": 1.0})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["spawn"] == {"x": 1.0, "y": 1.0}
        mock_set.assert_called_once_with(1.0, 1.0)


def test_sim_reset_reports_teleport_failure(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.kill", return_value=False), \
         patch("services.sim_service.SimService.disarm_via_console", return_value=False), \
         patch("services.sim_service.SimService.reset_drone_pose",
               return_value={"success": False,
                             "error": "drone model not found in Gazebo"}), \
         patch("services.sim_service.SimService.reset_drone_values_via_console",
               return_value={"ekfOrigin": True, "heading": True,
                             "disarmed": True}):
        response = api_client.post("/api/sim/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"]
        assert data["droneValues"]["heading"] is True


def test_sim_reset_reports_drone_value_failure(api_client):
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.kill", return_value=True), \
         patch("services.sim_service.SimService.disarm_via_console", return_value=True), \
         patch("services.sim_service.SimService.reset_drone_pose",
               return_value={"success": True, "model": "holybro_x500_0"}), \
         patch("services.sim_service.SimService.reset_drone_values_via_console",
               return_value={"ekfOrigin": True, "heading": False,
                             "disarmed": True}):
        response = api_client.post("/api/sim/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "drone values" in data["error"]
        assert data["teleport"]["success"] is True
