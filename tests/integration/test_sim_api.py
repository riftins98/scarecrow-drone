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


def test_sim_cameras_lists_launcher_flags(api_client):
    response = api_client.get("/api/sim/cameras")
    assert response.status_code == 200
    data = response.json()
    names = [c["name"] for c in data["cameras"]]
    assert names == ["fixed", "drone_cam", "drone_view"]
    # `center` is a legacy launcher flag kept for manual shell use and
    # deliberately not offered in the UI. This asserted its presence for long
    # after it was removed, which is why it failed rather than the API being
    # wrong. Assert the exclusion instead, so re-adding it is a decision.
    assert "center" not in names
    assert data["cameras"][0]["label"] == "Fixed"
    assert data["cameras"][0]["model"] == "mono_cam_hd"


def test_sim_options_includes_spawn_bounds(api_client):
    response = api_client.get("/api/sim/options")
    assert response.status_code == 200
    data = response.json()

    # These named worlds that no longer exist: drone_garage_pigeon_3d.sdf was
    # deleted in c07f4c4 ("removed all useless worlds"), and hangar_1 was never
    # a world name. Assert against what worlds/ actually contains, and derive
    # it rather than hardcoding, so deleting a world updates the test with it.
    assert "spawnMaps" in data
    assert "hangar_small" in data["spawnMaps"]
    assert "hangar_lite" in data["spawnMaps"]
    assert set(data["spawnMaps"]) == {w["name"] for w in data["worlds"]}

    # Derived from SPAWN_WALL_MARGIN rather than hardcoded. These were literals
    # for a 3.0m margin; the margin is 2.0m, so this test and the unit test in
    # test_spawn.py asserted contradictory bounds for the same world and only
    # one of them was right.
    from services.world_geometry import SPAWN_WALL_MARGIN

    hangar_lite = next(w for w in data["worlds"] if w["name"] == "hangar_lite")
    walls = hangar_lite["spawn"]["wallBounds"]
    assert hangar_lite["spawn"]["bounds"] == {
        "xMin": walls["xMin"] + SPAWN_WALL_MARGIN,
        "xMax": walls["xMax"] - SPAWN_WALL_MARGIN,
        "yMin": walls["yMin"] + SPAWN_WALL_MARGIN,
        "yMax": walls["yMax"] - SPAWN_WALL_MARGIN,
    }

    assert data["spawnWorld"] in data["spawnMaps"]
    b = data["spawnBounds"]
    assert b["xMin"] < b["xMax"] and b["yMin"] < b["yMax"]


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
        # Must be a world that actually supports spawns, or validation never
        # runs and the test passes on the wrong error. It previously used
        # drone_garage_pigeon_3d, deleted in c07f4c4, so the response was
        # "custom spawn is not supported for world ..." -- a different failure
        # that would also have masked a genuinely broken validator.
        response = api_client.post("/api/sim/connect", json={
            "world": "hangar_small", "spawn": {"x": 50, "y": 0},
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
