#!/usr/bin/env python3
"""Shell helper: resolve world metadata from SDF files (no hardcoded registry).

Usage:
  world_meta.py default-world
  world_meta.py spawn-pose <world_id>
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WG_PATH = REPO_ROOT / "webapp" / "backend" / "services" / "world_geometry.py"

_spec = importlib.util.spec_from_file_location("world_geometry", WG_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load {WG_PATH}")
_wg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wg)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    if cmd == "default-world":
        print(_wg.resolve_default_world(str(REPO_ROOT / "worlds")))
        return 0
    if cmd == "spawn-pose":
        if len(sys.argv) != 3:
            print("usage: world_meta.py spawn-pose <world_id>", file=sys.stderr)
            return 2
        print(_wg.default_spawn_pose(sys.argv[2]) or "")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
