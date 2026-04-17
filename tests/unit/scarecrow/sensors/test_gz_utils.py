"""Tests for gz_utils -- Gazebo CLI helpers."""
import time
from unittest.mock import MagicMock, patch

from scarecrow.sensors.gz_utils import prefetch_gz_env_async, GzPrefetchResult


class TestPrefetchGzEnvAsync:
    def test_returns_thread_and_result(self):
        fake_proc = MagicMock()
        fake_proc.stdout = "topic1\ntopic2\n"
        with patch("scarecrow.sensors.gz_utils.get_gz_env", return_value={"MOCK": "1"}), \
             patch("subprocess.run", return_value=fake_proc):
            thread, result = prefetch_gz_env_async()
            assert isinstance(result, GzPrefetchResult)
            thread.join(timeout=2)
            assert result.env == {"MOCK": "1"}
            assert "topic1" in result.topics
            assert "topic2" in result.topics

    def test_result_empty_on_subprocess_failure(self):
        with patch("scarecrow.sensors.gz_utils.get_gz_env", return_value={}), \
             patch("subprocess.run", side_effect=RuntimeError("boom")):
            thread, result = prefetch_gz_env_async()
            thread.join(timeout=2)
            assert result.topics == ""

    def test_thread_runs_in_background(self):
        """Thread should not block the caller."""
        fake_proc = MagicMock()
        fake_proc.stdout = "t"

        def slow_run(*args, **kwargs):
            time.sleep(0.05)
            return fake_proc

        with patch("scarecrow.sensors.gz_utils.get_gz_env", return_value={}), \
             patch("subprocess.run", side_effect=slow_run):
            start = time.time()
            thread, _ = prefetch_gz_env_async()
            elapsed = time.time() - start
            # Returning should be fast -- slow_run happens in the thread
            assert elapsed < 0.02
            thread.join(timeout=2)
