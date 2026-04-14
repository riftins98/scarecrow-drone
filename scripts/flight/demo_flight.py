#!/usr/bin/env python3
"""
Scarecrow Drone — Hover Test (MAVSDK)

GPS-denied indoor flight using ONLY:
  - Optical flow (MTF-01) for horizontal velocity
  - Downward rangefinder (TF-Luna) for height
  - 2D lidar (RPLidar A1M8) for obstacle avoidance
  - Mono camera (Pi Camera 3) for visual awareness

Sequence: arm -> takeoff to 2.5m -> stabilize -> hover (with YOLO detection) -> stabilize -> land
Records camera video throughout flight.
Captures lidar scan + optical flow snapshot at hover.
Creates a flight record in the webapp DB — visible in the UI.

This script runs identically on simulation and real hardware.
Only the connection string changes:
  Sim:  udp://:14540
  Real: serial:///dev/ttyACM0:921600
"""

import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import asyncio
import logging
import subprocess
import sys
import threading
import time

import argparse
import cv2
import numpy as np
from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed

# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5        # meters above ground
HOVER_DURATION = 5      # seconds to hover for detection
YOLO_CONFIDENCE = 0.3

# Lidar stabilization targets — distances from spawn position (5, -4.5) in drone_garage
# Drone faces north (+x, yaw=0): rear=south wall, right=west wall
# NOTE: front wall blocked by pigeon billboard — use rear instead
LIDAR_TARGET_REAR = 17.0   # meters to south wall
LIDAR_TARGET_RIGHT = 3.0   # meters to west wall

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Webapp DB path
sys.path.insert(0, os.path.join(REPO_ROOT, "webapp", "backend"))
from database.db import create_flight, end_flight, add_detection_image

# YOLO model
YOLO_MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")

# Lidar-based stabilization (same as room_circuit.py)
from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.controllers.distance_stabilizer import (
    DistanceStabilizerController,
    DistanceTargets,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flight-id", type=str, default=None,
                        help="Flight ID from webapp (if omitted, a new one is created)")
    return parser.parse_args()


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
        try:
            result = subprocess.run(
                ["hostname", "-I"], capture_output=True, text=True, timeout=3
            )
            env["GZ_IP"] = result.stdout.strip().split()[0]
        except Exception:
            pass
    env["GZ_PARTITION"] = "px4"
    return env


def _parse_gz_frame(raw):
    """Parse raw gz topic output into a BGR numpy array.
    Uses rfind for the closing quote to avoid stopping at embedded quote bytes."""
    if len(raw) < 100:
        return None

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

    data_start = raw.find(b'data: "') + 7
    data_end = raw.rfind(b'"')
    if data_start <= 7 or data_end <= data_start:
        return None

    chunk = raw[data_start:data_end]

    try:
        frame_bytes = chunk.decode('unicode_escape').encode('latin-1')
    except UnicodeDecodeError:
        result_bytes = bytearray()
        pos = 0
        while pos < len(chunk):
            try:
                part = chunk[pos:].decode('unicode_escape').encode('latin-1')
                result_bytes.extend(part)
                break
            except UnicodeDecodeError as e:
                good = chunk[pos:pos+e.start].decode('unicode_escape').encode('latin-1')
                result_bytes.extend(good)
                result_bytes.append(chunk[pos+e.start])
                pos += e.start + 1
        frame_bytes = bytes(result_bytes)

    if len(frame_bytes) < expected:
        return None

    try:
        pixels = np.frombuffer(frame_bytes[:expected], dtype=np.uint8).reshape((height, width, 3))
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


class CameraRecorder:
    """Saves raw gz topic dumps during flight, builds video with ffmpeg after landing.
    Shares parsed frames with HoverDetector via on_frame callback."""

    def __init__(self, output_dir):
        self.running = False
        self.thread = None
        self.topic = None
        self.env = None
        self.output_dir = output_dir
        self.tmp_dir = os.path.join(output_dir, ".camera_raw")
        self.start_time = None
        self.stop_time = None
        self._frame_count = 0
        self._lock = threading.Lock()
        self.on_frame = None   # callback(frame: np.ndarray) — set before start()

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
        if not self.topic:
            print("  [camera] Topic not found")
            return

        print(f"  [camera] Recording...")
        self.start_time = time.time()

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
                        # Share parsed frame with detector callback
                        if self.on_frame is not None:
                            frame = _parse_gz_frame(result.stdout)
                            if frame is not None:
                                self.on_frame(frame)
                except Exception:
                    pass

        workers = []
        for _ in range(4):
            t = threading.Thread(target=grab_frames, daemon=True)
            t.start()
            workers.append(t)

        while self.running:
            time.sleep(0.1)

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
            return None

        png_dir = os.path.join(self.output_dir, ".camera_png")
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
            return None

        shutil.copy2(
            os.path.join(png_dir, "frame_0000.png"),
            os.path.join(self.output_dir, "camera_ground.png")
        )
        shutil.copy2(
            os.path.join(png_dir, f"frame_{good-1:04d}.png"),
            os.path.join(self.output_dir, "camera_flight.png")
        )
        print("  [camera] Saved camera_ground.png + camera_flight.png")

        duration = (self.stop_time - self.start_time) if (self.start_time and self.stop_time) else 14
        real_fps = max(1, good / max(duration, 1))
        print(f"  [camera] Real framerate: {real_fps:.1f} fps ({good} frames / {duration:.1f}s)")

        outpath = os.path.join(self.output_dir, "flight_camera.mp4")
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
                shutil.rmtree(self.tmp_dir, ignore_errors=True)
                shutil.rmtree(png_dir, ignore_errors=True)
                return outpath
            else:
                print("  [camera] ffmpeg failed to create video")
        except Exception as e:
            print(f"  [camera] ffmpeg error: {e}")

        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(png_dir, ignore_errors=True)
        return None

    def _parse_frame(self, raw):
        return _parse_gz_frame(raw)


class HoverDetector:
    """Runs YOLO pigeon detection during hover via on_frame callback from CameraRecorder."""

    def __init__(self, flight_id, output_dir):
        self.flight_id = flight_id
        self.output_dir = output_dir
        self.detection_dir = os.path.join(output_dir, "detections")
        self.running = False
        self.pigeons_detected = 0
        self.frames_processed = 0
        self._model = None
        self._detect_lock = threading.Lock()
        self._last_process_time = 0.0

    def load_model(self):
        """Pre-load YOLO before flight so there's no delay at hover."""
        print("Loading YOLO model...")
        try:
            logging.getLogger("ultralytics").setLevel(logging.WARNING)
            from ultralytics import YOLO
            self._model = YOLO(YOLO_MODEL_PATH, verbose=False)
            print("  YOLO model loaded.")
            return True
        except Exception as e:
            print(f"  YOLO load failed: {e}")
            return False

    def start(self):
        os.makedirs(self.detection_dir, exist_ok=True)
        self.running = True

    def stop(self):
        self.running = False

    def process_frame(self, frame):
        """Called by CameraRecorder workers. Rate-limited to 1 inference/second."""
        if not self.running or self._model is None:
            return

        now = time.time()
        if not self._detect_lock.acquire(blocking=False):
            return
        try:
            if now - self._last_process_time < 1.0:
                return
            self._last_process_time = now
            self.frames_processed += 1
        finally:
            self._detect_lock.release()

        results = self._model(
            frame,
            conf=YOLO_CONFIDENCE,
            iou=0.45,
            imgsz=640,
            verbose=False
        )

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                cls_name = self._model.names[int(box.cls[0])]
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                detections.append({'class': cls_name, 'conf': conf,
                                   'bbox': (x1, y1, x2, y2), 'center': (cx, cy)})

        if detections:
            self.pigeons_detected += len(detections)
            print(f"  [detection] Frame {self.frames_processed}: "
                  f"{len(detections)} pigeon(s) at {detections[0]['conf']:.0%}")

            annotated = frame.copy()
            for d in detections:
                x1, y1, x2, y2 = d['bbox']
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated, f"Pigeon: {d['conf']:.2f}",
                            (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.circle(annotated, d['center'], 5, (0, 0, 255), -1)

            img_path = os.path.join(self.detection_dir,
                                    f"detection_{self.frames_processed:04d}.png")
            cv2.imwrite(img_path, annotated)
            add_detection_image(self.flight_id, img_path)
            print(f"DETECTION_IMAGE:{img_path}", flush=True)
        else:
            print(f"  [detection] Frame {self.frames_processed}: no detections")


async def lidar_stabilize(drone, lidar, targets, label="stabilize", timeout=12.0):
    """Hold position using lidar wall distances until stable."""
    stabilizer = DistanceStabilizerController(
        targets=targets,
        kp_front_rear=0.40,
        kp_left_right=0.45,
        max_forward_speed=0.25,
        max_lateral_speed=0.25,
        tolerance=0.15,
        stable_time=1.5,
    )

    # Log initial state vs targets
    scan = lidar.get_scan()
    if scan:
        rear_now = scan.rear_distance()
        right_now = scan.right_distance()
        rear_t = targets.rear if targets.rear else 0
        right_t = targets.right if targets.right else 0
        print(f"  [{label}] Start:  rear={rear_now:.2f}m (target {rear_t}m, err={rear_now - rear_t:+.2f}m)  "
              f"right={right_now:.2f}m (target {right_t}m, err={right_now - right_t:+.2f}m)")

    start = time.time()
    step = 0
    while time.time() - start < timeout:
        scan = lidar.get_scan()
        if scan is None:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            await asyncio.sleep(0.05)
            continue

        cmd = stabilizer.update(scan)
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, 0.0, 0.0)
        )

        step += 1
        if step % 20 == 0:  # log every ~1s
            rear_now = scan.rear_distance()
            right_now = scan.right_distance()
            rear_t = targets.rear if targets.rear else 0
            right_t = targets.right if targets.right else 0
            print(f"  [{label}] {time.time() - start:.1f}s  rear={rear_now:.2f}m (err={rear_now - rear_t:+.2f})  "
                  f"right={right_now:.2f}m (err={right_now - right_t:+.2f})  "
                  f"cmd: fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f}")

        if stabilizer.done:
            rear_now = scan.rear_distance()
            right_now = scan.right_distance()
            print(f"  [{label}] LOCKED: rear={rear_now:.2f}m  right={right_now:.2f}m  ({time.time() - start:.1f}s)")
            break

        await asyncio.sleep(0.05)
    else:
        scan = lidar.get_scan()
        if scan:
            print(f"  [{label}] TIMEOUT: rear={scan.rear_distance():.2f}m  right={scan.right_distance():.2f}m")

    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
    await asyncio.sleep(0.5)


async def get_position(drone):
    async for pos in drone.telemetry.position_velocity_ned():
        return pos


async def wait_for_altitude(drone, target_alt, ground_z, timeout=30):
    """Wait until drone reaches target altitude."""
    for i in range(int(timeout / 0.5)):
        await asyncio.sleep(0.5)
        async for pos in drone.telemetry.position_velocity_ned():
            agl = -(pos.position.down_m - ground_z)
            print(f"  Climbing... {agl:.1f}m / {target_alt}m")
            if agl >= target_alt - 0.3:
                return True
            break
    return False


async def wait_for_stable(drone, ground_z, tolerance=0.15, stable_secs=2.0, timeout=15.0):
    """Wait until altitude is stable within tolerance for stable_secs consecutive seconds."""
    stable_since = None
    deadline = time.time() + timeout

    while time.time() < deadline:
        async for pos in drone.telemetry.position_velocity_ned():
            agl = -(pos.position.down_m - ground_z)
            vz = abs(pos.velocity.down_m_s)
            break

        if vz < tolerance:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= stable_secs:
                print(f"  Stable at {agl:.2f}m (vz={vz:.3f} m/s)")
                return True
        else:
            stable_since = None

        await asyncio.sleep(0.2)

    print(f"  Stability timeout — continuing")
    return False


async def log_position(drone, phase, ground_z):
    pos = await get_position(drone)
    agl = -(pos.position.down_m - ground_z)
    vz = pos.velocity.down_m_s
    n = pos.position.north_m
    e = pos.position.east_m
    print(f"  [{phase:12s}] agl={agl:6.3f}m  vz={vz:+.3f}  n={n:+.3f} e={e:+.3f}")


async def run():
    args = parse_args()

    # --- Kill leftover mavsdk_server from previous runs ---
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)

    # --- Flight record in DB ---
    if args.flight_id:
        flight_id = args.flight_id
        print(f"\nFlight ID: {flight_id} (from webapp)")
    else:
        flight_id = create_flight()
        print(f"\nFlight ID: {flight_id} (new)")
    output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output:    {output_dir}")

    # --- Launch background tasks in parallel while connecting ---
    detector = HoverDetector(flight_id, output_dir)
    gz_topics_cache = [None]
    gz_env_cache = [None]

    def prefetch_gz():
        gz_env_cache[0] = get_gz_env()
        try:
            result = subprocess.run(
                ["gz", "topic", "-l"],
                capture_output=True, text=True, timeout=5, env=gz_env_cache[0]
            )
            gz_topics_cache[0] = result.stdout
        except Exception:
            gz_topics_cache[0] = ""

    yolo_thread = threading.Thread(target=detector.load_model, daemon=True)
    gz_thread = threading.Thread(target=prefetch_gz, daemon=True)
    yolo_thread.start()
    gz_thread.start()

    # --- Connect to drone ---
    drone = System()
    print("\nConnecting to drone...")
    await drone.connect(system_address=SYSTEM_ADDRESS)

    print("Waiting for connection (timeout 30s)...")
    try:
        async with asyncio.timeout(30):
            async for state in drone.core.connection_state():
                if state.is_connected:
                    print("Connected!")
                    break
    except asyncio.TimeoutError:
        print("ERROR: Could not connect to drone. Is PX4 running?")
        end_flight(flight_id, pigeons=0, frames=0)
        return

    print("Waiting for position estimate (timeout 60s)...")
    try:
        async with asyncio.timeout(60):
            async for health in drone.telemetry.health():
                if health.is_local_position_ok:
                    print("Position estimate OK")
                    break
    except asyncio.TimeoutError:
        print("ERROR: Position estimate timed out. Check optical flow + EKF2.")
        end_flight(flight_id, pigeons=0, frames=0)
        return

    # Wait for background tasks if still running
    if yolo_thread.is_alive():
        print("Waiting for YOLO model...")
        yolo_thread.join()
    if gz_thread.is_alive():
        gz_thread.join()

    topics = gz_topics_cache[0] or ""
    gz_env = gz_env_cache[0] or get_gz_env()

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
        end_flight(flight_id, pigeons=0, frames=0)
        return

    print("\n  All params OK: optical flow + rangefinder navigation")
    print("=" * 55)

    # --- Verify Gazebo sensor topics (using cached result) ---
    print("\n--- Gazebo Sensor Topics ---")
    sensors = {
        "Optical flow (MTF-01)":  "optical_flow/optical_flow",
        "Flow camera":            "flow_camera/image",
        "Downward rangefinder":   "lidar_sensor_link/sensor/lidar/scan",
        "2D lidar (RPLidar)":     "lidar_2d_v2",
        "Mono camera (Pi Cam)":   "camera_link/sensor/camera",
    }
    for name, pattern in sensors.items():
        print(f"  [{'OK' if pattern in topics else 'MISSING'}] {name}")

    # --- Pre-flight Setup ---
    print("\n--- Pre-flight Setup ---")
    try:
        await drone.action.set_gps_global_origin(0.0, 0.0, 0.0)
        print("  EKF origin set (0, 0, 0)")
    except Exception as e:
        print(f"  set_gps_global_origin failed: {e}")

    # --- Start lidar (use cached topic) ---
    print("\nStarting lidar...")
    lidar_topic = next((l.strip() for l in topics.split('\n') if "lidar_2d_v2/scan" in l and "points" not in l), None)
    lidar = GazeboLidar(topic=lidar_topic, env=gz_env, num_threads=3)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    for _ in range(30):
        await asyncio.sleep(0.1)
        scan = lidar.get_scan()
        if scan is not None:
            print(f"  Lidar ready: {scan.num_samples} samples")
            print(f"  Rear: {scan.rear_distance():.1f}m  Right: {scan.right_distance():.1f}m  "
                  f"Front: {scan.front_distance():.1f}m  Left: {scan.left_distance():.1f}m")
            print(f"  Stabilization targets: rear={LIDAR_TARGET_REAR}m  right={LIDAR_TARGET_RIGHT}m")
            break
    else:
        print("  ERROR: No lidar data — aborting")
        lidar.stop()
        end_flight(flight_id, pigeons=0, frames=0)
        return

    # --- Read ground position ---
    ground = await get_position(drone)
    ground_z = ground.position.down_m
    print(f"\n--- Flight Sequence ---")
    print(f"  Ground reference: z={ground_z:.3f} (NED)")

    # --- Start camera (use cached topic) ---
    camera = CameraRecorder(output_dir)
    camera.topic = next((l.strip() for l in topics.split('\n') if "camera_link/sensor/camera/image" in l), None)
    camera.env = gz_env
    if camera.topic:
        print(f"  Camera topic: {camera.topic}")
    camera.on_frame = detector.process_frame
    camera.start()

    # --- Takeoff ---
    print(f"\nSetting takeoff altitude to {TARGET_ALT}m...")
    await drone.action.set_takeoff_altitude(TARGET_ALT)

    print("Arming...")
    await drone.action.arm()
    print("Armed!")

    print(f"Taking off to {TARGET_ALT}m...")
    await drone.action.takeoff()

    if not await wait_for_altitude(drone, TARGET_ALT, ground_z, timeout=30):
        print("ERROR: Failed to reach target altitude. Aborting.")
        camera.stop()
        lidar.stop()
        end_flight(flight_id, pigeons=0, frames=0)
        return

    print(f"\nReached {TARGET_ALT}m — waiting for stable hover...")
    await wait_for_stable(drone, ground_z)

    # --- Enter offboard mode ---
    targets = DistanceTargets(rear=LIDAR_TARGET_REAR, right=LIDAR_TARGET_RIGHT)

    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
    try:
        await drone.offboard.start()
        print("  Offboard mode active")
    except OffboardError as e:
        print(f"  Offboard start failed: {e} — aborting")
        camera.stop()
        lidar.stop()
        end_flight(flight_id, pigeons=0, frames=0)
        return

    # --- Phase 1: Lidar stabilize to spawn position ---
    print(f"\n--- Phase 1: Lidar Stabilization (rear={LIDAR_TARGET_REAR}m, right={LIDAR_TARGET_RIGHT}m) ---")
    await lidar_stabilize(drone, lidar, targets, label="pre-hover")

    # --- Phase 2: Hover with YOLO detection + lidar hold ---
    print(f"\nHovering at {TARGET_ALT}m for {HOVER_DURATION}s — running pigeon detection...")

    # Start lidar/flow capture in background
    sensor_thread = threading.Thread(target=capture_lidar_and_flow,
                                     args=(output_dir,), daemon=True)
    sensor_thread.start()

    # Detection runs via camera.on_frame callback
    detector.start()

    # Continuous lidar hold during hover
    stabilizer = DistanceStabilizerController(
        targets=targets,
        kp_front_rear=0.40,
        kp_left_right=0.45,
        max_forward_speed=0.25,
        max_lateral_speed=0.25,
        tolerance=0.15,
        stable_time=1.0,
    )

    hover_start = time.time()
    step = 0
    while time.time() - hover_start < HOVER_DURATION:
        scan = lidar.get_scan()
        if scan is not None:
            cmd = stabilizer.update(scan)
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, 0.0, 0.0)
            )
            if stabilizer.done:
                stabilizer.reset()
        else:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))

        await asyncio.sleep(0.05)
        step += 1
        if step % 20 == 0:
            await log_position(drone, f"HOVER  {time.time() - hover_start:.1f}s", ground_z)

    detector.stop()
    sensor_thread.join(timeout=3)

    print(f"\n  Hover complete. Pigeons detected: {detector.pigeons_detected} "
          f"(frames: {detector.frames_processed})")

    # --- Phase 3: Re-stabilize before landing ---
    print("\n--- Phase 3: Re-stabilize to landing position ---")
    await lidar_stabilize(drone, lidar, targets, label="pre-land")

    # --- Phase 4: Lidar-locked descent ---
    print("\nLanding with lidar position hold...")
    DESCENT_SPEED = 0.3   # m/s downward
    LAND_AGL = 0.35       # meters AGL — disarm below this
    LAND_TIMEOUT = 30     # seconds

    stabilizer.reset()
    land_start = time.time()
    step = 0

    while time.time() - land_start < LAND_TIMEOUT:
        scan = lidar.get_scan()
        if scan is not None:
            cmd = stabilizer.update(scan)
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, DESCENT_SPEED, 0.0)
            )
            if stabilizer.done:
                stabilizer.reset()
        else:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0.0, 0.0, DESCENT_SPEED, 0.0)
            )

        await asyncio.sleep(0.05)
        step += 1

        if step % 10 == 0:
            pos = await get_position(drone)
            agl = -(pos.position.down_m - ground_z)
            scan_now = lidar.get_scan()
            if scan_now:
                print(f"  [descent] agl={agl:.2f}m  rear={scan_now.rear_distance():.2f}m  "
                      f"right={scan_now.right_distance():.2f}m  "
                      f"cmd: fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f}")
            else:
                print(f"  [descent] agl={agl:.2f}m  (no lidar)")
            if agl < LAND_AGL:
                print(f"  [descent] Near ground ({agl:.2f}m) — touching down")
                break

    # Stop offboard and disarm
    try:
        await drone.offboard.stop()
    except OffboardError:
        pass

    print("  Disarming...")
    try:
        await drone.action.disarm()
        print("  Disarmed!")
    except Exception:
        try:
            await drone.action.kill()
            print("  Killed motors")
        except Exception:
            pass

    lidar.stop()

    # --- Stop camera + build video ---
    camera.stop()
    print("\nBuilding video...")
    video_path = camera.save_video()

    # --- Finalize flight record ---
    end_flight(
        flight_id,
        pigeons=detector.pigeons_detected,
        frames=detector.frames_processed,
        video_path=video_path,
    )
    print(f"\nFlight record saved (ID: {flight_id})")

    print("\n" + "=" * 55)
    print("  FLIGHT COMPLETE")
    print("  Navigation: optical flow + rangefinder (NO GPS)")
    print(f"  Pigeons detected: {detector.pigeons_detected}")
    print(f"  Frames processed: {detector.frames_processed}")
    print(f"  Flight ID: {flight_id} (visible in UI history)")
    print(f"  Outputs in: {output_dir}/")
    print("=" * 55)


def capture_lidar_and_flow(output_dir):
    """Capture lidar scan and optical flow data."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    env = get_gz_env()
    os.makedirs(output_dir, exist_ok=True)

    # --- Lidar scan ---
    try:
        result_topics = subprocess.run(
            ["gz", "topic", "-l"], capture_output=True, text=True, timeout=5, env=env
        )
        lidar_topic = next(
            (l.strip() for l in result_topics.stdout.split('\n') if "lidar_2d_v2/scan" in l and "points" not in l),
            None
        )
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
            outpath = os.path.join(output_dir, "lidar_scan.pdf")
            fig.savefig(outpath, bbox_inches='tight', dpi=150)
            plt.close(fig)
            print(f"  Saved: {outpath}")
    except Exception as e:
        print(f"  Lidar capture error: {e}")

    # --- Optical flow ---
    try:
        px4_bin = os.path.join(REPO_ROOT, "px4", "build/px4_sitl_default/bin")
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
        outpath = os.path.join(output_dir, "optical_flow.pdf")
        fig.savefig(outpath, bbox_inches='tight', dpi=150)
        plt.close(fig)
        print(f"  Saved: {outpath}")
    except Exception as e:
        print(f"  Flow capture error: {e}")


if __name__ == "__main__":
    asyncio.run(run())
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    os._exit(0)
