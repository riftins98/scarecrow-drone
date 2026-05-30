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

    def force_disarm(self, attempts: int = 3, connect_timeout: float = 14.0,
                     settle: float = 2.0) -> bool:
        """Best-effort force-stop for a panic reset: connect to PX4 and put it
        in a state where it won't fly the drone after we teleport it. First
        commands Hold (exit offboard so it stops chasing setpoints), then kills
        the motors so it can't fly back up.

        Connects on udpin://0.0.0.0:14540 — the same SDK stream the flight
        scripts use; PX4 keeps broadcasting there after the script that was
        listening dies, so a fresh listener reconnects.

        Robustness details, each a bug found the hard way:
        - Runs in a dedicated worker THREAD: the FastAPI reset handler is async,
          and ``run_until_complete`` can't run inside an already-running loop.
        - Uses a FRESH OS-assigned server port per attempt: a hardcoded port
          made the next reset hang in ``connect()`` while the prior server was
          still releasing it.
        - RETRIES with a settle delay: right after one connect/disconnect, PX4
          SITL may briefly refuse a new SDK connection, so a rapid second reset
          would otherwise fail.

        Returns True once Hold/kill is acknowledged; False if all attempts fail
        (the caller still proceeds with the teleport — best-effort)."""
        import asyncio
        import socket
        import threading
        import time

        try:
            from mavsdk import System
        except ImportError:
            return False

        result = {"ok": False}

        def _free_port() -> int:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]
            finally:
                s.close()

        async def _attempt() -> bool:
            system = System(port=_free_port())
            try:
                await system.connect(system_address="udpin://0.0.0.0:14540")
                async for state in system.core.connection_state():
                    if state.is_connected:
                        break
                # 1. Exit offboard so PX4 stops chasing its last setpoint.
                try:
                    await system.action.hold()
                except Exception:
                    pass  # the kill below is what guarantees motors off
                # 2. Force motors off. kill() is instant; disarm() is the fallback.
                try:
                    await system.action.kill()
                    return True
                except Exception:
                    await system.action.disarm()
                    return True
            finally:
                # MAVSDK spawns a mavsdk_server subprocess; terminate it so it
                # doesn't leak or hold its port for the next attempt/reset.
                proc = getattr(system, "_server_process", None)
                if proc is not None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

        def _worker():
            for i in range(attempts):
                loop = asyncio.new_event_loop()
                try:
                    if loop.run_until_complete(
                        asyncio.wait_for(_attempt(), connect_timeout)
                    ):
                        result["ok"] = True
                        return
                except Exception:
                    pass
                finally:
                    loop.close()
                # Let PX4 settle before retrying (and the server fully release).
                if i < attempts - 1:
                    time.sleep(settle)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        # Allow for all attempts + their settle delays, plus a little slack.
        t.join(attempts * connect_timeout + (attempts - 1) * settle + 3)
        return bool(result["ok"])

    def return_home(self) -> bool:
        """Command return-to-home. Stub: Phase 6 implements RTL via MAVSDK."""
        return self.abort()

    def get_telemetry(self) -> dict:
        return dict(self._latest_telemetry)

    def update_telemetry(self, data: dict) -> None:
        """Called by subprocess stdout parser when a TELEMETRY: line arrives."""
        self._latest_telemetry = data
