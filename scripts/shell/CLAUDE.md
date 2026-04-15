# shell

Bash scripts for launching and configuring the simulation environment.

## Files
- `launch.sh` — Main sim launcher: kills old PX4/gz processes, copies custom airframes+models+worlds into px4/Tools/simulation/gz/, builds PX4 SITL, launches with selected world. Usage: `./scripts/shell/launch.sh [world_name]` (default: drone_garage). Must `source env.sh` first.
- `env.sh` — Sets environment variables for Gazebo/PX4 paths. Must be sourced before launch.sh: `source scripts/shell/env.sh`
