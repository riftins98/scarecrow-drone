"""Landing and disarm that does not strand an armed drone.

The failure this guards against is a mission ending with props still spinning
because a telemetry read hung during descent. Every step is bounded and the
sequence always reaches a disarm attempt.
"""
from __future__ import annotations

import asyncio

from scarecrow.controllers.wall_follow import VelocityCommand

# 150 polls at 0.2s = 30s, comfortably longer than a descent from any altitude
# this system flies at indoors.
_TOUCHDOWN_POLL_COUNT = 150
_TOUCHDOWN_POLL_INTERVAL_S = 0.2

# Below this AGL the drone is on the ground. Not zero: the rangefinder reads a
# small positive value with the gear down.
_TOUCHDOWN_AGL_M = 0.15


async def safe_land(drone) -> None:
    """Stop, leave offboard, land, confirm touchdown, disarm.

    Offboard must be released before `land()`: PX4 will not accept the land
    command while an offboard setpoint stream is active, and the drone would
    hover until the mission gave up.

    `force_kill_on_failure` is passed only when touchdown was *confirmed*.
    Force-killing a drone that might still be airborne would drop it.
    """
    await drone.set_velocity(VelocityCommand())
    await drone.stop_offboard()
    print("Commanding land...")
    await drone.land()

    landed = False
    for _ in range(_TOUCHDOWN_POLL_COUNT):
        await asyncio.sleep(_TOUCHDOWN_POLL_INTERVAL_S)
        try:
            pos = await asyncio.wait_for(drone.get_position(), timeout=1.0)
        except Exception:
            # Lost telemetry mid-descent. Stop polling and still try to disarm,
            # but without the force flag since touchdown is unconfirmed.
            break
        agl = -(pos.position.down_m - drone.ground_z)
        if agl < _TOUCHDOWN_AGL_M:
            landed = True
            break

    if not landed:
        print("  WARNING: touchdown not confirmed before disarm attempt")

    print("Disarming...")
    if await drone.disarm(force_kill_on_failure=landed):
        print("  Disarmed.")
    else:
        print("  WARNING: drone did not disarm cleanly")


async def wait_for_rangefinder(rangefinder, timeout_s: float = 10.0) -> bool:
    """Wait until a rangefinder produces a reading. False on timeout.

    A started rangefinder is not a publishing one -- the Gazebo topic can take
    seconds to carry its first message. Reading too early yields None and looks
    like a missing sensor.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if rangefinder.get_distance_m() is not None:
            return True
        await asyncio.sleep(0.1)
    return False
