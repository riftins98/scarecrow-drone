from textwrap import dedent
from unittest.mock import MagicMock, patch

from scarecrow.sensors.gz_entities import (
    GzPx4FrameTransform,
    choose_nearest_model,
    discover_model_name,
    discover_world_name,
    load_world_model_candidates,
    parse_pose_info,
    remove_model,
    remove_nearest_model,
)


def test_discover_world_name_from_topic_list():
    topics = "\n".join(
        [
            "/stats",
            "/world/hangar_lite/model/holybro_x500/link/base_link/pose",
            "/world/hangar_lite/model/pigeon_1/pose",
        ]
    )

    assert discover_world_name(topics) == "hangar_lite"


def test_discover_model_name_from_topic_list():
    topics = "\n".join(
        [
            "/world/hangar_lite/model/fixed_cam/link/camera_link/sensor/camera/image",
            "/world/hangar_lite/model/holybro_x500/link/base_link/pose",
        ]
    )

    assert discover_model_name(topics, contains="holybro") == "holybro_x500"


def test_parse_pose_info_reads_model_position_and_yaw():
    poses = parse_pose_info(
        dedent(
            """\
            pose {
              name: "holybro_x500"
              position {
                x: 4
                y: -3
                z: 0.25
              }
              orientation {
                x: 0
                y: 0
                z: 0.7071068
                w: 0.7071068
              }
            }
            pose {
              name: "pigeon_1::link"
              position { x: 99 y: 99 z: 0 }
            }
            pose {
              name: "pigeon_1"
              position {
                x: 10.5
                y: -3.5
                z: 2.5
              }
            }
            """
        )
    )

    assert poses["holybro_x500"].x == 4.0
    assert poses["holybro_x500"].y == -3.0
    assert abs(poses["holybro_x500"].yaw_deg - 90.0) < 0.01
    assert poses["pigeon_1"].x == 10.5
    assert "pigeon_1::link" not in poses


def test_frame_transform_maps_px4_point_to_gazebo_world():
    transform = GzPx4FrameTransform(
        px4_origin_x=1.0,
        px4_origin_y=2.0,
        px4_origin_yaw_deg=0.0,
        gz_origin_x=10.0,
        gz_origin_y=20.0,
        gz_origin_yaw_deg=90.0,
    )

    x, y = transform.px4_to_gz(2.0, 2.0)
    assert abs(x - 10.0) < 0.001
    assert abs(y - 21.0) < 0.001
    target = transform.estimate_target_gz_xy(
        local_x=1.0,
        local_y=2.0,
        yaw_deg=0.0,
        range_m=2.0,
    )
    assert abs(target[0] - 10.0) < 0.001
    assert abs(target[1] - 22.0) < 0.001


def test_load_world_model_candidates_filters_pigeons(tmp_path):
    worlds_dir = tmp_path
    (worlds_dir / "test_world.sdf").write_text(
        dedent(
            """\
            <sdf version="1.9">
              <world name="test_world">
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_1</name>
                  <pose>1 2 3 0 0 0</pose>
                </include>
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_2</name>
                  <pose>4 5 6 0 0 0</pose>
                </include>
                <include>
                  <uri>model://mono_cam_hd</uri>
                  <name>fixed_cam</name>
                  <pose>7 8 9 0 0 0</pose>
                </include>
              </world>
            </sdf>
            """
        )
    )

    candidates = load_world_model_candidates("test_world", worlds_dir=str(worlds_dir))

    assert [candidate.name for candidate in candidates] == ["pigeon_1", "pigeon_2"]
    assert candidates[0].x == 1.0
    assert candidates[0].y == 2.0
    assert candidates[0].z == 3.0


def test_choose_nearest_model_respects_max_distance(tmp_path):
    worlds_dir = tmp_path
    (worlds_dir / "test_world.sdf").write_text(
        dedent(
            """\
            <sdf version="1.9">
              <world name="test_world">
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_1</name>
                  <pose>0 0 0 0 0 0</pose>
                </include>
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_2</name>
                  <pose>10 0 0 0 0 0</pose>
                </include>
              </world>
            </sdf>
            """
        )
    )
    candidates = load_world_model_candidates("test_world", worlds_dir=str(worlds_dir))

    chosen = choose_nearest_model(candidates, x=8.0, y=0.0, max_distance_m=3.0)
    assert chosen is not None
    assert chosen[0].name == "pigeon_2"
    assert chosen[1] == 2.0

    assert choose_nearest_model(candidates, x=8.0, y=0.0, max_distance_m=1.0) is None


def test_remove_model_calls_gz_remove_service():
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "data: true\n"
    proc.stderr = ""

    with patch("subprocess.run", return_value=proc) as run:
        result = remove_model(
            world_name="hangar_lite",
            model_name="pigeon_1",
            env={"GZ_PARTITION": "px4"},
        )

    assert result.success is True
    assert result.model_name == "pigeon_1"
    cmd = run.call_args.args[0]
    assert "/world/hangar_lite/remove" in cmd
    assert 'name: "pigeon_1" type: MODEL' in cmd
    assert run.call_args.kwargs["env"] == {"GZ_PARTITION": "px4"}


def test_remove_nearest_model_removes_closest_candidate(tmp_path):
    worlds_dir = tmp_path
    (worlds_dir / "test_world.sdf").write_text(
        dedent(
            """\
            <sdf version="1.9">
              <world name="test_world">
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_1</name>
                  <pose>0 0 0 0 0 0</pose>
                </include>
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_2</name>
                  <pose>4 0 0 0 0 0</pose>
                </include>
              </world>
            </sdf>
            """
        )
    )

    live_poses = {
        "pigeon_1": MagicMock(name="pigeon_1", x=100.0, y=0.0, z=0.0),
        "pigeon_2": MagicMock(name="pigeon_2", x=3.8, y=0.0, z=0.0),
    }
    with patch("scarecrow.sensors.gz_entities.get_world_model_poses", return_value=live_poses), \
         patch("scarecrow.sensors.gz_entities.remove_model") as remove:
        remove.return_value = MagicMock(
            success=True,
            world_name="test_world",
            model_name="pigeon_2",
            message="data: true",
        )
        result = remove_nearest_model(
            world_name="test_world",
            x=3.5,
            y=0.0,
            env={},
            worlds_dir=str(worlds_dir),
        )

    assert result.success is True
    assert result.model_name == "pigeon_2"
    assert abs(result.distance_m - 0.3) < 0.001
    remove.assert_called_once()


def test_remove_nearest_model_does_not_require_distance_guard_for_multiple_targets(tmp_path):
    worlds_dir = tmp_path
    (worlds_dir / "test_world.sdf").write_text(
        dedent(
            """\
            <sdf version="1.9">
              <world name="test_world">
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_1</name>
                  <pose>0 0 0 0 0 0</pose>
                </include>
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_2</name>
                  <pose>20 0 0 0 0 0</pose>
                </include>
              </world>
            </sdf>
            """
        )
    )

    with patch("scarecrow.sensors.gz_entities.remove_model") as remove:
        remove.return_value = MagicMock(
            success=True,
            world_name="test_world",
            model_name="pigeon_2",
            message="data: true",
        )
        result = remove_nearest_model(
            world_name="test_world",
            x=100.0,
            y=0.0,
            env={},
            worlds_dir=str(worlds_dir),
        )

    assert result.success is True
    assert result.model_name == "pigeon_2"
    assert result.distance_m == 80.0
    remove.assert_called_once()


def test_remove_nearest_model_ignores_sdf_candidate_missing_from_live_poses(tmp_path):
    worlds_dir = tmp_path
    (worlds_dir / "test_world.sdf").write_text(
        dedent(
            """\
            <sdf version="1.9">
              <world name="test_world">
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_1</name>
                  <pose>0 0 0 0 0 0</pose>
                </include>
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_2</name>
                  <pose>10 0 0 0 0 0</pose>
                </include>
              </world>
            </sdf>
            """
        )
    )
    live_poses = {
        "pigeon_2": MagicMock(name="pigeon_2", x=10.0, y=0.0, z=0.0),
    }

    with patch("scarecrow.sensors.gz_entities.get_world_model_poses", return_value=live_poses), \
         patch("scarecrow.sensors.gz_entities.remove_model") as remove:
        remove.return_value = MagicMock(
            success=True,
            world_name="test_world",
            model_name="pigeon_2",
            message="data: true",
        )
        result = remove_nearest_model(
            world_name="test_world",
            x=0.0,
            y=0.0,
            env={},
            worlds_dir=str(worlds_dir),
        )

    assert result.success is True
    assert result.model_name == "pigeon_2"
    remove.assert_called_once()


def test_remove_nearest_model_removes_single_candidate_beyond_distance_guard(tmp_path):
    worlds_dir = tmp_path
    (worlds_dir / "hangar_lite.sdf").write_text(
        dedent(
            """\
            <sdf version="1.9">
              <world name="hangar_lite">
                <include>
                  <uri>model://pigeon_3d</uri>
                  <name>pigeon_1</name>
                  <pose>10.5 -3.5 2.5 0 0 0</pose>
                </include>
              </world>
            </sdf>
            """
        )
    )

    with patch("scarecrow.sensors.gz_entities.remove_model") as remove:
        remove.return_value = MagicMock(
            success=True,
            world_name="hangar_lite",
            model_name="pigeon_1",
            message="data: true",
        )
        result = remove_nearest_model(
            world_name="hangar_lite",
            x=4.287,
            y=-0.010,
            env={},
            worlds_dir=str(worlds_dir),
            max_distance_m=5.0,
        )

    assert result.success is True
    assert result.model_name == "pigeon_1"
    assert result.distance_m > 5.0
    remove.assert_called_once()
