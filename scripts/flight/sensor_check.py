#!/usr/bin/env python3
"""
Scarecrow Drone — Sensor Demonstration

Captures data from all 3 active sensors and produces visual outputs:
  1. 2D Lidar (RPLidar A1M8) → top-down scan plot (PDF)
  2. Mono Camera (Pi Camera 3) → saved frame (PNG)
  3. Optical Flow (MTF-01) → flow quality + rate log

Requires: Gazebo running with the indoor_room world and the drone spawned.
Run after launch.sh and PX4 is ready.

Usage:
  source .venv-mavsdk/bin/activate
  python3 scripts/sensor_demo.py
"""

import json
import math
import os
import struct
import subprocess
import sys
import time

import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from PIL import Image

# --- Config ---
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")


def get_gz_env():
    """Get Gazebo environment variables."""
    env = os.environ.copy()
    gz_ip = env.get("GZ_IP", "")
    if not gz_ip:
        try:
            result = subprocess.run(
                ["ipconfig", "getifaddr", "en0"],
                capture_output=True, text=True, timeout=3
            )
            gz_ip = result.stdout.strip()
        except Exception:
            gz_ip = "127.0.0.1"
    env["GZ_IP"] = gz_ip
    env["GZ_PARTITION"] = "px4"
    return env


def capture_gz_topic(topic, timeout=5):
    """Capture one message from a Gazebo topic."""
    env = get_gz_env()
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", topic],
            capture_output=True, text=True, timeout=timeout, env=env
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"  Error capturing topic: {e}")
        return None


def capture_lidar_scan():
    """Capture 2D lidar scan and produce a top-down plot."""
    print("\n--- 2D Lidar (RPLidar A1M8) ---")

    # Use scarecrow lidar package for correct parsing
    from scarecrow.sensors.lidar.gazebo import GazeboLidar
    import time

    lidar = GazeboLidar(num_threads=2)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    # Wait for scan
    scan = None
    for _ in range(20):
        time.sleep(0.5)
        scan = lidar.get_scan()
        if scan is not None:
            break

    lidar.stop()

    if scan is None:
        print("  ERROR: No lidar data received")
        return False

    print(f"  Got {scan.num_samples} range measurements")
    print(f"  Front: {scan.front_distance():.1f}m  Left: {scan.left_distance():.1f}m  Right: {scan.right_distance():.1f}m")

    # Convert to cartesian (body frame: x=forward, y=left)
    angles = scan.angles
    ranges = scan.ranges
    valid = (ranges > 0.1) & (ranges < 30.0)

    bx = ranges[valid] * np.cos(angles[valid])  # forward
    by = ranges[valid] * np.sin(angles[valid])   # left

    # Plot coords: forward = UP, left = LEFT (bird's eye view, north up)
    x = -by   # left in body → left in plot (negate so right = positive X)
    y = bx    # forward in body → up in plot

    # Plot
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.set_aspect('equal')
    ax.scatter(x, y, s=1, c='blue', alpha=0.7, label='Lidar scan')
    ax.plot(0, 0, 'r^', markersize=15, label='Drone', zorder=5)

    # Room boundary (20m x 20m, centered at world origin)
    # Drone is NOT at world origin — we don't know exact position here,
    # so just show the scan data without room overlay
    ax.annotate('', xy=(0, 1.5), xytext=(0, 0.3),
                arrowprops=dict(arrowstyle='->', color='red', lw=2))
    ax.text(0.2, 1.0, 'FWD', color='red', fontsize=9, fontweight='bold')

    ax.set_xlabel('Right (m)', fontsize=12)
    ax.set_ylabel('Forward (m)', fontsize=12)
    ax.set_title(f'2D Lidar Scan — RPLidar A1M8 ({scan.num_samples} samples, 360°)', fontsize=14)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-12, 12)
    ax.set_ylim(-12, 12)

    outpath = os.path.join(OUTPUT_DIR, "lidar_scan.pdf")
    fig.savefig(outpath, bbox_inches='tight', dpi=150)
    plt.close(fig)
    print(f"  Saved: {outpath}")
    return True


def capture_camera_frame():
    """Capture a mono camera frame and save as PNG."""
    print("\n--- Mono Camera (Pi Camera 3) ---")

    topic = "/world/indoor_room/model/holybro_x500_0/link/camera_link/sensor/camera/image"
    print(f"  Capturing frame from: {topic}")

    env = get_gz_env()
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", topic],
            capture_output=True, timeout=15, env=env
        )
    except subprocess.TimeoutExpired:
        print("  ERROR: Timeout capturing camera")
        return False

    from scarecrow.sensors.camera.gazebo import parse_gz_frame
    pixels_bgr = parse_gz_frame(result.stdout)
    if pixels_bgr is None:
        print("  ERROR: Could not parse camera frame")
        return False

    height, width = pixels_bgr.shape[:2]
    pixels_rgb = pixels_bgr[:, :, ::-1]
    print(f"  Image: {width}x{height}, RGB")

    img = Image.fromarray(pixels_rgb)
    outpath = os.path.join(OUTPUT_DIR, "camera_frame.png")
    img.save(outpath)
    print(f"  Saved: {outpath}")
    return True


def capture_optical_flow():
    """Capture optical flow data and display."""
    print("\n--- Optical Flow (MTF-01) ---")

    topic = "/world/indoor_room/model/holybro_x500_0/link/flow_link/sensor/optical_flow/optical_flow"
    print(f"  Capturing flow from: {topic}")

    data = capture_gz_topic(topic, timeout=10)
    if not data:
        # Flow may not publish when stationary — check camera instead
        cam_topic = "/world/indoor_room/model/holybro_x500_0/link/flow_link/sensor/flow_camera/image"
        cam_data = capture_gz_topic(cam_topic, timeout=5)
        if cam_data:
            print("  Flow camera is active (publishing images)")
            print("  Optical flow publishes when drone is in motion")
            # Get PX4's processed flow data
            return capture_px4_flow()
        else:
            print("  ERROR: No optical flow or camera data")
            return False

    # Parse flow data
    quality = 0
    integrated_x = integrated_y = 0.0
    for line in data.split('\n'):
        line = line.strip()
        if line.startswith('quality:'):
            quality = int(line.split(':')[1].strip())
        elif line.startswith('integrated_x:'):
            integrated_x = float(line.split(':')[1].strip())
        elif line.startswith('integrated_y:'):
            integrated_y = float(line.split(':')[1].strip())

    print(f"  Quality: {quality}/255")
    print(f"  Flow X: {integrated_x:.6f} rad")
    print(f"  Flow Y: {integrated_y:.6f} rad")

    create_flow_chart(quality, integrated_x, integrated_y)
    return True


def capture_px4_flow():
    """Get optical flow data from PX4's uORB."""
    try:
        bin_dir = os.path.join(
            os.environ.get("PX4_DIR", "px4"),
            "build/px4_sitl_default/bin"
        )
        result = subprocess.run(
            [f"{bin_dir}/px4-listener", "vehicle_optical_flow", "-n", "1"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout
        quality = 0
        for line in output.split('\n'):
            if 'quality:' in line:
                quality = int(line.split(':')[1].strip())
        print(f"  PX4 vehicle_optical_flow quality: {quality}/255")
        create_flow_chart(quality, 0.0, 0.0)
        return True
    except Exception as e:
        print(f"  Could not read PX4 flow data: {e}")
        return False


def create_flow_chart(quality, flow_x, flow_y):
    """Create optical flow visualization."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Quality gauge
    colors = ['#ff4444' if quality < 50 else '#ffaa00' if quality < 150 else '#44cc44']
    ax1.barh(['Quality'], [quality], color=colors, height=0.5)
    ax1.set_xlim(0, 255)
    ax1.set_xlabel('Quality (0-255)')
    ax1.set_title('Optical Flow Quality — MTF-01', fontsize=14)
    ax1.axvline(x=50, color='red', linestyle=':', alpha=0.5, label='Min threshold')
    ax1.text(quality + 5, 0, f'{quality}', va='center', fontsize=14, fontweight='bold')
    ax1.legend()

    # Flow vector
    ax2.set_aspect('equal')
    ax2.set_xlim(-0.01, 0.01)
    ax2.set_ylim(-0.01, 0.01)
    ax2.arrow(0, 0, flow_x * 100, flow_y * 100,
              head_width=0.001, head_length=0.0005, fc='blue', ec='blue')
    ax2.plot(0, 0, 'ko', markersize=5)
    ax2.set_xlabel('Flow X (rad)')
    ax2.set_ylabel('Flow Y (rad)')
    ax2.set_title('Flow Vector (stationary = near zero)', fontsize=14)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='gray', linewidth=0.5)
    ax2.axvline(x=0, color='gray', linewidth=0.5)

    outpath = os.path.join(OUTPUT_DIR, "optical_flow.pdf")
    fig.savefig(outpath, bbox_inches='tight', dpi=150)
    plt.close(fig)
    print(f"  Saved: {outpath}")


def capture_rangefinder():
    """Capture downward rangefinder reading."""
    print("\n--- Downward Rangefinder (TF-Luna) ---")

    topic = "/world/indoor_room/model/holybro_x500_0/link/lidar_sensor_link/sensor/lidar/scan"
    print(f"  Capturing from: {topic}")

    data = capture_gz_topic(topic, timeout=10)
    if not data:
        print("  ERROR: No rangefinder data")
        return False

    # Parse range (field is 'ranges:' in Gazebo protobuf text)
    for line in data.split('\n'):
        line = line.strip()
        if line.startswith('ranges:'):
            try:
                val = float(line.split(':')[1].strip())
                print(f"  Height above ground: {val:.3f}m")
                return True
            except ValueError:
                pass

    print("  ERROR: Could not parse range")
    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 55)
    print("  SCARECROW DRONE — SENSOR DEMONSTRATION")
    print("=" * 55)

    # Check Gazebo is running
    env = get_gz_env()
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"], capture_output=True, text=True, timeout=5, env=env
        )
        if "holybro_x500_0" not in result.stdout:
            print("\nERROR: Drone not found in Gazebo. Run launch.sh first.")
            sys.exit(1)
    except Exception:
        print("\nERROR: Cannot connect to Gazebo.")
        sys.exit(1)

    print("\nDrone detected in Gazebo. Capturing sensor data...\n")

    results = {}
    results['rangefinder'] = capture_rangefinder()
    results['lidar'] = capture_lidar_scan()
    results['camera'] = capture_camera_frame()
    results['flow'] = capture_optical_flow()

    # Summary
    print("\n" + "=" * 55)
    print("  SENSOR DEMO RESULTS")
    print("=" * 55)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  [{status:6s}] {name}")
    print(f"\n  Output files in: {OUTPUT_DIR}/")
    print("=" * 55)


if __name__ == "__main__":
    main()
