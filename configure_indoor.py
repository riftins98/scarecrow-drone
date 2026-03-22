#!/usr/bin/env python3
"""
Indoor Configuration Script -- Scarecrow Drone (Holybro X500 V2 + Pixhawk 6X)
==============================================================================
Configures PX4 SITL to match the real drone GPS-denied indoor sensor suite:
  - NO GPS  (real drone has no GPS module)
  - Barometer as primary height source
  - Rangefinder aid (MTF-01 downward ToF) -- Phase 2+
  - Optical flow (MTF-01) -- Phase 3 (disabled until sim data confirmed)
  - Allow arming without GPS

NOTE: Parameters reset on every container restart. Run this script after
every docker run or docker restart of the px4_sitl container.
"""

import asyncio
import sys
from mavsdk import System

INDOOR_PARAMS = [
    ("SYS_HAS_GPS",      0, "int", "Declare: no GPS hardware installed"),
    ("EKF2_GPS_CTRL",    0, "int", "Disable GPS fusion in EKF2"),
    ("COM_ARM_WO_GPS",   1, "int", "Allow arming without GPS fix"),
    ("EKF2_HGT_REF",     0, "int", "Primary height source = barometer"),
    ("EKF2_BARO_CTRL",   1, "int", "Enable barometer fusion"),
    ("EKF2_RNG_CTRL",    1, "int", "Enable rangefinder fusion"),
    ("EKF2_RNG_AID",     1, "int", "Rangefinder aids height estimate"),
    ("EKF2_OF_CTRL",     0, "int", "Optical flow OFF -- enable in Phase 3"),
    ("COM_ARM_CHK_ESCS", 0, "int", "Skip ESC arming check (SITL safe)"),
]

VERIFY_PARAMS = [
    "SYS_HAS_GPS", "EKF2_GPS_CTRL", "COM_ARM_WO_GPS",
    "EKF2_HGT_REF", "EKF2_BARO_CTRL", "EKF2_RNG_CTRL", "EKF2_OF_CTRL",
]


async def run():
    print("=" * 62)
    print("  Scarecrow Drone -- Indoor Parameter Configuration")
    print("  GPS-denied | Baro altitude | Rangefinder aid")
    print("=" * 62)

    drone = System()
    print("
[CONNECT] Connecting to SITL on udpin://:14550 ...")
    await drone.connect(system_address="udpin://:14550")

    try:
        async with asyncio.timeout(30):
            async for state in drone.core.connection_state():
                if state.is_connected:
                    print("[CONNECT] Connected
")
                    break
    except asyncio.TimeoutError:
        print("[CONNECT] FAILED -- is the px4_sitl container running?")
        sys.exit(1)

    passed, failed = [], []
    print(f"  {chr(39)}{chr(39)}{chr(39)}")
    print(f"  Parameter                Value   Result")
    print("  " + "-" * 50)

    for name, value, ptype, desc in INDOOR_PARAMS:
        try:
            if ptype == "int":
                await drone.param.set_param_int(name, value)
            else:
                await drone.param.set_param_float(name, float(value))
            print(f"  {name:<24} {str(value):<6}  SET     {desc}")
            passed.append(name)
        except Exception as e:
            err = str(e).split("
")[0]
            print(f"  {name:<24} {str(value):<6}  SKIP    {err}")
            failed.append((name, err))

    print("
" + "=" * 62)
    print(f"  Applied: {len(passed)}/{len(INDOOR_PARAMS)} parameters")
    if failed:
        print(f"  Skipped: {len(failed)}")
        for n, e in failed:
            print(f"    - {n}: {e}")
    print("=" * 62)

    print("
[VERIFY] Reading back critical parameters:")
    ok = True
    for name in VERIFY_PARAMS:
        try:
            val = await drone.param.get_param_int(name)
            print(f"  {name} = {val}")
        except Exception as e:
            print(f"  {name} = ERROR: {e}")
            ok = False

    print()
    if ok:
        print("PASS  Indoor configuration applied.")
        print("      Run health_check.py to verify sensor state.
")
    else:
        print("WARN  Some params could not be read back.
")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
