"""UT-10..11: YoloDetector tests (ADD Section 5.4). Mocks ultralytics."""
from unittest.mock import MagicMock

import numpy as np

from scarecrow.detection.yolo import YoloDetector


def _mock_detection_result(conf=0.9):
    mock_box = MagicMock()
    mock_box.xyxy = [MagicMock(tolist=MagicMock(return_value=[10, 10, 100, 100]))]
    mock_box.conf = [MagicMock(__float__=lambda s: conf)]
    mock_box.cls = [MagicMock(__int__=lambda s: 0)]
    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    return mock_result


class TestYoloDetector:
    def test_rate_limiting_skips_within_interval(self, tmp_path):
        """UT-10: Skips frames that arrive within min_interval seconds."""
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            min_interval=1.0,
        )
        # Mock the model so no real inference runs
        mock_result = MagicMock()
        mock_result.boxes = None
        det._model = MagicMock(return_value=[mock_result])
        det._model.names = {}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)
        assert det.frames_processed == 1
        det.process_frame(frame)  # within interval -- skipped
        assert det.frames_processed == 1

    def test_callback_fires_on_detection(self, tmp_path):
        """UT-11: on_detection callback is called with image path when bird found."""
        callback = MagicMock()
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            on_detection=callback,
        )

        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock(tolist=MagicMock(return_value=[10, 10, 100, 100]))]
        mock_box.conf = [MagicMock(__float__=lambda s: 0.9)]
        mock_box.cls = [MagicMock(__int__=lambda s: 0)]
        mock_result = MagicMock()
        mock_result.boxes = [mock_box]
        det._model = MagicMock(return_value=[mock_result])
        det._model.names = {0: "pigeon"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)
        assert callback.called
        call_arg = callback.call_args[0][0]
        assert "detection" in call_arg

    def test_detection_data_callback_receives_detections(self, tmp_path):
        data_callback = MagicMock()
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            on_detection_data=data_callback,
        )

        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock(tolist=MagicMock(return_value=[10, 10, 100, 100]))]
        mock_box.conf = [MagicMock(__float__=lambda s: 0.9)]
        mock_box.cls = [MagicMock(__int__=lambda s: 0)]
        mock_result = MagicMock()
        mock_result.boxes = [mock_box]
        det._model = MagicMock(return_value=[mock_result])
        det._model.names = {0: "pigeon"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)

        data_callback.assert_called_once()
        detections = data_callback.call_args[0][0]
        assert detections[0]["class"] == "pigeon"
        assert detections[0]["center"] == (55, 55)

    def test_target_classes_filters_non_target_detections(self, tmp_path):
        data_callback = MagicMock()
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            min_interval=0.0,
            on_detection_data=data_callback,
            target_classes=("bird",),
        )

        person_box = MagicMock()
        person_box.xyxy = [MagicMock(tolist=MagicMock(return_value=[10, 10, 100, 100]))]
        person_box.conf = [MagicMock(__float__=lambda s: 0.95)]
        person_box.cls = [MagicMock(__int__=lambda s: 0)]

        bird_box = MagicMock()
        bird_box.xyxy = [MagicMock(tolist=MagicMock(return_value=[40, 20, 140, 120]))]
        bird_box.conf = [MagicMock(__float__=lambda s: 0.8)]
        bird_box.cls = [MagicMock(__int__=lambda s: 1)]

        mock_result = MagicMock()
        mock_result.boxes = [person_box, bird_box]
        det._model = MagicMock(return_value=[mock_result])
        det._model.names = {0: "person", 1: "bird"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)

        data_callback.assert_called_once()
        detections = data_callback.call_args[0][0]
        assert len(detections) == 1
        assert detections[0]["class"] == "bird"
        assert detections[0]["center"] == (90, 70)

    def test_no_detection_log_explains_target_class_filter(self, tmp_path, capsys):
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            min_interval=0.0,
            confidence=0.70,
            target_classes=("bird", "pigeon"),
        )

        person_box = MagicMock()
        person_box.xyxy = [MagicMock(tolist=MagicMock(return_value=[10, 10, 100, 100]))]
        person_box.conf = [MagicMock(__float__=lambda s: 0.85)]
        person_box.cls = [MagicMock(__int__=lambda s: 0)]

        mock_result = MagicMock()
        mock_result.boxes = [person_box]
        det._model = MagicMock(return_value=[mock_result])
        det._model.names = {0: "person"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)

        output = capsys.readouterr().out
        assert "no detections" in output
        assert "best candidate 85%" in output
        assert "threshold 70%" in output
        assert "not in target_classes=[bird, pigeon]" in output

    def test_no_callback_when_no_detections(self, tmp_path):
        callback = MagicMock()
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            on_detection=callback,
        )
        mock_result = MagicMock()
        mock_result.boxes = []
        det._model = MagicMock(return_value=[mock_result])
        det._model.names = {}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)
        assert not callback.called

    def test_not_running_skips_processing(self, tmp_path):
        det = YoloDetector(model_path="fake.pt", output_dir=str(tmp_path))
        det._model = MagicMock()
        # running == False by default
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)
        assert det.frames_processed == 0
        assert not det._model.called

    def test_stop_sets_running_false(self, tmp_path):
        det = YoloDetector(model_path="fake.pt", output_dir=str(tmp_path))
        det.start()
        assert det.running
        det.stop()
        assert not det.running

    def test_preload_async_returns_daemon_thread(self, tmp_path):
        """preload_async starts load_model in a background thread."""
        det = YoloDetector(model_path="fake.pt", output_dir=str(tmp_path))
        # Stub load_model so we don't import ultralytics (slow)
        det.load_model = MagicMock(return_value=False)
        thread = det.preload_async()
        assert thread is not None
        assert thread.daemon is True
        thread.join(timeout=2)
        assert not thread.is_alive()
        det.load_model.assert_called_once()

    def test_save_policy_can_disable_detection_and_empty_frame_writes(self, tmp_path):
        callback = MagicMock()
        data_callback = MagicMock()
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            min_interval=0.0,
            on_detection=callback,
            on_detection_data=data_callback,
        )
        det.configure_saving(save_detections=False, save_no_detections=False)
        det._model = MagicMock(return_value=[_mock_detection_result()])
        det._model.names = {0: "pigeon"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)

        data_callback.assert_called_once()
        callback.assert_not_called()
        assert list((tmp_path / "detections").glob("*.png")) == []
        assert list((tmp_path / "frames").glob("*.png")) == []

    def test_capture_next_detection_saves_one_forced_image(self, tmp_path):
        callback = MagicMock()
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            min_interval=0.0,
            on_detection=callback,
        )
        det.configure_saving(save_detections=False, save_no_detections=False)
        det.capture_next_detection("wall_trigger")
        det._model = MagicMock(return_value=[_mock_detection_result()])
        det._model.names = {0: "pigeon"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)
        det.process_frame(frame)

        files = list((tmp_path / "detections").glob("*.png"))
        assert len(files) == 1
        assert files[0].name.startswith("wall_trigger_")
        callback.assert_called_once()

    def test_capture_next_detection_saves_queued_forced_images(self, tmp_path):
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            min_interval=0.0,
        )
        det.configure_saving(save_detections=False, save_no_detections=False)
        det.capture_next_detection("pursuit_start")
        det.capture_next_detection("pursuit_centered")
        det._model = MagicMock(return_value=[_mock_detection_result()])
        det._model.names = {0: "pigeon"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)
        det.process_frame(frame)
        det.process_frame(frame)

        names = {file.name for file in (tmp_path / "detections").glob("*.png")}
        assert len(names) == 2
        assert any(name.startswith("pursuit_start_") for name in names)
        assert any(name.startswith("pursuit_centered_") for name in names)

    def test_save_policy_uses_detection_prefix_for_throttled_images(self, tmp_path):
        det = YoloDetector(
            model_path="fake.pt",
            output_dir=str(tmp_path),
            min_interval=0.0,
        )
        det.configure_saving(
            save_detections=True,
            save_no_detections=False,
            detection_prefix="pursuit_02_leg_4_sample",
        )
        det._model = MagicMock(return_value=[_mock_detection_result()])
        det._model.names = {0: "pigeon"}
        det.start()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        det.process_frame(frame)

        files = list((tmp_path / "detections").glob("*.png"))
        assert len(files) == 1
        assert files[0].name.startswith("pursuit_02_leg_4_sample_")
