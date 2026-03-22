# Scarecrow Drone

Autonomous indoor drone project -- Holybro X500 V2 + Pixhawk 6X.

## Hardware
- Frame: Holybro X500 V2
- Flight controller: Pixhawk 6X (PX4 firmware)
- Companion computer: Raspberry Pi 5 8GB
- Camera: Pi Camera Module 3
- Optical flow + downward rangefinder: MTF-01
- Upward LiDAR: TF-Luna
- Battery: HRB 4S 14.8V 5200mAh
- **No GPS -- indoor optical flow navigation**

## Simulation Stack
- PX4 SITL v1.15.4
- Gazebo Harmonic (gz-sim8)
- MAVSDK Python
- Ubuntu 24.04 (via UTM on Mac)

## Setup
```bash
pip install -r requirements.txt
```

## Scripts
- `configure_indoor.py` -- applies GPS-denied indoor PX4 parameters
- `health_check.py` -- verifies indoor sensor configuration

## Phases
- [x] Phase 1: Simulation setup + health check
- [ ] Phase 2: Takeoff, hover, land
- [ ] Phase 3: Optical flow navigation
- [ ] Phase 4: Object detection + scarecrow response
