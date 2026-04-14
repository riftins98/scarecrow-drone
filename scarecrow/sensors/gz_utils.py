"""Shared Gazebo CLI environment detection."""
from __future__ import annotations

import os
import subprocess


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
