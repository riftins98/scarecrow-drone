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

    def force_disarm(self, timeout: float = 6.0) -> bool:
        """Best-effort force-disarm for a panic reset: connect to the SITL
        MAVSDK endpoint and issue ``action.kill()`` so the motors stop and the
        autopilot won't fly back up after we teleport it to the ground.

        Runs the async MAVSDK calls on a private event loop in this thread, so
        it's safe to call from a sync FastAPI handler. Returns True if the kill
        command was acknowledged; False on any failure (the caller still
        proceeds with the teleport — disarm is best-effort)."""
        import asyncio

        async def _kill() -> bool:
            try:
                from mavsdk import System
            except ImportError:
                return False
            system = System()
            # Same endpoint the flight scripts use (honors the optional
            # externally-launched mavsdk_server env vars).
            await system.connect(system_address="udp://:14540")
            # Wait briefly for a connection before commanding.
            try:
                async for state in system.core.connection_state():
                    if state.is_connected:
                        break
            except Exception:
                return False
            try:
                await system.action.kill()
                return True
            except Exception:
                try:
                    await system.action.disarm()
                    return True
                except Exception:
                    return False

        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(asyncio.wait_for(_kill(), timeout))
            finally:
                loop.close()
        except Exception:
            return False

    def return_home(self) -> bool:
        """Command return-to-home. Stub: Phase 6 implements RTL via MAVSDK."""
        return self.abort()

    def get_telemetry(self) -> dict:
        return dict(self._latest_telemetry)

    def update_telemetry(self, data: dict) -> None:
        """Called by subprocess stdout parser when a TELEMETRY: line arrives."""
        self._latest_telemetry = data
