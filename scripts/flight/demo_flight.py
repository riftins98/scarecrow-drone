#!/usr/bin/env python3
"""
Scarecrow Drone — Hover Test (MAVSDK)

GPS-denied indoor flight using ONLY:
  - Optical flow (MTF-01) for horizontal velocity
  - Downward rangefinder (TF-Luna) for height
  - 2D lidar (RPLidar A1M8) for obstacle avoidance
  - Mono camera (Pi Camera 3) for visual awareness

Sequence: arm -> takeoff to 1m -> hover 5s -> land
Records camera video throughout flight.
Captures lidar scan + optical flow snapshot at hover.

This script runs identically on simulation and real hardware.
Only the connection string changes:
  Sim:  udp://:14540
  Real: serial:///dev/ttyACM0:921600
"""

import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import asyncio
import re
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
from mavsdk import System

# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5  # meters above ground
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")


def get_gz_env():
    """Get environment for Gazebo CLI commands. Auto-detects whether GZ_IP is needed."""
    env = os.environ.copy()

    # Try without GZ_IP first (works in non-standalone/GUI mode)
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"], capture_output=True, text=True, timeout=3, env=env
        )
        if "holybro_x500" in result.stdout:
            return env
    except Exception:
        pass

    # Try with GZ_IP (needed in standalone mode with GZ_PARTITION)
    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            capture_output=True, text=True, timeout=3
        )
        env["GZ_IP"] = result.stdout.strip()
    except Exception:
        pass
    env["GZ_PARTITION"] = "px4"
    return env


def get_gz_topics():
    """Get all Gazebo topics."""
    env = get_gz_env()
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True, text=True, timeout=5, env=env
        )
        return result.stdout
    except Exception:
        return ""


def find_topic(pattern):
    """Find a Gazebo topic matching the pattern."""
    for line in get_gz_topics().split('\n'):
        if pattern in line:
            return line.strip()
    return None


def find_camera_topic():
    """Find the camera image topic."""
    return find_topic("camera_link/sensor/camera/image")


def capture_camera_frame(topic, env):
    """Capture one camera frame and return as numpy array."""
    try:
        # Use raw bytes mode to avoid text encoding issues
        result = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", topic],
            capture_output=True, timeout=10, env=env
        )
        raw = result.stdout
    except Exception:
        return None

    # Parse width/height from the text portion
    text = raw.decode('latin-1', errors='replace')
    width = height = 0
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('width:'):
            try: width = int(line.split(':')[1].strip())
            except: pass
        elif line.startswith('height:'):
            try: height = int(line.split(':')[1].strip())
            except: pass

    if width == 0 or height == 0:
        return None

    # Find raw pixel data: look for the RGB data by size
    expected = width * height * 3
    # The pixel data starts after 'data: "' and is the bulk of the output
    # Find it by looking for the largest contiguous block
    idx = raw.find(b'data: "')
    if idx < 0:
        return None

    # Skip past 'data: "'
    start = idx + 7
    # Find closing quote — but the data may contain quotes, so use expected size
    # Extract expected bytes worth of data
    pixel_data = raw[start:start + expected + 1000]  # grab extra for escape overhead

    # Unescape the protobuf text encoding
    try:
        # Simple unescape: handle \n, \\, \", \ooo (octal), \xNN
        unescaped = bytearray()
        i = 0
        while i < len(pixel_data) and len(unescaped) < expected:
            b = pixel_data[i]
            if b == ord('\\') and i + 1 < len(pixel_data):
                nb = pixel_data[i + 1]
                if nb == ord('n'):
                    unescaped.append(10)
                    i += 2
                elif nb == ord('\\'):
                    unescaped.append(92)
                    i += 2
                elif nb == ord('"'):
                    unescaped.append(34)
                    i += 2
                elif nb == ord('t'):
                    unescaped.append(9)
                    i += 2
                elif nb == ord('r'):
                    unescaped.append(13)
                    i += 2
                elif nb == ord('x') and i + 3 < len(pixel_data):
                    try:
                        val = int(pixel_data[i+2:i+4], 16)
                        unescaped.append(val)
                        i += 4
                    except ValueError:
                        unescaped.append(b)
                        i += 1
                elif ord('0') <= nb <= ord('7'):
                    # Octal escape: up to 3 digits
                    end = i + 2
                    while end < min(i + 5, len(pixel_data)) and ord('0') <= pixel_data[end] <= ord('7'):
                        end += 1
                    try:
                        val = int(pixel_data[i+1:end], 8)
                        unescaped.append(val & 0xFF)
                    except ValueError:
                        unescaped.append(b)
                    i = end
                else:
                    unescaped.append(b)
                    i += 1
            elif b == ord('"'):
                break  # end of data field
            else:
                unescaped.append(b)
                i += 1

        if len(unescaped) < expected:
            return None

        pixels = np.frombuffer(bytes(unescaped[:expected]), dtype=np.uint8).reshape((height, width, 3))
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


class CameraRecorder:
    """Saves raw gz topic dumps during flight, builds video with ffmpeg after landing."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.topic = None
        self.env = None
        self.tmp_dir = os.path.join(OUTPUT_DIR, ".camera_raw")
        self.start_time = None
        self.stop_time = None

    def start(self):
        self.running = True
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.thread = threading.Thread(target=self._capture, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)

    def _capture(self):
        """Save raw gz topic output to files. No parsing — just bytes to disk."""
        if not self.topic:
            print("  [camera] Topic not found")
            return

        print(f"  [camera] Recording...")
        self.start_time = time.time()
        self._frame_count = 0
        self._lock = threading.Lock()

        def grab_frames():
            while self.running:
                try:
                    result = subprocess.run(
                        ["gz", "topic", "-e", "-n", "1", "-t", self.topic],
                        capture_output=True, timeout=8, env=self.env
                    )
                    if result.returncode == 0 and len(result.stdout) > 100000:
                        with self._lock:
                            n = self._frame_count
                            self._frame_count += 1
                        outfile = os.path.join(self.tmp_dir, f"raw_{n:04d}.bin")
                        with open(outfile, 'wb') as f:
                            f.write(result.stdout)
                except Exception:
                    pass

        # Run 4 capture threads in parallel for higher frame rate
        workers = []
        for _ in range(4):
            t = threading.Thread(target=grab_frames, daemon=True)
            t.start()
            workers.append(t)

        # Wait until recording stops
        while self.running:
            time.sleep(0.1)

        # Wait for workers to finish current frame
        for t in workers:
            t.join(timeout=3)

        self.stop_time = time.time()
        print(f"  [camera] Captured {self._frame_count} raw frames")

    def save_video(self):
        """Parse raw dumps into PNGs, stitch into MP4 with ffmpeg."""
        import glob
        import shutil

        raw_files = sorted(glob.glob(os.path.join(self.tmp_dir, "raw_*.bin")))
        if not raw_files:
            print("  [camera] No frames captured")
            return

        # Parse each raw dump into a PNG
        png_dir = os.path.join(OUTPUT_DIR, ".camera_png")
        os.makedirs(png_dir, exist_ok=True)
        good = 0

        for i, rawfile in enumerate(raw_files):
            try:
                with open(rawfile, 'rb') as f:
                    raw = f.read()
                frame = self._parse_frame(raw)
                if frame is not None:
                    cv2.imwrite(os.path.join(png_dir, f"frame_{good:04d}.png"), frame)
                    good += 1
            except Exception:
                pass

        print(f"  [camera] Decoded {good}/{len(raw_files)} frames")

        if good == 0:
            print("  [camera] No valid frames")
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            shutil.rmtree(png_dir, ignore_errors=True)
            return

        # Save first and last as standalone PNGs
        first_png = os.path.join(png_dir, "frame_0000.png")
        last_png = os.path.join(png_dir, f"frame_{good-1:04d}.png")
        shutil.copy2(first_png, os.path.join(OUTPUT_DIR, "camera_ground.png"))
        shutil.copy2(last_png, os.path.join(OUTPUT_DIR, "camera_flight.png"))
        print("  [camera] Saved camera_ground.png + camera_flight.png")

        # Stitch into MP4 with ffmpeg at real-time framerate
        duration = (self.stop_time - self.start_time) if (self.start_time and self.stop_time) else 14
        real_fps = max(1, good / max(duration, 1))
        print(f"  [camera] Real framerate: {real_fps:.1f} fps ({good} frames / {duration:.1f}s)")

        outpath = os.path.join(OUTPUT_DIR, "flight_camera.mp4")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-framerate", str(round(real_fps, 1)),
                "-i", os.path.join(png_dir, "frame_%04d.png"),
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-pix_fmt", "yuv420p",
                outpath
            ], capture_output=True, timeout=120)
            if os.path.exists(outpath):
                size = os.path.getsize(outpath)
                print(f"  [camera] Video: {outpath} ({size // 1024}KB)")
            else:
                print("  [camera] ffmpeg failed to create video")
        except Exception as e:
            print(f"  [camera] ffmpeg error: {e}")

        # Cleanup
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(png_dir, ignore_errors=True)

    def _parse_frame(self, raw):
        """Parse raw gz topic dump into BGR numpy array."""
        text = raw.decode('latin-1', errors='replace')
        width = height = 0
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('width:'):
                try: width = int(line.split(':')[1].strip())
                except: pass
            elif line.startswith('height:'):
                try: height = int(line.split(':')[1].strip())
                except: pass

        if width == 0 or height == 0:
            return None

        expected = width * height * 3
        match = re.search(rb'data: "(.*?)"', raw, re.DOTALL)
        if not match:
            return None

        try:
            decoded = match.group(1).decode('unicode_escape').encode('latin-1')
            if len(decoded) < expected:
                return None
            pixels = np.frombuffer(decoded[:expected], dtype=np.uint8).reshape((height, width, 3))
            return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
        except Exception:
            return None


async def get_position(drone):
    """Read current NED position once."""
    async for pos in drone.telemetry.position_velocity_ned():
        return pos


async def run():
    drone = System()
    print("Connecting to drone...")
    await drone.connect(system_address=SYSTEM_ADDRESS)

    print("Waiting for connection...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Connected!")
            break

    print("Waiting for position estimate...")
    async for health in drone.telemetry.health():
        if health.is_local_position_ok:
            print("Position estimate OK")
            break

    # --- Verify sensor configuration ---
    print("\n" + "=" * 55)
    print("  SENSOR VERIFICATION — GPS-Denied Navigation")
    print("=" * 55)
    params_check = {
        'EKF2_GPS_CTRL':  (0, "GPS disabled"),
        'EKF2_OF_CTRL':   (1, "Optical flow enabled"),
        'SYS_HAS_GPS':    (0, "GPS hardware disabled"),
    }
    all_ok = True
    for name, (expected, desc) in params_check.items():
        val = int(await drone.param.get_param_int(name))
        ok = val == expected
        print(f"  [{'OK' if ok else 'FAIL'}] {name} = {val} -- {desc}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nSensor config mismatch! Aborting.")
        return

    print("\n  All params OK: optical flow + rangefinder navigation")
    print("=" * 55)

    # --- Verify Gazebo sensor topics ---
    print("\n--- Gazebo Sensor Topics ---")
    await verify_gz_sensors()

    # --- Pre-flight Setup ---
    # NOTE: Before running, set heading in pxh>: commander set_heading 0
    print("\n--- Pre-flight Setup ---")
    try:
        await drone.action.set_gps_global_origin(0.0, 0.0, 0.0)
        print("  EKF origin set (0, 0, 0)")
    except Exception as e:
        print(f"  set_gps_global_origin failed: {e}")
    print("  (heading must be set manually: commander set_heading 0)")

    # --- Read ground position ---
    await asyncio.sleep(2)
    ground = await get_position(drone)
    ground_z = ground.position.down_m
    print("\n--- Flight Sequence ---")
    print(f"  Ground reference: z={ground_z:.3f} (NED)")
    await log_position(drone, "GROUND", ground_z)

    # --- Start camera recording (runs throughout flight) ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    camera = CameraRecorder()
    # Pre-resolve topic and env on main thread (background thread may not have GZ_IP)
    camera.topic = find_camera_topic()
    camera.env = get_gz_env()
    if camera.topic:
        print(f"  Camera topic: {camera.topic}")
    camera.start()

    # --- Set takeoff altitude and arm ---
    print(f"\nSetting takeoff altitude to {TARGET_ALT}m...")
    await drone.action.set_takeoff_altitude(TARGET_ALT)

    print("Arming...")
    await drone.action.arm()
    print("Armed!")

    # --- Takeoff ---
    print(f"Taking off to {TARGET_ALT}m...")
    await drone.action.takeoff()

    for i in range(20):
        await asyncio.sleep(0.5)
        await log_position(drone, f"TAKEOFF {i*0.5:.1f}s", ground_z)

    # --- Hover + lidar/flow snapshot ---
    print(f"\nHovering at {TARGET_ALT}m...")

    # Capture lidar + flow in background thread
    sensor_thread = threading.Thread(target=capture_lidar_and_flow, daemon=True)
    sensor_thread.start()

    for i in range(10):
        await asyncio.sleep(0.5)
        await log_position(drone, f"HOVER  {i*0.5:.1f}s", ground_z)

    sensor_thread.join(timeout=3)

    # --- Land ---
    print("\nLanding...")
    await drone.action.land()

    for i in range(30):
        await asyncio.sleep(0.5)
        await log_position(drone, f"LAND   {i*0.5:.1f}s", ground_z)

    # Wait for disarm (PX4 auto-disarms after landing)
    print("\nWaiting for disarm...")
    try:
        disarm_timeout = asyncio.get_event_loop().time() + 15
        async for armed in drone.telemetry.armed():
            if not armed:
                print("  Disarmed!")
                break
            if asyncio.get_event_loop().time() > disarm_timeout:
                print("  Timeout — disarming")
                await drone.action.disarm()
                break
    except Exception:
        pass

    # --- Stop camera recording and build video ---
    camera.stop()
    print("\nBuilding outputs...")
    camera.save_video()

    print("\n" + "=" * 55)
    print("  FLIGHT COMPLETE")
    print("  Navigation: optical flow + rangefinder (NO GPS)")
    print(f"  Outputs in: {OUTPUT_DIR}/")
    print("    - flight_camera.mp4 (camera video)")
    print("    - lidar_scan.pdf    (2D lidar)")
    print("    - optical_flow.pdf  (flow quality)")
    print("=" * 55)


async def log_position(drone, phase, ground_z):
    """Log height above ground and velocity."""
    pos = await get_position(drone)
    agl = -(pos.position.down_m - ground_z)
    vz = pos.velocity.down_m_s
    n = pos.position.north_m
    e = pos.position.east_m
    print(f"  [{phase:12s}] agl={agl:6.3f}m  vz={vz:+.3f}  n={n:+.3f} e={e:+.3f}")


def capture_lidar_and_flow():
    """Capture lidar scan and optical flow data (fast, no camera — camera is already recording video)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    env = get_gz_env()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Lidar scan ---
    try:
        lidar_topic = find_topic("lidar_2d_v2/scan")
        if not lidar_topic:
            print("  Lidar topic not found")
            return
        result = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", lidar_topic],
            capture_output=True, text=True, timeout=5, env=env
        )
        ranges = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('ranges:'):
                try:
                    val = float(line.split(':')[1].strip())
                    if 0 < val < 30:
                        ranges.append(val)
                except ValueError:
                    pass

        if ranges:
            n = len(ranges)
            angles = np.linspace(-2.356195, 2.356195, n)
            world_x = np.array(ranges) * np.cos(angles)
            world_y = np.array(ranges) * np.sin(angles)
            x = -world_y
            y = world_x

            fig, ax = plt.subplots(1, 1, figsize=(10, 10))
            ax.set_aspect('equal')
            ax.scatter(x, y, s=1, c='blue', alpha=0.7, label='Lidar scan')
            ax.plot(0, 0, 'r^', markersize=15, label='Drone', zorder=5)
            room = patches.Rectangle((-10, -10), 20, 20, linewidth=2,
                                     edgecolor='gray', facecolor='none', linestyle='--', label='Room')
            ax.add_patch(room)
            ax.text(0, 10.5, 'RED wall (North)', color='red', fontsize=11, ha='center', fontweight='bold')
            ax.text(0, -11, 'BLUE wall (South)', color='blue', fontsize=11, ha='center', fontweight='bold')
            ax.text(-11.5, 0, 'GREEN\nwall', color='green', fontsize=10, va='center')
            ax.text(10.5, 0, 'YELLOW\nwall', color='#B8860B', fontsize=10, va='center')
            ax.annotate('', xy=(0, 1.2), xytext=(0, 0.3),
                        arrowprops=dict(arrowstyle='->', color='red', lw=2))
            ax.text(0.15, 0.8, 'FWD', color='red', fontsize=9, fontweight='bold')
            ax.set_xlabel('East (m)')
            ax.set_ylabel('North (m)')
            ax.set_title(f'2D Lidar — RPLidar A1M8 ({n} points, in-flight)', fontsize=14)
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)
            ax.set_xlim(-12, 12)
            ax.set_ylim(-12, 12)
            outpath = os.path.join(OUTPUT_DIR, "lidar_scan.pdf")
            fig.savefig(outpath, bbox_inches='tight', dpi=150)
            plt.close(fig)
            print(f"  Saved: {outpath}")
    except Exception as e:
        print(f"  Lidar capture error: {e}")

    # --- Optical flow ---
    try:
        px4_bin = os.path.join(os.environ.get("PX4_DIR", "px4"),
                               "build/px4_sitl_default/bin")
        result = subprocess.run(
            [f"{px4_bin}/px4-listener", "vehicle_optical_flow", "-n", "1"],
            capture_output=True, text=True, timeout=5
        )
        quality = 0
        for line in result.stdout.split('\n'):
            if 'quality:' in line:
                quality = int(line.split(':')[1].strip())

        fig, ax = plt.subplots(figsize=(8, 3))
        colors = ['#ff4444' if quality < 50 else '#ffaa00' if quality < 150 else '#44cc44']
        ax.barh(['Quality'], [quality], color=colors, height=0.5)
        ax.set_xlim(0, 255)
        ax.set_xlabel('Quality (0-255)')
        ax.set_title('Optical Flow — MTF-01 (in-flight)', fontsize=14)
        ax.text(min(quality + 5, 240), 0, f'{quality}', va='center', fontsize=14, fontweight='bold')
        outpath = os.path.join(OUTPUT_DIR, "optical_flow.pdf")
        fig.savefig(outpath, bbox_inches='tight', dpi=150)
        plt.close(fig)
        print(f"  Saved: {outpath}")
    except Exception as e:
        print(f"  Flow capture error: {e}")


async def verify_gz_sensors():
    """Check that all sensor topics exist in Gazebo."""
    env = get_gz_env()
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True, text=True, timeout=5, env=env
        )
        topics = result.stdout
    except Exception as e:
        print(f"  Could not query Gazebo topics: {e}")
        return

    sensors = {
        "Optical flow (MTF-01)":  "optical_flow/optical_flow",
        "Flow camera":            "flow_camera/image",
        "Downward rangefinder":   "lidar_sensor_link/sensor/lidar/scan",
        "2D lidar (RPLidar)":     "lidar_2d_v2",
        "Mono camera (Pi Cam)":   "camera_link/sensor/camera",
    }

    for name, pattern in sensors.items():
        found = pattern in topics
        print(f"  [{'OK' if found else 'MISSING'}] {name}")


if __name__ == "__main__":
    asyncio.run(run())
