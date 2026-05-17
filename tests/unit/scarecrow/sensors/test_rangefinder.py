"""Tests for single-ray Gazebo rangefinder support."""

from scarecrow.sensors.rangefinder import GazeboRangefinder


class TestGazeboRangefinder:
    def test_discovers_ceiling_rangefinder_scan_topic(self):
        rangefinder = GazeboRangefinder(env={"TEST": "1"})
        topic_list = "\n".join(
            [
                "/world/hangar_1/model/holybro_x500/link/lidar_2d_v2/scan",
                "/world/hangar_1/model/holybro_x500/link/tf_luna_up_link/sensor/ceiling_rangefinder/scan",
            ]
        )

        result = rangefinder._discover_topic(topic_list=topic_list)

        assert result is not None
        assert result.endswith("ceiling_rangefinder/scan")

    def test_filters_out_points_topic(self):
        rangefinder = GazeboRangefinder(env={"TEST": "1"})
        topic_list = "\n".join(
            [
                "/world/hangar_1/model/holybro_x500/link/tf_luna_up_link/sensor/ceiling_rangefinder/scan/points",
                "/world/hangar_1/model/holybro_x500/link/tf_luna_up_link/sensor/ceiling_rangefinder/scan",
            ]
        )

        result = rangefinder._discover_topic(topic_list=topic_list)

        assert result is not None
        assert "points" not in result

    def test_parse_single_range_reading(self):
        reading = GazeboRangefinder._parse_reading(
            """
            header {
              stamp {
                sec: 1
              }
            }
            ranges: 2.75
            """
        )

        assert reading is not None
        assert reading.distance_m == 2.75

    def test_parse_invalid_reading_returns_none(self):
        assert GazeboRangefinder._parse_reading("ranges: invalid") is None
        assert GazeboRangefinder._parse_reading("ranges: 0") is None
        assert GazeboRangefinder._parse_reading("ranges: inf") is None
        assert GazeboRangefinder._parse_reading("ranges: nan") is None
