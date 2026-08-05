"""Tearing down a PX4 SITL instance completely.

A Disconnect that killed only the main `px4` process left `px4-mavlink` and the
`init.d-posix/rcS` startup shell running. Those keep the instance alive, so the
NEXT Connect failed with `ERROR [px4] Task already running`, never brought the
estimator up, and the drone refused to arm with "Preflight Fail: ekf2 missing
data" -- a symptom that points at the EKF instead of at the leftover process.

That is why these tests assert on the kill *patterns* rather than on some
"stopped" flag: the flag was already correct while the bug was live.
"""
from unittest.mock import MagicMock, patch

import pytest

from services import sim_service
from services.sim_service import _kill_px4_instance, _px4_alive


def _runner(alive_names=(), missing_pkill=False):
    """Fake subprocess.run over a set of 'running' process descriptors.

    A descriptor is matched against the pkill/pgrep pattern the same way the
    real tools would: -x against the process name, -f against the command line.
    """
    state = {"alive": set(alive_names)}

    def run(cmd, **kwargs):
        if missing_pkill:
            raise FileNotFoundError(cmd[0])
        tool = cmd[0]
        args = [a for a in cmd[1:] if a != "-9"]
        exact = "-x" in args
        pattern = args[-1]

        def matches(name):
            if exact:
                return name == pattern
            if pattern.startswith("^"):
                return name.startswith(pattern[1:])
            return pattern in name

        hit = {n for n in state["alive"] if matches(n)}
        if tool == "pkill":
            state["alive"] -= hit
        return MagicMock(returncode=0 if hit else 1)

    return run, state


class TestPx4Alive:
    def test_detects_the_main_process(self):
        run, _ = _runner(["px4"])
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _px4_alive() is True

    def test_detects_a_module_client_the_old_check_missed(self):
        """`pkill -x px4` never matched `px4-mavlink`; the name differs."""
        run, _ = _runner(["px4-mavlink --instance 0 stream -r 50"])
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _px4_alive() is True

    def test_detects_the_startup_shell(self):
        run, _ = _runner(["/bin/sh /px4/build/.../etc/init.d-posix/rcS 0"])
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _px4_alive() is True

    def test_reports_clean_when_nothing_runs(self):
        run, _ = _runner([])
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _px4_alive() is False

    def test_no_pgrep_reports_clean_rather_than_raising(self):
        """Non-POSIX hosts have no pgrep, and never spawned PX4 from here."""
        run, _ = _runner([], missing_pkill=True)
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _px4_alive() is False


class TestKillPx4Instance:
    def test_kills_the_main_process(self):
        run, state = _runner(["px4"])
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _kill_px4_instance() is True
        assert state["alive"] == set()

    def test_kills_module_clients(self):
        """The regression: a surviving px4-mavlink breaks the next launch."""
        run, state = _runner(["px4", "px4-mavlink --instance 0 stream"])
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _kill_px4_instance() is True
        assert state["alive"] == set()

    def test_kills_the_rcs_startup_shell(self):
        run, state = _runner(
            ["px4", "/bin/sh /repo/px4/build/px4_sitl_default/etc/init.d-posix/rcS 0"]
        )
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _kill_px4_instance() is True
        assert state["alive"] == set()

    def test_kills_a_full_instance_in_one_call(self):
        run, state = _runner([
            "px4",
            "px4-mavlink --instance 0 stream -r 50",
            "px4-commander status",
            "/bin/sh /repo/px4/build/px4_sitl_default/etc/init.d-posix/rcS 0",
        ])
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _kill_px4_instance() is True
        assert state["alive"] == set()

    def test_does_not_touch_unrelated_processes(self):
        """Tight scoping matters: this runs on the developer's own machine."""
        survivors = ["gz sim --headless", "python3 my_px4_notes.py", "uvicorn app:app"]
        run, state = _runner(["px4"] + survivors)
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            _kill_px4_instance()
        assert state["alive"] == set(survivors)

    def test_escalates_to_sigkill_when_a_process_ignores_sigterm(self):
        sent = []

        def run(cmd, **kwargs):
            sent.append(cmd)
            # pgrep always reports something alive -> forces escalation.
            return MagicMock(returncode=0 if cmd[0] == "pgrep" else 1)

        with patch.object(sim_service.subprocess, "run", side_effect=run), \
                patch.object(sim_service.time, "sleep"):
            _kill_px4_instance(timeout_s=0.01)

        assert any(c[0] == "pkill" and "-9" in c for c in sent), \
            "a process that ignores SIGTERM must be SIGKILLed, not left running"

    def test_reports_failure_when_the_instance_cannot_be_killed(self):
        """Connect must be able to tell the user, not fail confusingly later."""

        def run(cmd, **kwargs):
            return MagicMock(returncode=0 if cmd[0] == "pgrep" else 1)

        with patch.object(sim_service.subprocess, "run", side_effect=run), \
                patch.object(sim_service.time, "sleep"):
            assert _kill_px4_instance(timeout_s=0.01) is False

    def test_waits_for_death_before_returning(self):
        """The next launch starts ~1s later; a dying process still holds it."""
        calls = {"n": 0}

        def run(cmd, **kwargs):
            if cmd[0] == "pgrep":
                calls["n"] += 1
                return MagicMock(returncode=0 if calls["n"] <= 3 else 1)
            return MagicMock(returncode=0)

        with patch.object(sim_service.subprocess, "run", side_effect=run), \
                patch.object(sim_service.time, "sleep"):
            assert _kill_px4_instance() is True
        assert calls["n"] > 1, "returned without waiting for the process to exit"

    def test_missing_pkill_is_not_an_error(self):
        run, _ = _runner([], missing_pkill=True)
        with patch.object(sim_service.subprocess, "run", side_effect=run):
            assert _kill_px4_instance() is True
