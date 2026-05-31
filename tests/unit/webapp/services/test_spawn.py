"""Unit tests for configurable drone spawn maps and validation.

The spawn point must stay >=3m from every wall and clear of static obstacles.
These cover SDF-derived world maps, pure validation, and the SimService
spawn state/teleport orchestration (gz set_pose is mocked).
"""
from unittest.mock import patch

from services.sim_service import (
    SimService,
    DEFAULT_SPAWN_POSE,
    SPAWN_BOUNDS,
    SPAWN_WORLD,
    SPAWN_OBSTACLES,
    validate_spawn,
)
from services.world_geometry import all_spawn_maps, spawn_map_for_world

# A point that is inside the valid box AND clear of both parked aircraft.
# (The room center is occupied by the two Shadow aircraft, so tests must use a
# corner.) Corners like (-8, 4) / (8, 4) are clear.
CLEAR = (-8.0, 4.0)


class TestWorldGeometry:
    def test_all_worlds_with_floor_get_spawn_maps(self):
        maps = all_spawn_maps()
        assert "drone_garage_pigeon_3d" in maps
        assert "hangar_1" in maps
        assert "hangar_lite" in maps

    def test_garage_map_has_dynamic_aircraft_obstacles(self):
        info = spawn_map_for_world("drone_garage_pigeon_3d")
        assert info is not None
        assert info["wallBounds"] == {
            "xMin": -12.0, "xMax": 12.0, "yMin": -7.5, "yMax": 7.5,
        }
        assert info["bounds"] == {
            "xMin": -9.0, "xMax": 9.0, "yMin": -4.5, "yMax": 4.5,
        }
        assert len(info["obstacles"]) == 2
        assert {o["label"] for o in info["obstacles"]} == {"shadow_1", "shadow_2"}

    def test_hangar_lite_map_uses_its_own_floor(self):
        info = spawn_map_for_world("hangar_lite")
        assert info is not None
        assert info["wallBounds"] == {
            "xMin": 0.0, "xMax": 12.0, "yMin": -7.5, "yMax": 0.5,
        }
        assert info["bounds"] == {
            "xMin": 3.0, "xMax": 9.0, "yMin": -4.5, "yMax": -2.5,
        }
        assert info["obstacles"] == []


class TestValidateSpawn:
    def test_clear_corners_ok(self):
        assert validate_spawn(-8.0, 4.0) == (True, None)
        assert validate_spawn(8.0, 4.0)[0] is True
        # The far corners of the valid box are clear of the central aircraft.
        assert validate_spawn(SPAWN_BOUNDS["xMin"], SPAWN_BOUNDS["yMax"])[0] is True
        assert validate_spawn(SPAWN_BOUNDS["xMin"], SPAWN_BOUNDS["yMin"])[0] is True

    def test_too_close_to_wall_rejected(self):
        assert validate_spawn(SPAWN_BOUNDS["xMax"] + 0.1, 4.0)[0] is False
        assert validate_spawn(-8.0, SPAWN_BOUNDS["yMax"] + 0.1)[0] is False
        assert validate_spawn(SPAWN_BOUNDS["xMin"] - 0.1, 4.0)[0] is False

    def test_on_aircraft_rejected(self):
        # Both aircraft centers (and the room center between them) are blocked.
        for obs in SPAWN_OBSTACLES:
            ok, err = validate_spawn(obs["cx"], obs["cy"])
            assert ok is False
            assert obs["label"] in err
        assert validate_spawn(0.0, 0.0)[0] is False  # center, between the craft

    def test_error_message_mentions_bounds(self):
        ok, err = validate_spawn(99, 99)
        assert ok is False
        assert "too close to a wall" in err

    def test_other_mapped_world_uses_its_own_bounds(self):
        assert validate_spawn(6.0, -3.5, world="hangar_lite") == (True, None)
        ok, err = validate_spawn(1.0, -3.5, world="hangar_lite")
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
            svc.launch(world=SPAWN_WORLD, spawn={"x": -8.0, "y": 4.0})
            assert svc._spawn_pose == "-8.0,4.0,0,0,0,0"

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

    def test_custom_spawn_sets_pose_for_other_mapped_world(self):
        svc = SimService()
        with patch.object(SimService, "stop"), \
             patch("services.sim_service.time.sleep"), \
             patch("services.sim_service.os.path.exists", return_value=True), \
             patch("services.sim_service.subprocess.Popen"), \
             patch("services.sim_service.threading.Thread"):
            svc.launch(world="hangar_lite", spawn={"x": 6.0, "y": -3.5})
            assert svc._spawn_pose == "6.0,-3.5,0,0,0,0"

    def test_custom_spawn_rejected_for_unsupported_world(self):
        svc = SimService()
        with patch.object(SimService, "stop"), \
             patch("services.sim_service.time.sleep"):
            try:
                svc.launch(world="some_other_world", spawn={"x": -8.0, "y": 4.0})
                assert False, "expected ValueError"
            except ValueError as e:
                assert "not supported" in str(e)


class TestSetSpawn:
    def test_set_spawn_validates_and_updates_and_teleports(self):
        svc = SimService()
        svc._world = SPAWN_WORLD
        with patch.object(SimService, "_teleport_to",
                          return_value={"success": True, "model": "holybro_x500_0"}) as mock_tp:
            res = svc.set_spawn(-8.0, 4.0)
            assert res["success"] is True
            assert res["spawn"] == {"x": -8.0, "y": 4.0}
            # Panic reset must now return to the NEW spot.
            assert svc._spawn_pose == "-8.0,4.0,0,0,0,0"
            mock_tp.assert_called_once_with("-8.0,4.0,0,0,0,0")

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
            res = svc.set_spawn(-8.0, 4.0)
            assert res["success"] is False
            assert svc._spawn_pose == DEFAULT_SPAWN_POSE  # unchanged


class TestSpawnProperty:
    def test_reflects_current_pose(self):
        svc = SimService()
        svc._spawn_pose = "1.5,-2.5,0,0,0,0"
        assert svc.spawn == {"x": 1.5, "y": -2.5}


class TestDronePose:
    SAMPLE = (
        "Name: holybro_x500_0\n"
        "  - Pose [ XYZ (m) ] [ RPY (rad) ]:\n"
        "  - [5.00 -4.50 0.20]\n"
        "  - [0.00 0.00 1.5708]\n"
    )

    def test_parses_xy_and_heading(self):
        from unittest.mock import MagicMock
        svc = SimService()
        with patch.object(SimService, "is_connected", True), \
             patch.object(SimService, "_discover_drone_model", return_value="holybro_x500_0"), \
             patch("services.sim_service.subprocess.run",
                   return_value=MagicMock(stdout=self.SAMPLE)):
            pose = svc.drone_pose()
            assert pose == {"x": 5.0, "y": -4.5, "heading": 90.0}

    def test_none_when_unparseable(self):
        from unittest.mock import MagicMock
        svc = SimService()
        with patch.object(SimService, "is_connected", True), \
             patch.object(SimService, "_discover_drone_model", return_value="holybro_x500_0"), \
             patch("services.sim_service.subprocess.run",
                   return_value=MagicMock(stdout="no pose here")):
            assert svc.drone_pose() is None

    def test_none_when_not_connected(self):
        svc = SimService()
        with patch.object(SimService, "is_connected", False):
            assert svc.drone_pose() is None
