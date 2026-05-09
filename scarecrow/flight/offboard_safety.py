"""Safety and altitude-hold helpers for offboard flight loops."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from ..controllers.wall_follow import VelocityCommand


@dataclass(frozen=True)
class SafetyLimits:
    max_forward_speed: float = 0.5
    max_lateral_speed: float = 0.4
    max_vertical_speed: float = 0.4
    max_yaw_speed: float = 20.0
    max_height: float = 3.0
    min_wall_distance: float = 0.6
    health_grace_s: float = 2.0


class AltitudeHoldController:
    """Simple P controller for altitude hold in AGL meters."""

    def __init__(
        self,
        target_alt_m: float,
        kp: float = 0.6,
        deadband_m: float = 0.05,
        max_up_speed: float = 0.4,
        max_down_speed: float = 0.4,
    ) -> None:
        self.target_alt_m = target_alt_m
        self.kp = kp
        self.deadband_m = deadband_m
        self.max_up_speed = max_up_speed
        self.max_down_speed = max_down_speed

    def update(self, agl_m: float) -> float:
        """Return down-axis velocity (positive = descend)."""
        error = self.target_alt_m - agl_m
        if abs(error) <= self.deadband_m:
            return 0.0
        if error > 0.0:
            # Below target: climb (negative down velocity).
            return -min(self.max_up_speed, self.kp * error)
        # Above target: descend (positive down velocity).
        return min(self.max_down_speed, self.kp * abs(error))


class HealthMonitor:
    """Track health flags without blocking the main control loop."""

    def __init__(self, system) -> None:
        self._system = system
        self._task: Optional[asyncio.Task] = None
        self.is_local_position_ok: bool = False
        self._last_ok_time: Optional[float] = None

    async def _run(self) -> None:
        async for health in self._system.telemetry.health():
            now = time.monotonic()
            self.is_local_position_ok = health.is_local_position_ok
            if self.is_local_position_ok:
                self._last_ok_time = now

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def time_since_ok(self) -> Optional[float]:
        if self._last_ok_time is None:
            return None
        return time.monotonic() - self._last_ok_time


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def apply_velocity_limits(cmd: VelocityCommand, limits: SafetyLimits) -> VelocityCommand:
    return VelocityCommand(
        forward_m_s=_clamp(cmd.forward_m_s, -limits.max_forward_speed, limits.max_forward_speed),
        right_m_s=_clamp(cmd.right_m_s, -limits.max_lateral_speed, limits.max_lateral_speed),
        down_m_s=_clamp(cmd.down_m_s, -limits.max_vertical_speed, limits.max_vertical_speed),
        yawspeed_deg_s=_clamp(cmd.yawspeed_deg_s, -limits.max_yaw_speed, limits.max_yaw_speed),
    )


def apply_safety(
    cmd: VelocityCommand,
    *,
    agl_m: float,
    wall_dist_m: float,
    front_dist_m: float,
    limits: SafetyLimits,
    height_descent_m_s: float = 0.4,
) -> tuple[VelocityCommand, Optional[str]]:
    """Apply hard safety guards. Returns (cmd, stop_reason)."""
    if wall_dist_m < limits.min_wall_distance or front_dist_m < limits.min_wall_distance:
        return VelocityCommand(), "wall_too_close"

    if agl_m > limits.max_height:
        return VelocityCommand(
            forward_m_s=0.0,
            right_m_s=0.0,
            down_m_s=min(limits.max_vertical_speed, height_descent_m_s),
            yawspeed_deg_s=0.0,
        ), "height_limit"

    return apply_velocity_limits(cmd, limits), None
