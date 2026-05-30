"""Drone subprocess state wrapper.

Today: thin wrapper around DetectionService for flight lifecycle commands.
Phase 3-6 (UC7 Abort, UC5 Chase) extend this with SIGTERM handling and
telemetry stdout parsing.
"""
from typing import Optional


class DroneService:
    def __init__(self, detection_service=None):
        self.detection_service = detection_service
        self._latest_telemetry: dict = {}
        self._current_flight_id: Optional[str] = None

    @property
    def current_flight_id(self) -> Optional[str]:
        if self.detection_service is not None:
            return self.detection_service.flight_id
        return self._current_flight_id

    def get_status(self) -> dict:
        """Drone operational status for `/api/drone/status`."""
        is_connected = False
        is_flying = False
        if self.detection_service is not None:
            is_flying = self.detection_service.running
        return {
            "isConnected": is_connected,
            "isFlying": is_flying,
            "mode": "offboard" if is_flying else "idle",
            "batteryLevel": self._latest_telemetry.get("battery"),
        }

    def start_flight(self, flight_id: str, on_detection=None) -> bool:
        """Spawn the detection flight subprocess."""
        if self.detection_service is None:
            return False
        return self.detection_service.start(flight_id, on_detection=on_detection)

    def stop_flight(self) -> dict:
        """Gracefully stop the flight subprocess (lets it land)."""
        if self.detection_service is None:
            return {}
        return self.detection_service.stop() or {}

    def abort(self) -> bool:
        """Emergency abort. Stub: Phase 6 (UC7) implements SIGTERM + emergency landing."""
        if self.detection_service is None:
            return False
        self.detection_service.stop()
        return True

    def force_disarm(self, timeout: float = 10.0) -> bool:
        """Best-effort force-stop for a panic reset: connect to PX4 and put it
        in a state where it won't fly the drone after we teleport it.

        Connects on udpin://:14540 — the same stream the flight scripts use.
        PX4 keeps broadcasting to 14540 even after the script that was listening
        there dies, so a fresh listener reconnects. We first switch to Hold so
        the vehicle exits offboard (otherwise it keeps chasing its last
        setpoint), then kill the motors so it can't fly back up.

        Runs the async MAVSDK calls on a private event loop, so it's safe to
        call from a sync FastAPI handler. Returns True if at least the kill was
        acknowledged; False on any failure (the caller still proceeds with the
        teleport — disarm is best-effort)."""
        import asyncio

        try:
            from mavsdk import System
        except ImportError:
            return False

        # Bind the embedded mavsdk_server to a non-default port so it never
        # collides with one a flight script may still be tearing down.
        system = System(port=50061)

        async def _stop() -> bool:
            # Listen on the SDK stream PX4 broadcasts to (same as the scripts).
            # MAVSDK requires an explicit interface (0.0.0.0 = all).
            await system.connect(system_address="udpin://0.0.0.0:14540")
            try:
                async for state in system.core.connection_state():
                    if state.is_connected:
                        break
            except Exception:
                return False

            # 1. Exit offboard: command Hold so PX4 stops chasing setpoints.
            try:
                await system.action.hold()
            except Exception:
                pass  # not fatal; the kill below is what guarantees motors off

            # 2. Force motors off. Try kill (instant), fall back to disarm.
            try:
                await system.action.kill()
                return True
            except Exception:
                try:
                    await system.action.disarm()
                    return True
                except Exception:
                    return False

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(asyncio.wait_for(_stop(), timeout))
        except Exception:
            return False
        finally:
            loop.close()
            # MAVSDK spawns a mavsdk_server subprocess that would otherwise leak
            # (and keep its port held) on every reset. Terminate it explicitly.
            proc = getattr(system, "_server_process", None)
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass

    def return_home(self) -> bool:
        """Command return-to-home. Stub: Phase 6 implements RTL via MAVSDK."""
        return self.abort()

    def get_telemetry(self) -> dict:
        return dict(self._latest_telemetry)

    def update_telemetry(self, data: dict) -> None:
        """Called by subprocess stdout parser when a TELEMETRY: line arrives."""
        self._latest_telemetry = data
