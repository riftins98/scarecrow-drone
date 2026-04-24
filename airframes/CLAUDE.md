# airframes

PX4 airframe configuration scripts. Copied into `px4/ROMFS/px4fmu_common/init.d-posix/airframes/` by `scripts/shell/launch.sh` before each SITL build.

## Files
- `4022_gz_holybro_x500` — Main airframe script. Sources stock `4001_gz_x500` (Holybro base), then disables GPS (`SYS_HAS_GPS 0`, `SIM_GPS_USED 0`, `EKF2_GPS_CTRL 0`) and allows arming without GPS (`COM_ARM_WO_GPS 1`). Everything else stays at PX4 defaults.
- `4022_gz_holybro_x500.post` — Post-autostart hook: after a 2s delay, runs `commander set_heading 0` so the estimator yaw reference is deterministic. Disabled with `SCARECROW_AUTO_SET_HEADING=0` for debugging.
