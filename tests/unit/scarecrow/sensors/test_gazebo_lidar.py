"""Tests for GazeboLidar discovery logic. Does NOT spawn real gz subprocesses."""
from scarecrow.sensors.lidar.gazebo import GazeboLidar


class TestDiscoverTopic:
    def test_picks_scan_topic_from_list(self):
        lidar = GazeboLidar(env={"TEST": "1"})
        topic_list = "\n".join([
            "/world/default/model/holybro_x500/link/lidar_2d_v2/scan",
            "/world/default/model/holybro_x500/link/camera_link/image",
        ])
        result = lidar._discover_topic(topic_list=topic_list)
        assert result is not None
        assert "lidar_2d_v2/scan" in result

    def test_filters_out_points_topic(self):
        """Bug fix: must skip the /points variant (point cloud) and pick /scan."""
        lidar = GazeboLidar(env={"TEST": "1"})
        topic_list = "\n".join([
            "/world/default/model/holybro_x500/link/lidar_2d_v2/scan/points",
            "/world/default/model/holybro_x500/link/lidar_2d_v2/scan",
        ])
        result = lidar._discover_topic(topic_list=topic_list)
        assert result is not None
        assert "points" not in result
        assert result.endswith("scan")

    def test_returns_none_when_no_lidar_topic(self):
        lidar = GazeboLidar(env={"TEST": "1"})
        topic_list = "/world/default/model/holybro_x500/link/camera_link/sensor/camera/image"
        assert lidar._discover_topic(topic_list=topic_list) is None

    def test_empty_topic_list_returns_none(self):
        lidar = GazeboLidar(env={"TEST": "1"})
        assert lidar._discover_topic(topic_list="") is None
