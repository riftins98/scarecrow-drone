#!/usr/bin/env python3
"""Hangar circuit search with pigeon pursuit and live-only YOLO frames.

Entry point only. The mission itself is
`scarecrow.missions.hangar_circuit` -- flight logic belongs in the package
where it can be imported, tested and reused, not in a script.

Run with Gazebo already launched, for example:
    ./scripts/shell/launch_with_stream.sh hangar_lite
    pixi run python scripts/flight/hangar_circuit_pursuit.py --ceiling-clearance 1.0
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

# Keep webapp/live terminal output line-by-line even when this script is run
# outside DetectionService's `python -u` launcher path.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# gRPC (MAVSDK's transport) is noisy at default verbosity and its fork handler
# deadlocks against the detector's worker threads.
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from scarecrow.missions.hangar_circuit import (  # noqa: E402
    HangarCircuitPursuitMission,
    config_from_args,
    parse_args,
)


async def run() -> None:
    await HangarCircuitPursuitMission(config_from_args(parse_args())).run()


def _cleanup_and_exit(exit_code: int = 0) -> None:
    """Reap mavsdk_server and exit immediately.

    os._exit, not sys.exit: the detector's worker threads and gRPC's own
    threads are non-daemon, and a normal interpreter shutdown waits on them --
    which has hung after an otherwise clean landing. The flight is over and
    every resource is process-local, so skipping teardown is safe here.
    """
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    os._exit(exit_code)


if __name__ == "__main__":
    try:
        asyncio.run(run())
        _cleanup_and_exit(0)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        _cleanup_and_exit(130)
    except Exception as exc:
        print(f"\n[FLIGHT FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        _cleanup_and_exit(1)
