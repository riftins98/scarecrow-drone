"""Spawn-map geometry derived from world/model SDF files.

The frontend spawn picker needs three pieces of world geometry:
  - the full floor rectangle,
  - the safe interior after wall clearance,
  - static included props whose footprints should block spawning.

This module keeps that logic data-driven from SDF instead of hardcoding a
single world name.
"""
from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WORLDS_DIR = os.path.join(REPO_ROOT, "worlds")
MODELS_DIR = os.path.join(REPO_ROOT, "models")

SPAWN_WALL_MARGIN = 3.0
SPAWN_OBSTACLE_MARGIN = 0.3

_CAMERA_MODELS = {"mono_cam", "mono_cam_hd"}
_MIN_OBSTACLE_AREA = 0.20


def _nums(text: Optional[str], n: int, default: float = 0.0) -> list[float]:
    vals: list[float] = []
    for raw in (text or "").split():
        try:
            vals.append(float(raw))
        except ValueError:
            pass
    while len(vals) < n:
        vals.append(default)
    return vals[:n]


def _pose(el: ET.Element) -> tuple[float, float, float, float, float, float]:
    pose_el = el.find("pose")
    x, y, z, roll, pitch, yaw = _nums(pose_el.text if pose_el is not None else "", 6)
    return x, y, z, roll, pitch, yaw


def _combine_pose(
    parent: tuple[float, float, float, float, float, float],
    child: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    """Enough SDF pose composition for these worlds: combine XY with yaw."""
    px, py, pz, pr, pp, pyaw = parent
    cx, cy, cz, cr, cp, cyaw = child
    c = math.cos(pyaw)
    s = math.sin(pyaw)
    return (
        px + cx * c - cy * s,
        py + cx * s + cy * c,
        pz + cz,
        pr + cr,
        pp + cp,
        pyaw + cyaw,
    )


def _bbox_from_center(
    cx: float, cy: float, sx: float, sy: float, yaw: float
) -> dict[str, float]:
    hx, hy = sx / 2.0, sy / 2.0
    c = math.cos(yaw)
    s = math.sin(yaw)
    pts = []
    for lx, ly in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
        pts.append((cx + lx * c - ly * s, cy + lx * s + ly * c))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"xMin": min(xs), "xMax": max(xs), "yMin": min(ys), "yMax": max(ys)}


def _size(el: ET.Element) -> Optional[list[float]]:
    size_el = el.find("./geometry/box/size")
    if size_el is None:
        size_el = el.find("./geometry/plane/size")
        if size_el is not None:
            sx, sy = _nums(size_el.text, 2)
            return [sx, sy, 0.0]
    if size_el is None:
        return None
    return _nums(size_el.text, 3)


def _world_name_from_path(sdf_path: str) -> str:
    return os.path.splitext(os.path.basename(sdf_path))[0]


def _largest_floor_bounds(root: ET.Element) -> Optional[dict[str, float]]:
    candidates: list[tuple[float, dict[str, float]]] = []
    for model in root.iter("model"):
        name = (model.get("name") or "").lower()
        if "floor" not in name and "ground" not in name:
            continue
        model_pose = _pose(model)
        for link in model.findall("link"):
            link_pose = _combine_pose(model_pose, _pose(link))
            for collision in link.findall("collision"):
                size = _size(collision)
                if not size:
                    continue
                sx, sy, sz = size
                if sx < 2.0 or sy < 2.0:
                    continue
                if sz > 0.5:
                    continue
                pose = _combine_pose(link_pose, _pose(collision))
                bounds = _bbox_from_center(pose[0], pose[1], sx, sy, pose[5])
                candidates.append((sx * sy, bounds))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


@lru_cache(maxsize=128)
def _model_footprint(model_name: str) -> Optional[dict[str, float]]:
    path = os.path.join(MODELS_DIR, model_name, "model.sdf")
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None

    candidates: list[tuple[float, dict[str, float]]] = []
    for collision in root.iter("collision"):
        size = _size(collision)
        if not size:
            continue
        sx, sy, _sz = size
        area = sx * sy
        if area <= 0:
            continue
        candidates.append((area, {"halfW": sx / 2.0, "halfL": sy / 2.0}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _included_obstacles(root: ET.Element) -> list[dict]:
    obstacles: list[dict] = []
    for include in root.iter("include"):
        uri_el = include.find("uri")
        if uri_el is None or not uri_el.text:
            continue
        uri = uri_el.text.strip()
        if not uri.startswith("model://"):
            continue
        model_name = uri.rsplit("/", 1)[-1]
        if model_name in _CAMERA_MODELS:
            continue
        footprint = _model_footprint(model_name)
        if not footprint:
            continue
        area = footprint["halfW"] * 2.0 * footprint["halfL"] * 2.0
        if area < _MIN_OBSTACLE_AREA:
            continue
        x, y, _z, _roll, _pitch, yaw = _pose(include)
        obstacles.append({
            "cx": x,
            "cy": y,
            "yaw": yaw,
            "halfW": footprint["halfW"],
            "halfL": footprint["halfL"],
            "kind": "aircraft" if "drone" in model_name else "box",
            "label": (include.findtext("name") or model_name).strip(),
        })
    return obstacles


@lru_cache(maxsize=128)
def spawn_map_for_world(world_name: str) -> Optional[dict]:
    sdf_path = os.path.join(WORLDS_DIR, f"{world_name}.sdf")
    try:
        root = ET.parse(sdf_path).getroot()
    except (ET.ParseError, OSError):
        return None
    return _spawn_map_from_root(root, world_name)


def _spawn_map_from_root(root: ET.Element, world_name: str) -> Optional[dict]:
    wall_bounds = _largest_floor_bounds(root)
    if not wall_bounds:
        return None

    bounds = {
        "xMin": wall_bounds["xMin"] + SPAWN_WALL_MARGIN,
        "xMax": wall_bounds["xMax"] - SPAWN_WALL_MARGIN,
        "yMin": wall_bounds["yMin"] + SPAWN_WALL_MARGIN,
        "yMax": wall_bounds["yMax"] - SPAWN_WALL_MARGIN,
    }
    if bounds["xMin"] >= bounds["xMax"] or bounds["yMin"] >= bounds["yMax"]:
        return None

    return {
        "world": world_name,
        "wallBounds": {k: round(v, 3) for k, v in wall_bounds.items()},
        "bounds": {k: round(v, 3) for k, v in bounds.items()},
        "obstacles": _included_obstacles(root),
        "obstacleMargin": SPAWN_OBSTACLE_MARGIN,
        "wallMargin": SPAWN_WALL_MARGIN,
    }


def spawn_map_for_path(sdf_path: str) -> Optional[dict]:
    try:
        root = ET.parse(sdf_path).getroot()
    except (ET.ParseError, OSError):
        return None
    return _spawn_map_from_root(root, _world_name_from_path(sdf_path))


def all_spawn_maps(worlds_dir: str = WORLDS_DIR) -> dict[str, dict]:
    if not os.path.isdir(worlds_dir):
        return {}
    out: dict[str, dict] = {}
    for fname in sorted(os.listdir(worlds_dir)):
        if not fname.endswith(".sdf"):
            continue
        world = fname[:-4]
        info = spawn_map_for_path(os.path.join(worlds_dir, fname))
        if info:
            out[world] = info
    return out


def in_obstacle(x: float, y: float, obs: dict, margin: float) -> bool:
    dx, dy = x - obs["cx"], y - obs["cy"]
    c, s = math.cos(-obs["yaw"]), math.sin(-obs["yaw"])
    lx = dx * c - dy * s
    ly = dx * s + dy * c
    return abs(lx) <= obs["halfW"] + margin and abs(ly) <= obs["halfL"] + margin


def validate_spawn(world_name: str, x: float, y: float) -> tuple[bool, Optional[str]]:
    info = spawn_map_for_world(world_name)
    if not info:
        return False, f"custom spawn is not supported for world {world_name!r}"
    b = info["bounds"]
    if not (b["xMin"] <= x <= b["xMax"] and b["yMin"] <= y <= b["yMax"]):
        return False, (
            f"spawn ({x:.1f}, {y:.1f}) is too close to a wall - must be within "
            f"x [{b['xMin']:.1f}, {b['xMax']:.1f}], y [{b['yMin']:.1f}, {b['yMax']:.1f}]"
        )
    margin = info["obstacleMargin"]
    for obs in info["obstacles"]:
        if in_obstacle(x, y, obs, margin):
            label = obs.get("label") or "obstacle"
            return False, f"spawn ({x:.1f}, {y:.1f}) is on/too close to {label}"
    return True, None
