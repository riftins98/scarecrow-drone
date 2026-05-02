"""High-level drone interface wrapping MAVSDK.

Provides a clean async API for flight scripts. Internally delegates to the
existing flight helpers (`scarecrow.flight.helpers`) so the proven async
patterns are reused verbatim -- no rewrites.

Usage:
    drone = Drone(system_address="udp://:14540")
    await drone.connect()
    await drone.wait_for_health()
    await drone.arm()
    await drone.takeoff(altitude=2.5)
    await drone.start_offboard()
    await drone.set_velocity(VelocityCommand(forward_m_s=0.3))
    ...
    await drone.stop_offboard()
    await drone.land()
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed

from .controllers.wall_follow import VelocityCommand
from .flight.helpers import get_position, wait_for_altitude, wait_for_stable
from .logging_setup import get_logger, log_event, Timer

_log = get_logger("drone")


class Drone:
    """Async drone interface for both simulation and hardware.

    Args:
        system_address: MAVSDK connection string. Sim: 'udp://:14540',
            hardware: 'serial:///dev/ttyACM0:921600'.
        mode: 'sim' or 'hardware'. Only used for labeling/logging; the
            connection string drives the actual transport.
    """

    def __init__(
        self,
        system_address: str = "udp://:14540",
        mode: Literal["sim", "hardware"] = "sim",
    ):
        self._system: System = System()
        self._address = system_address
        self.mode = mode
        self._ground_z: float = 0.0
        self._in_offboard: bool = False
        self._in_air: bool = False
        self._armed: bool = False

    # -- Connection --

    async def connect(self, timeout: float = 30.0) -> bool:
        """Connect to the drone and wait for connection state. Returns True on success."""
        log_event(_log, "connect_request", address=self._address, timeout=timeout, mode=self.mode)
        with Timer(_log, "connect", address=self._address):
            await self._system.connect(system_address=self._address)
            try:
                async with asyncio.timeout(timeout):
                    async for state in self._system.core.connection_state():
                        if state.is_connected:
                            log_event(_log, "connect_ok")
                            return True
            except asyncio.TimeoutError:
                log_event(_log, "connect_timeout")
                return False
        log_event(_log, "connect_failed_no_state")
        return False

    async def wait_for_health(self, timeout: float = 60.0) -> bool:
        """Wait for local position estimate to be OK. Required before arming."""
        log_event(_log, "wait_for_health_begin", timeout=timeout)
        last_state = None
        try:
            async with asyncio.timeout(timeout):
                async for h in self._system.telemetry.health():
                    state = (h.is_local_position_ok, h.is_home_position_ok,
                             h.is_global_position_ok, h.is_armable)
                    if state != last_state:
                        log_event(_log, "health_change",
                                  local_pos=h.is_local_position_ok,
                                  home=h.is_home_position_ok,
                                  global_pos=h.is_global_position_ok,
                                  armable=h.is_armable)
                        last_state = state
                    if h.is_local_position_ok:
                        log_event(_log, "wait_for_health_ok")
                        return True
        except asyncio.TimeoutError:
            log_event(_log, "wait_for_health_timeout")
            return False
        return False

    async def set_ekf_origin(self, verbose: bool = True) -> bool:
        """Set EKF global origin at (0, 0, 0). Required in GPS-denied mode.

        Returns True on success, False on failure. Failure is commonly caused
        by socket issues from a separate shell -- in that case the origin
        must be set manually via `commander set_gps_global_origin 0 0 0`
        in the PX4 pxh> prompt BEFORE running this script.
        """
        try:
            log_event(_log, "set_ekf_origin_request")
            await self._system.action.set_gps_global_origin(0.0, 0.0, 0.0)
            log_event(_log, "set_ekf_origin_ok")
            if verbose:
                print("  EKF origin set (0, 0, 0)")
            return True
        except Exception as e:
            log_event(_log, "set_ekf_origin_fail", error=str(e), error_type=type(e).__name__)
            if verbose:
                print(f"  set_gps_global_origin failed: {e}")
                print("  If arm fails with COMMAND_DENIED, set origin manually in pxh>:")
                print("    commander set_ekf_origin 0 0 0")
            return False

    async def verify_gps_denied_params(self, verbose: bool = True) -> bool:
        """Check PX4 params are configured for GPS-denied navigation.

        Required params:
          EKF2_GPS_CTRL = 0  (GPS disabled)
          EKF2_OF_CTRL  = 1  (Optical flow enabled)
          SYS_HAS_GPS   = 0  (GPS hardware disabled)

        Returns True if all params match expected values. Does NOT modify
        params -- per project constraint, EKF2 params must not be set at runtime.

        Args:
            verbose: Print each param check to stdout.
        """
        expected = {
            "EKF2_GPS_CTRL": (0, "GPS disabled"),
            "EKF2_OF_CTRL": (1, "Optical flow enabled"),
            "SYS_HAS_GPS": (0, "GPS hardware disabled"),
        }
        all_ok = True
        for name, (want, desc) in expected.items():
            try:
                val = int(await self._system.param.get_param_int(name))
            except Exception as e:
                if verbose:
                    print(f"  [FAIL] {name} read error: {e}")
                all_ok = False
                continue
            ok = val == want
            if verbose:
                print(f"  [{'OK' if ok else 'FAIL'}] {name} = {val} -- {desc}")
            if not ok:
                all_ok = False
        return all_ok

    # -- Basic commands --

    async def arm(self, retries: int = 2, retry_delay: float = 1.0) -> None:
        """Arm the vehicle.

        Checks if the drone is ALREADY armed (from a previous session that
        didn't disarm cleanly) and force-disarms it first -- otherwise PX4
        rejects the new arm request with COMMAND_DENIED.

        Retries on transient arm failures which sometimes happen when PX4
        is still finalizing preflight checks.
        """
        log_event(_log, "arm_request", retries=retries, retry_delay=retry_delay)
        if await self._is_currently_armed():
            log_event(_log, "arm_already_armed_killing")
            print("  Drone already armed from previous session -- force-disarming first")
            try:
                await self._system.action.kill()
            except Exception:
                pass
            await asyncio.sleep(1.5)  # give PX4 time to settle

        last_error = None
        for attempt in range(retries + 1):
            try:
                with Timer(_log, "arm_attempt", attempt=attempt):
                    await self._system.action.arm()
                self._armed = True
                log_event(_log, "arm_ok", attempt=attempt)
                return
            except Exception as e:
                last_error = e
                log_event(_log, "arm_fail", attempt=attempt,
                          error=str(e), error_type=type(e).__name__)
                if attempt < retries:
                    await asyncio.sleep(retry_delay)
        if last_error is not None:
            log_event(_log, "arm_giving_up")
            raise last_error

    async def _is_currently_armed(self) -> bool:
        """Check the live armed state from PX4 telemetry.

        Returns True if a previous session left the drone armed. Best-effort --
        returns False if the telemetry stream doesn't respond quickly.
        """
        try:
            async with asyncio.timeout(2.0):
                async for armed in self._system.telemetry.armed():
                    return bool(armed)
        except (asyncio.TimeoutError, Exception):
            pass
        return False

    async def disarm(self, force_kill_on_failure: bool = True) -> bool:
        """Disarm the vehicle. If disarm fails and force_kill_on_failure is True,
        falls back to action.kill() to force motors off.

        Returns True if motors are guaranteed off (either disarm or kill worked),
        False if both failed.
        """
        log_event(_log, "disarm_request", force_kill_on_failure=force_kill_on_failure)
        try:
            await self._system.action.disarm()
            self._armed = False
            log_event(_log, "disarm_ok")
            return True
        except Exception as e:
            log_event(_log, "disarm_fail", error=str(e), error_type=type(e).__name__)
            if not force_kill_on_failure:
                raise
            print(f"  disarm failed ({e}) -- forcing motor kill")
            try:
                await self._system.action.kill()
                self._armed = False
                log_event(_log, "kill_ok")
                return True
            except Exception as kill_error:
                log_event(_log, "kill_fail", error=str(kill_error), error_type=type(kill_error).__name__)
                print(f"  kill also failed: {kill_error}")
                return False

    async def prepare_takeoff(self, altitude: float = 2.5, settle_delay: float = 0.5):
        """Pre-arm setup for takeoff: record ground_z and set altitude.

        IMPORTANT: Call this BEFORE arm(). PX4 reads the position stream and
        takeoff altitude during preflight checks -- calling them after arm
        causes COMMAND_DENIED on subsequent commands.

        Returns the ground position so callers don't need a second get_position()
        call (which would open a redundant telemetry subscription).

        Args:
            altitude: Target takeoff altitude (meters AGL).
            settle_delay: Seconds to wait after set_takeoff_altitude to let PX4
                finalize preflight state. Empirically prevents intermittent
                COMMAND_DENIED on arm().
        """
        ground = await get_position(self._system)
        self._ground_z = ground.position.down_m
        await self._system.action.set_takeoff_altitude(altitude)
        if settle_delay > 0:
            await asyncio.sleep(settle_delay)
        return ground

    async def takeoff(self, altitude: float = 2.5, timeout: float | None = None) -> bool:
        """Take off to target altitude AGL.

        If prepare_takeoff() was not called first, this runs it now (but the
        caller should prefer calling prepare_takeoff() explicitly before arm()).

        timeout=None lets wait_for_altitude pick the default, which respects
        $SCARECROW_TAKEOFF_TIMEOUT (set on WSL by scripts/shell/env.sh).
        """
        log_event(_log, "takeoff_request", altitude=altitude, timeout=timeout)
        if self._ground_z == 0.0:
            await self.prepare_takeoff(altitude)
        with Timer(_log, "takeoff", altitude=altitude):
            await self._system.action.takeoff()
            ok = await wait_for_altitude(self._system, altitude, self._ground_z, timeout=timeout)
            if ok:
                log_event(_log, "altitude_reached", altitude=altitude)
                await wait_for_stable(self._system, self._ground_z)
                self._in_air = True
                log_event(_log, "takeoff_stable")
            else:
                log_event(_log, "takeoff_timeout", altitude=altitude)
        return ok

    async def land(self) -> None:
        log_event(_log, "land_request")
        await self._system.action.land()
        self._in_air = False
        log_event(_log, "land_command_sent")

    async def return_home(self) -> None:
        """Return-to-launch."""
        await self._system.action.return_to_launch()

    async def emergency_stop(self) -> None:
        """Stop offboard and land immediately. Safe to call from any state."""
        if self._in_offboard:
            try:
                await self._system.offboard.stop()
            except Exception:
                pass
            self._in_offboard = False
        try:
            await self._system.action.land()
        except Exception:
            pass
        self._in_air = False

    # -- Offboard control --

    async def start_offboard(self) -> bool:
        """Enter offboard mode. Sends an initial zero-velocity setpoint first
        (required by PX4 before mode switch)."""
        log_event(_log, "offboard_start_request")
        await self._system.offboard.set_velocity_body(
            VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
        )
        try:
            await self._system.offboard.start()
            self._in_offboard = True
            log_event(_log, "offboard_start_ok")
            return True
        except Exception as e:
            log_event(_log, "offboard_start_fail", error=str(e), error_type=type(e).__name__)
            return False

    async def stop_offboard(self) -> None:
        if self._in_offboard:
            log_event(_log, "offboard_stop_request")
            try:
                await self._system.offboard.stop()
                log_event(_log, "offboard_stop_ok")
            except Exception as e:
                log_event(_log, "offboard_stop_fail", error=str(e), error_type=type(e).__name__)
            self._in_offboard = False

    async def set_velocity(self, cmd: VelocityCommand) -> None:
        """Send a body-frame velocity setpoint."""
        await self._system.offboard.set_velocity_body(
            VelocityBodyYawspeed(
                cmd.forward_m_s,
                cmd.right_m_s,
                cmd.down_m_s,
                cmd.yawspeed_deg_s,
            )
        )

    # -- Telemetry --

    async def get_position(self):
        """Current NED position + velocity."""
        return await get_position(self._system)

    async def get_yaw(self) -> float:
        """Current yaw in degrees (-180 to 180)."""
        async for att in self._system.telemetry.attitude_euler():
            return att.yaw_deg

    async def get_battery(self) -> Optional[float]:
        """Battery remaining percentage (0-100) or None if unavailable."""
        try:
            async for bat in self._system.telemetry.battery():
                return bat.remaining_percent * 100.0
        except Exception:
            return None

    # -- Properties --

    @property
    def ground_z(self) -> float:
        return self._ground_z

    @property
    def is_armed(self) -> bool:
        return self._armed

    @property
    def is_in_air(self) -> bool:
        return self._in_air

    @property
    def is_in_offboard(self) -> bool:
        return self._in_offboard

    @property
    def system(self) -> System:
        """Underlying MAVSDK System. Use only when raw access is required
        (e.g. passing to legacy helpers like `rotate_90`)."""
        return self._system
