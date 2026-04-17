"""UT-10..11: YoloDetector tests (ADD Section 5.4). Mocks ultralytics."""
from unittest.mock import MagicMock

import numpy as np

from scarecrow.detection.yolo import YoloDetector


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
