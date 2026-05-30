"""Unit tests for the configurable drone spawn (launch + re-spawn + validation).

The spawn point must stay >=3m from every wall of the garage world. These
cover the pure validation rule and the SimService spawn state/teleport
orchestration (gz set_pose is mocked).
"""
from unittest.mock import patch

from services.sim_service import (
    SimService,
    DEFAULT_SPAWN_POSE,
    SPAWN_BOUNDS,
    SPAWN_WORLD,
    validate_spawn,
)


class TestValidateSpawn:
    def test_center_and_edges_ok(self):
        assert validate_spawn(0, 0) == (True, None)
        assert validate_spawn(SPAWN_BOUNDS["xMax"], SPAWN_BOUNDS["yMax"])[0] is True
        assert validate_spawn(SPAWN_BOUNDS["xMin"], SPAWN_BOUNDS["yMin"])[0] is True

    def test_too_close_to_wall_rejected(self):
        assert validate_spawn(SPAWN_BOUNDS["xMax"] + 0.1, 0)[0] is False
        assert validate_spawn(0, SPAWN_BOUNDS["yMax"] + 0.1)[0] is False
        assert validate_spawn(SPAWN_BOUNDS["xMin"] - 0.1, 0)[0] is False

    def test_error_message_mentions_bounds(self):
        ok, err = validate_spawn(99, 99)
        assert ok is False
        assert "too close to a wall" in err


class TestLaunchSpawn:
    def test_custom_spawn_sets_pose(self):
        svc = SimService()
        # Stub out the actual subprocess launch; we only care about _spawn_pose.
        with patch.object(SimService, "stop"), \
             patch("services.sim_service.time.sleep"), \
             patch("services.sim_service.os.path.exists", return_value=True), \
             patch("services.sim_service.subprocess.Popen"), \
             patch("services.sim_service.threading.Thread"):
            svc.launch(world=SPAWN_WORLD, spawn={"x": 2.0, "y": 1.5})
            assert svc._spawn_pose == "2.0,1.5,0,0,0,0"

    def test_invalid_spawn_raises(self):
        svc = SimService()
        with patch.object(SimService, "stop"), \
             patch("services.sim_service.time.sleep"):
            try:
                svc.launch(world=SPAWN_WORLD, spawn={"x": 50, "y": 0})
                assert False, "expected ValueError"
            except ValueError as e:
                assert "too close to a wall" in str(e)

    def test_no_spawn_uses_default(self):
        svc = SimService()
        with patch.object(SimService, "stop"), \
             patch("services.sim_service.time.sleep"), \
             patch("services.sim_service.os.path.exists", return_value=True), \
             patch("services.sim_service.subprocess.Popen"), \
             patch("services.sim_service.threading.Thread"):
            svc.launch(world=SPAWN_WORLD)
            assert svc._spawn_pose == DEFAULT_SPAWN_POSE

    def test_custom_spawn_ignored_for_other_world(self):
        svc = SimService()
        with patch.object(SimService, "stop"), \
             patch("services.sim_service.time.sleep"), \
             patch("services.sim_service.os.path.exists", return_value=True), \
             patch("services.sim_service.subprocess.Popen"), \
             patch("services.sim_service.threading.Thread"):
            svc.launch(world="some_other_world", spawn={"x": 2.0, "y": 1.5})
            assert svc._spawn_pose == DEFAULT_SPAWN_POSE


class TestSetSpawn:
    def test_set_spawn_validates_and_updates_and_teleports(self):
        svc = SimService()
        svc._world = SPAWN_WORLD
        with patch.object(SimService, "_teleport_to",
                          return_value={"success": True, "model": "holybro_x500_0"}) as mock_tp:
            res = svc.set_spawn(3.0, 2.0)
            assert res["success"] is True
            assert res["spawn"] == {"x": 3.0, "y": 2.0}
            # Panic reset must now return to the NEW spot.
            assert svc._spawn_pose == "3.0,2.0,0,0,0,0"
            mock_tp.assert_called_once_with("3.0,2.0,0,0,0,0")

    def test_set_spawn_rejects_out_of_bounds_without_teleport(self):
        svc = SimService()
        svc._world = SPAWN_WORLD
        with patch.object(SimService, "_teleport_to") as mock_tp:
            res = svc.set_spawn(50.0, 0.0)
            assert res["success"] is False
            assert "too close to a wall" in res["error"]
            mock_tp.assert_not_called()

    def test_set_spawn_rejected_for_other_world(self):
        svc = SimService()
        svc._world = "some_other_world"
        res = svc.set_spawn(0.0, 0.0)
        assert res["success"] is False
        assert "not supported" in res["error"]

    def test_failed_teleport_does_not_update_spawn(self):
        svc = SimService()
        svc._world = SPAWN_WORLD
        svc._spawn_pose = DEFAULT_SPAWN_POSE
        with patch.object(SimService, "_teleport_to",
                          return_value={"success": False, "error": "no model"}):
            res = svc.set_spawn(3.0, 2.0)
            assert res["success"] is False
            assert svc._spawn_pose == DEFAULT_SPAWN_POSE  # unchanged


class TestSpawnProperty:
    def test_reflects_current_pose(self):
        svc = SimService()
        svc._spawn_pose = "1.5,-2.5,0,0,0,0"
        assert svc.spawn == {"x": 1.5, "y": -2.5}
