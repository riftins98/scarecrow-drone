#!/usr/bin/env python3
"""
Indoor Health Check -- Scarecrow Drone (Holybro X500 V2 + Pixhawk 6X)
=======================================================================
Verifies the SITL is configured for GPS-denied indoor operation matching
the real drone sensor suite:
  - NO GPS (expected -- pass if GPS is absent/unfixed)
  - Barometer active as primary altitude source
  - IMU healthy
  - Rangefinder configured (MTF-01 ToF)
  - Optical flow OFF (enabled in Phase 3)
  - Arming without GPS allowed
"""

import asyncio
import sys
from mavsdk import System

PASS = "PASS"
FAIL = "FAIL"
INFO = "INFO"
WARN = "WARN"

results = []


def record(status, label, value, note=""):
    results.append((status, label, value, note))
    icon = {"PASS": "v", "FAIL": "x", "INFO": " ", "WARN": "!"}.get(status, " ")
    note_str = f"  ({note})" if note else ""
    print(f"  [{icon}] {label:<35} {value}{note_str}")


async def run():
    print("=" * 62)
    print("  Scarecrow Drone -- Indoor Health Check")
    print("  Holybro X500 V2 | Pixhawk 6X | No GPS | Baro Alt")
    print("=" * 62)

    drone = System()
    print("
[1/7] Connection")
    await drone.connect(system_address="udpin://:14550")

    try:
        async with asyncio.timeout(30):
            async for state in drone.core.connection_state():
                if state.is_connected:
                    record(PASS, "MAVLink connection", "udpin://:14550")
                    break
    except asyncio.TimeoutError:
        record(FAIL, "MAVLink connection", "TIMEOUT after 30s")
        _print_summary()
        sys.exit(1)

    print("
[2/7] Firmware")
    try:
        async with asyncio.timeout(10):
            info = await drone.info.get_version()
            fw = f"{info.flight_sw_major}.{info.flight_sw_minor}.{info.flight_sw_patch}"
            record(INFO, "PX4 firmware", fw)
    except asyncio.TimeoutError:
        record(WARN, "Firmware version", "timeout")

    print("
[3/7] Battery")
    try:
        async with asyncio.timeout(10):
            async for bat in drone.telemetry.battery():
                v = bat.voltage_v
                status = PASS if v > 10.0 else FAIL
                record(status, "Battery voltage", f"{v:.2f} V")
                record(INFO, "Battery remaining", f"{bat.remaining_percent:.0f}%")
                break
    except asyncio.TimeoutError:
        record(WARN, "Battery", "timeout")

    print("
[4/7] GPS (expect: no fix)")
    try:
        async with asyncio.timeout(10):
            async for gps in drone.telemetry.gps_info():
                fix = str(gps.fix_type)
                no_gps = "NO_GPS" in fix or gps.num_satellites == 0
                status = PASS if no_gps else WARN
                note = "correct for indoor build" if no_gps else "GPS active -- should be disabled"
                record(status, "GPS fix type", fix, note)
                break
    except asyncio.TimeoutError:
        record(PASS, "GPS", "no data -- correct (no GPS hardware)")

    print("
[5/7] Indoor PX4 Parameters")
    param_checks = [
        ("SYS_HAS_GPS",    0, "No GPS declared"),
        ("EKF2_GPS_CTRL",  0, "GPS fusion disabled"),
        ("COM_ARM_WO_GPS", 1, "Arm without GPS allowed"),
        ("EKF2_HGT_REF",   0, "Baro as height source"),
        ("EKF2_BARO_CTRL", 1, "Barometer enabled"),
        ("EKF2_RNG_CTRL",  1, "Rangefinder enabled"),
        ("EKF2_OF_CTRL",   0, "Optical flow OFF (Phase 3)"),
    ]
    for name, expected, desc in param_checks:
        try:
            val = await drone.param.get_param_int(name)
            ok = val == expected
            status = PASS if ok else FAIL
            note = desc if ok else f"expected {expected}, got {val}"
            record(status, name, str(val), note)
        except Exception as e:
            record(WARN, name, f"unreadable: {e}")

    print("
[6/7] Altitude and IMU")
    try:
        async with asyncio.timeout(10):
            async for pos in drone.telemetry.position():
                record(PASS, "Relative altitude (baro)", f"{pos.relative_altitude_m:.3f} m")
                break
    except asyncio.TimeoutError:
        record(FAIL, "Altitude", "timeout")

    try:
        async with asyncio.timeout(10):
            async for imu in drone.telemetry.imu():
                ax = imu.acceleration_frd.forward_m_s2
                ay = imu.acceleration_frd.right_m_s2
                az = imu.acceleration_frd.down_m_s2
                mag = (ax**2 + ay**2 + az**2) ** 0.5
                healthy = 8.0 < mag < 12.0
                record(PASS if healthy else WARN, "IMU accel magnitude", f"{mag:.2f} m/s2")
                break
    except asyncio.TimeoutError:
        record(WARN, "IMU", "timeout")

    print("
[7/7] Flight Mode and Arm State")
    try:
        async with asyncio.timeout(10):
            async for mode in drone.telemetry.flight_mode():
                record(INFO, "Flight mode", str(mode))
                break
        async with asyncio.timeout(10):
            async for armed in drone.telemetry.armed():
                record(INFO, "Armed", str(armed))
                break
    except asyncio.TimeoutError:
        record(WARN, "Flight mode / armed", "timeout")

    _print_summary()


def _print_summary():
    passes = sum(1 for r in results if r[0] == PASS)
    fails  = sum(1 for r in results if r[0] == FAIL)
    print("
" + "=" * 62)
    print(f"  SUMMARY: {passes} PASS  |  {fails} FAIL  |  {len(results)} checks")
    print("=" * 62)
    if fails == 0:
        print("
  HEALTH CHECK PASSED")
        print("  Ready to proceed to Phase 2.
")
    else:
        print("
  HEALTH CHECK FAILED
")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
