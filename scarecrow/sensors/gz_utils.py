"""Shared Gazebo CLI environment detection."""
from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional


def get_gz_env() -> dict:
    """Return environment variables for gz CLI commands.

    Auto-detects whether GZ_IP / GZ_PARTITION are needed based on
    whether the Gazebo instance is reachable without them (GUI/non-standalone
    mode) or requires explicit network config (standalone mode).
    """
    env = os.environ.copy()

    # Try without GZ_IP first (works in non-standalone/GUI mode)
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True, text=True, timeout=3, env=env,
        )
        if "holybro_x500" in result.stdout:
            return env
    except Exception:
        pass

    # Try with GZ_IP (needed in standalone mode with GZ_PARTITION)
    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            capture_output=True, text=True, timeout=3,
        )
        env["GZ_IP"] = result.stdout.strip()
    except Exception:
        try:
            result = subprocess.run(
                ["hostname", "-I"],
                capture_output=True, text=True, timeout=3,
            )
            env["GZ_IP"] = result.stdout.strip().split()[0]
        except Exception:
            pass

    env["GZ_PARTITION"] = "px4"
    return env


@dataclass
class GzPrefetchResult:
    """Cached gz environment + topic list from a parallel prefetch."""
    env: dict = field(default_factory=dict)
    topics: str = ""


def prefetch_gz_env_async() -> tuple[threading.Thread, GzPrefetchResult]:
    """Fetch gz env and `gz topic -l` in a background thread.

    Flight scripts typically call this right before `drone.connect()` so the
    gz setup happens during the ~2-3s MAVSDK handshake.

    Returns:
        (thread, result) tuple. Caller should `thread.join()` before using
        `result.env` or `result.topics`.

    Usage:
        gz_thread, gz_result = prefetch_gz_env_async()
        await drone.connect()   # runs in parallel
        gz_thread.join()
        lidar = GazeboLidar(env=gz_result.env)
    """
    result = GzPrefetchResult()

    def _fetch():
        result.env = get_gz_env()
        try:
            proc = subprocess.run(
                ["gz", "topic", "-l"],
                capture_output=True, text=True, timeout=5, env=result.env,
            )
            result.topics = proc.stdout
        except Exception:
            result.topics = ""

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    return t, result
