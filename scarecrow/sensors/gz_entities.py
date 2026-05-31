"""Gazebo Sim entity helpers."""
from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, radians, sin
from typing import Sequence


@dataclass(frozen=True)
class GzModelCandidate:
    """A top-level model include from a world SDF."""

    name: str
    uri: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class GzModelPose:
    """A live Gazebo model pose in world coordinates."""

    name: str
    x: float
    y: float
    z: float
    yaw_deg: float = 0.0


@dataclass(frozen=True)
class GzPx4FrameTransform:
    """Runtime transform from PX4 local XY coordinates to Gazebo world XY."""

    px4_origin_x: float
    px4_origin_y: float
    px4_origin_yaw_deg: float
    gz_origin_x: float
    gz_origin_y: float
    gz_origin_yaw_deg: float

    @property
    def yaw_offset_deg(self) -> float:
        return self.gz_origin_yaw_deg - self.px4_origin_yaw_deg

    def px4_to_gz(self, x: float, y: float) -> tuple[float, float]:
        """Map a PX4 local XY point into Gazebo world XY."""
        dx = x - self.px4_origin_x
        dy = y - self.px4_origin_y
        yaw = radians(self.yaw_offset_deg)
        return (
            self.gz_origin_x + cos(yaw) * dx - sin(yaw) * dy,
            self.gz_origin_y + sin(yaw) * dx + cos(yaw) * dy,
        )

    def estimate_target_gz_xy(
        self,
        *,
        local_x: float,
        local_y: float,
        yaw_deg: float,
        range_m: float | None,
    ) -> tuple[float, float]:
        """Estimate a forward target point in Gazebo world XY."""
        target_x = local_x
        target_y = local_y
        if range_m is not None and isfinite(range_m):
            yaw = radians(yaw_deg)
            target_x += cos(yaw) * range_m
            target_y += sin(yaw) * range_m
        return self.px4_to_gz(target_x, target_y)


@dataclass(frozen=True)
class GzRemoveResult:
    """Result of a Gazebo entity removal request."""

    success: bool
    world_name: str | None
    model_name: str | None
    message: str
    distance_m: float | None = None


_WORLD_TOPIC_RE = re.compile(r"(?:^|/)world/([^/\s]+)(?:/|$)")
_MODEL_TOPIC_RE = re.compile(r"(?:^|/)model/([^/\s]+)(?:/|$)")


def discover_world_name(topics: str) -> str | None:
    """Return the Gazebo world name found in a topic list."""
    for line in topics.splitlines():
        match = _WORLD_TOPIC_RE.search(line.strip())
        if match:
            return match.group(1)
    return None


def discover_model_name(topics: str, *, contains: str) -> str | None:
    """Return the first Gazebo model name from topics containing a string."""
    for line in topics.splitlines():
        match = _MODEL_TOPIC_RE.search(line.strip())
        if match and contains in match.group(1):
            return match.group(1)
    return None


def get_world_model_poses(
    *,
    world_name: str,
    env: dict | None = None,
    timeout_s: float = 2.0,
) -> dict[str, GzModelPose]:
    """Read live model poses from Gazebo's world pose topic."""
    topic = f"/world/{world_name}/pose/info"
    try:
        proc = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", topic],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    if proc.returncode != 0 or not proc.stdout:
        return {}
    return parse_pose_info(proc.stdout)


def parse_pose_info(text: str) -> dict[str, GzModelPose]:
    """Parse `gz.msgs.Pose_V` text output into named model poses."""
    poses: dict[str, GzModelPose] = {}
    for block in _pose_blocks(text):
        name = _quoted_field(block, "name")
        if not name or "::" in name:
            continue

        position = _submessage(block, "position")
        if not position:
            continue
        x = _numeric_field(position, "x", 0.0)
        y = _numeric_field(position, "y", 0.0)
        z = _numeric_field(position, "z", 0.0)

        orientation = _submessage(block, "orientation")
        yaw_deg = 0.0
        if orientation:
            qx = _numeric_field(orientation, "x", 0.0)
            qy = _numeric_field(orientation, "y", 0.0)
            qz = _numeric_field(orientation, "z", 0.0)
            qw = _numeric_field(orientation, "w", 1.0)
            yaw_deg = _yaw_from_quaternion(qx, qy, qz, qw)

        poses[name] = GzModelPose(name=name, x=x, y=y, z=z, yaw_deg=yaw_deg)
    return poses


def find_model_pose(
    poses: dict[str, GzModelPose],
    *,
    name: str | None = None,
    contains: str | None = None,
) -> GzModelPose | None:
    """Find a live Gazebo pose by exact name or substring."""
    if name and name in poses:
        return poses[name]
    if contains:
        return next((pose for model_name, pose in poses.items() if contains in model_name), None)
    return None


def load_world_model_candidates(
    world_name: str,
    *,
    worlds_dir: str,
    model_names: Sequence[str] | None = None,
    name_prefixes: Sequence[str] = ("pigeon",),
    uri_keywords: Sequence[str] = ("pigeon",),
) -> list[GzModelCandidate]:
    """Load removable target candidates from a repo-owned world SDF.

    Selection can be narrowed by exact model names, name prefixes, or URI
    keywords. Top-level ``<include>`` entries are used because those are the
    Gazebo models the world remove service can delete by name.
    """
    sdf_path = os.path.join(worlds_dir, f"{world_name}.sdf")
    if not os.path.isfile(sdf_path):
        return []

    wanted_names = set(model_names or [])
    prefixes = tuple(prefix for prefix in name_prefixes if prefix)
    keywords = tuple(keyword.lower() for keyword in uri_keywords if keyword)

    try:
        root = ET.parse(sdf_path).getroot()
    except ET.ParseError:
        return []

    candidates: list[GzModelCandidate] = []
    for include in root.findall(".//world/include"):
        name = _child_text(include, "name")
        uri = _child_text(include, "uri")
        if not name or not uri:
            continue
        if not _matches_target(name, uri, wanted_names, prefixes, keywords):
            continue

        x, y, z = _parse_pose_xyz(_child_text(include, "pose"))
        candidates.append(GzModelCandidate(name=name, uri=uri, x=x, y=y, z=z))
    return candidates


def choose_nearest_model(
    candidates: Sequence[GzModelCandidate],
    *,
    x: float,
    y: float,
    max_distance_m: float | None = None,
) -> tuple[GzModelCandidate, float] | None:
    """Choose the candidate nearest to a world XY position."""
    if not candidates or not isfinite(x) or not isfinite(y):
        return None

    best = min(candidates, key=lambda model: hypot(model.x - x, model.y - y))
    distance = hypot(best.x - x, best.y - y)
    if max_distance_m is not None and distance > max_distance_m:
        return None
    return best, distance


def remove_model(
    *,
    world_name: str,
    model_name: str,
    env: dict | None = None,
    timeout_ms: int = 2000,
) -> GzRemoveResult:
    """Delete a named model from a running Gazebo Sim world."""
    service = f"/world/{world_name}/remove"
    req = f'name: "{model_name}" type: MODEL'
    try:
        proc = subprocess.run(
            [
                "gz",
                "service",
                "-s",
                service,
                "--reqtype",
                "gz.msgs.Entity",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                str(timeout_ms),
                "--req",
                req,
            ],
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout_ms / 1000.0 + 1.0),
            env=env,
        )
    except FileNotFoundError:
        return GzRemoveResult(False, world_name, model_name, "gz CLI not found")
    except subprocess.TimeoutExpired:
        return GzRemoveResult(False, world_name, model_name, "remove request timed out")

    output = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part.strip())
    success = proc.returncode == 0 and "data: false" not in output.lower()
    if success:
        return GzRemoveResult(True, world_name, model_name, output or "removed")
    return GzRemoveResult(False, world_name, model_name, output or f"gz exited {proc.returncode}")


def remove_nearest_model(
    *,
    world_name: str | None,
    x: float,
    y: float,
    env: dict | None,
    worlds_dir: str,
    model_names: Sequence[str] | None = None,
    name_prefixes: Sequence[str] = ("pigeon",),
    uri_keywords: Sequence[str] = ("pigeon",),
    max_distance_m: float | None = None,
    timeout_ms: int = 2000,
    prefer_live_poses: bool = True,
) -> GzRemoveResult:
    """Remove the best matching target model.

    If the world only has one matching target, remove it directly. When several
    targets match, choose the one nearest to the successful pursuit position and
    apply the optional distance guard.
    """
    if not world_name:
        return GzRemoveResult(False, None, None, "Gazebo world name not found")

    candidates = load_world_model_candidates(
        world_name,
        worlds_dir=worlds_dir,
        model_names=model_names,
        name_prefixes=name_prefixes,
        uri_keywords=uri_keywords,
    )
    if not candidates:
        return GzRemoveResult(False, world_name, None, "no matching target models in world SDF")

    if prefer_live_poses:
        live_poses = get_world_model_poses(world_name=world_name, env=env)
        if live_poses:
            live_candidates = [
                GzModelCandidate(
                    name=candidate.name,
                    uri=candidate.uri,
                    x=live_poses[candidate.name].x,
                    y=live_poses[candidate.name].y,
                    z=live_poses[candidate.name].z,
                )
                for candidate in candidates
                if candidate.name in live_poses
            ]
            if live_candidates:
                candidates = live_candidates

    if len(candidates) == 1:
        model = candidates[0]
        distance = hypot(model.x - x, model.y - y) if isfinite(x) and isfinite(y) else None
        result = remove_model(
            world_name=world_name,
            model_name=model.name,
            env=env,
            timeout_ms=timeout_ms,
        )
        return GzRemoveResult(
            result.success,
            result.world_name,
            result.model_name,
            result.message,
            distance_m=distance,
        )

    chosen = choose_nearest_model(candidates, x=x, y=y, max_distance_m=max_distance_m)
    if chosen is None:
        distance_text = "configured range" if max_distance_m is None else f"{max_distance_m:.2f}m"
        return GzRemoveResult(
            False,
            world_name,
            None,
            f"no target model within {distance_text}",
        )

    model, distance = chosen
    result = remove_model(
        world_name=world_name,
        model_name=model.name,
        env=env,
        timeout_ms=timeout_ms,
    )
    return GzRemoveResult(
        result.success,
        result.world_name,
        result.model_name,
        result.message,
        distance_m=distance,
    )


def _child_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    return "" if child is None or child.text is None else child.text.strip()


def _parse_pose_xyz(pose_text: str) -> tuple[float, float, float]:
    parts = pose_text.split()
    values = []
    for raw in parts[:3]:
        try:
            values.append(float(raw))
        except ValueError:
            values.append(0.0)
    while len(values) < 3:
        values.append(0.0)
    return values[0], values[1], values[2]


def _matches_target(
    name: str,
    uri: str,
    wanted_names: set[str],
    prefixes: Sequence[str],
    keywords: Sequence[str],
) -> bool:
    if wanted_names and name not in wanted_names:
        return False
    if wanted_names:
        return True
    if any(name.startswith(prefix) for prefix in prefixes):
        return True
    uri_lower = uri.lower()
    return any(keyword in uri_lower for keyword in keywords)


def _pose_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    depth = 0
    for line in text.splitlines():
        stripped = line.strip()
        if depth == 0:
            if stripped == "pose {":
                current = [line]
                depth = line.count("{") - line.count("}")
            continue

        current.append(line)
        depth += line.count("{") - line.count("}")
        if depth == 0:
            blocks.append("\n".join(current))
            current = []
    return blocks


def _quoted_field(text: str, field: str) -> str:
    match = re.search(rf"\b{re.escape(field)}:\s*\"([^\"]+)\"", text)
    return "" if match is None else match.group(1)


def _numeric_field(text: str, field: str, default: float) -> float:
    match = re.search(rf"\b{re.escape(field)}:\s*([-+0-9.eE]+)", text)
    if match is None:
        return default
    try:
        return float(match.group(1))
    except ValueError:
        return default


def _submessage(text: str, field: str) -> str:
    match = re.search(rf"\b{re.escape(field)}\s*\{{([^{{}}]*)\}}", text, flags=re.S)
    return "" if match is None else match.group(1)


def _yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    return degrees(atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))
