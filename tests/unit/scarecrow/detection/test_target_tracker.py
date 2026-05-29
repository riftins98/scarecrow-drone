from scarecrow.controllers.target_pursuit import TargetObservation
from scarecrow.detection.tracking import TargetTracker


def test_tracker_stores_highest_confidence_detection():
    tracker = TargetTracker(image_width=1280)

    tracker.update_from_yolo([
        {"class": "target", "conf": 0.4, "center": (100, 200), "bbox": (1, 2, 3, 4)},
        {"class": "target", "conf": 0.9, "center": (500, 250), "bbox": (5, 6, 7, 8)},
    ])

    observation = tracker.latest()
    assert observation is not None
    assert observation.center_x == 500
    assert observation.center_y == 250
    assert observation.confidence == 0.9
    assert observation.bbox == (5, 6, 7, 8)


def test_tracker_reports_age():
    tracker = TargetTracker()
    tracker.update_from_yolo([
        {"class": "target", "conf": 0.9, "center": (500, 250), "bbox": (5, 6, 7, 8)},
    ])

    assert tracker.age >= 0.0


def test_tracker_returns_none_when_observation_is_stale():
    tracker = TargetTracker()
    tracker._observation = TargetObservation(
        center_x=500,
        center_y=250,
        image_width=1280,
        confidence=0.9,
        timestamp=10.0,
    )

    assert tracker.latest(max_age_s=1.0, now=12.0) is None
    assert tracker.latest(max_age_s=3.0, now=12.0) is not None
