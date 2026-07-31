"""Complete flight missions.

A mission owns an entire flight: sensor bring-up, takeoff, the phase sequence,
landing and map output. Everything below (`controllers/`, `sensors/`,
`navigation/`) is a component a mission composes.

This layer exists so `scripts/flight/*.py` can be argument parsing and an
`asyncio.run()` call, instead of carrying the flight logic itself. Anything
runnable, testable or reusable belongs here rather than in a script.
"""

from .hangar_circuit import HangarCircuitConfig, HangarCircuitPursuitMission

__all__ = ["HangarCircuitConfig", "HangarCircuitPursuitMission"]
