"""Unit tests for SimService's PX4-console disarm path (panic reset).

The reset button disarms PX4 by writing `commander disarm -f` to PX4's pxh
console — either via the backend's own launcher pipe, or (when the sim was
started by Start Scarecrow.bat) via the launcher's on-disk FIFO. These tests
cover the delivery/fallback logic with mocks; the real PX4 round-trip is
verified manually in sim.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from services.sim_service import SimService


class TestSendPxhCommand:
    def test_prefers_process_stdin(self):
        svc = SimService()
        svc.process = MagicMock()
        svc.process.stdin = MagicMock()
        assert svc._send_pxh_command("commander disarm -f") is True
        svc.process.stdin.write.assert_called_once_with("commander disarm -f\n")
        svc.process.stdin.flush.assert_called_once()

    def test_falls_back_to_fifo_when_no_process(self):
        svc = SimService()
        svc.process = None
        with patch("services.sim_service.os.name", "posix"), \
             patch.object(SimService, "_find_pxh_fifo", return_value="/tmp/scarecrow_pxh.AB.fifo"), \
             patch("services.sim_service.os.open", return_value=7) as mock_open, \
             patch("services.sim_service.os.write") as mock_write, \
             patch("services.sim_service.os.close") as mock_close:
            assert svc._send_pxh_command("commander disarm -f") is True
            mock_open.assert_called_once()
            mock_write.assert_called_once()
            assert b"commander disarm -f" in mock_write.call_args.args[1]
            mock_close.assert_called_once_with(7)

    def test_returns_false_when_no_pipe_and_no_fifo(self):
        svc = SimService()
        svc.process = None
        with patch("services.sim_service.os.name", "posix"), \
             patch.object(SimService, "_find_pxh_fifo", return_value=None):
            assert svc._send_pxh_command("commander disarm -f") is False


class TestDisarmViaConsole:
    def test_sends_hold_then_disarm(self):
        svc = SimService()
        with patch.object(SimService, "_send_pxh_command", return_value=True) as mock_send:
            assert svc.disarm_via_console() is True
            sent = [c.args[0] for c in mock_send.call_args_list]
            assert sent == ["commander mode auto:hold", "commander disarm -f"]

    def test_true_if_any_command_lands(self):
        svc = SimService()
        # hold fails to deliver, disarm succeeds -> still considered a success.
        with patch.object(SimService, "_send_pxh_command", side_effect=[False, True]):
            assert svc.disarm_via_console() is True


@pytest.mark.skipif(os.name != "posix", reason="os.mkfifo is POSIX-only")
class TestFindPxhFifo:
    def test_returns_newest_fifo(self, tmp_path):
        old = tmp_path / "scarecrow_pxh.OLD.fifo"
        new = tmp_path / "scarecrow_pxh.NEW.fifo"
        os.mkfifo(old)
        os.mkfifo(new)
        os.utime(old, (1, 1))
        os.utime(new, (2, 2))
        with patch.dict(os.environ, {"TMPDIR": str(tmp_path)}):
            assert SimService._find_pxh_fifo() == str(new)

    def test_none_when_no_fifo(self, tmp_path):
        with patch.dict(os.environ, {"TMPDIR": str(tmp_path)}):
            assert SimService._find_pxh_fifo() is None

    def test_ignores_non_fifo_matches(self, tmp_path):
        # A regular file matching the glob must not be returned.
        regular = tmp_path / "scarecrow_pxh.NOTAFIFO.fifo"
        regular.write_text("x")
        with patch.dict(os.environ, {"TMPDIR": str(tmp_path)}):
            assert SimService._find_pxh_fifo() is None
