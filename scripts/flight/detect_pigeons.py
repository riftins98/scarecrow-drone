#!/usr/bin/env python3
"""
Scarecrow Drone — Pigeon Detection from Gazebo Camera

Connects the simulated mono camera (Pi Camera 3) to the YOLOv8
pigeon detector from the scarecrow_drone project. Runs real-time
inference on the Gazebo camera feed and saves annotated frames.

Usage:
    python3 scripts/flight/detect_pigeons.py
    python3 scripts/flight/detect_pigeons.py --model /path/to/best_v4.pt
    python3 scripts/flight/detect_pigeons.py --show  # display live window
"""

import os
import re
import subprocess
import sys
import time
import argparse
import functools

import cv2
import numpy as np

# Ensure all prints are flushed immediately (for subprocess monitoring)
print = functools.partial(print, flush=True)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")

# Default model path — bundled in repo
DEFAULT_MODEL = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")

# Pigeon overlay images for sim testing
PIGEON_IMAGES_DIR = os.path.join(REPO_ROOT, "models", "pigeon_billboard", "materials", "textures")


# ---------- Gazebo helpers (from demo_flight.py) ----------

def get_gz_env():
    env = os.environ.copy()

    # Try without GZ_IP first (works in non-standalone/GUI mode — macOS + Linux)
    print("[env] Trying gz topic -l without GZ_IP...")
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True, text=True, timeout=3, env=env,
        )
        topic_count = len([l for l in result.stdout.split('\n') if l.strip()])
        print(f"[env] Got {topic_count} topics (no GZ_IP)")
        if "holybro_x500" in result.stdout:
            print("[env] holybro_x500 found — using env without GZ_IP")
            return env
        else:
            print("[env] holybro_x500 NOT found in topic list")
            if result.stderr:
                print(f"[env] stderr: {result.stderr.strip()}")
    except Exception as e:
        print(f"[env] gz topic -l failed: {e}")

    # Try with GZ_IP (needed in standalone mode with GZ_PARTITION)
    print("[env] Falling back to GZ_IP + GZ_PARTITION=px4...")
    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            capture_output=True, text=True, timeout=3,
        )
        ip = result.stdout.strip()
        print(f"[env] ipconfig en0 -> {ip!r}")
        env["GZ_IP"] = ip
    except Exception as e:
        print(f"[env] ipconfig failed: {e}, trying hostname -I...")
        try:
            result = subprocess.run(
                ["hostname", "-I"],
                capture_output=True, text=True, timeout=3,
            )
            ip = result.stdout.strip().split()[0]
            print(f"[env] hostname -I -> {ip!r}")
            env["GZ_IP"] = ip
        except Exception as e2:
            print(f"[env] hostname -I also failed: {e2}")
    env["GZ_PARTITION"] = "px4"
    print(f"[env] GZ_IP={env.get('GZ_IP', '(not set)')}  GZ_PARTITION=px4")
    return env


def find_camera_topic(env):
    print("[topic] Listing gz topics...")
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"], capture_output=True, text=True, timeout=5, env=env
        )
        topics = [l.strip() for l in result.stdout.split('\n') if l.strip()]
        print(f"[topic] {len(topics)} topics found")
        for line in topics:
            if "camera_link/sensor/camera/image" in line and "/model/holybro_x500" in line:
                print(f"[topic] Drone camera topic found: {line}")
                return line
        print("[topic] No drone camera topic matched '/model/holybro_x500.../camera/image'")
        if result.stderr:
            print(f"[topic] stderr: {result.stderr.strip()}")
    except Exception as e:
        print(f"[topic] gz topic -l failed: {e}")
    return None


def capture_frame(topic, env):
    """Capture one camera frame from Gazebo and return as BGR numpy array."""
    t0 = time.time()
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", topic],
            capture_output=True, timeout=30, env=env
        )
        raw = result.stdout
        elapsed = time.time() - t0
        print(f"[capture] gz topic returned {len(raw)} bytes in {elapsed:.1f}s")
    except Exception as e:
        print(f"[capture] gz topic capture failed: {e}")
        return None

    if len(raw) < 100:
        print(f"[capture] Response too small ({len(raw)} bytes), skipping")
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

    # Extract data between quotes
    data_start = raw.find(b'data: "') + 7
    data_end = raw.rfind(b'"')
    if data_start <= 7 or data_end <= data_start:
        return None

    chunk = raw[data_start:data_end]

    try:
        frame_bytes = chunk.decode('unicode_escape').encode('latin-1')
    except UnicodeDecodeError:
        # Recover from truncated escape sequences
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


# ---------- Pigeon overlay for sim testing ----------

def load_pigeon_overlays(pigeon_dir):
    """Load pigeon images for compositing onto sim camera frames."""
    overlays = []
    if not os.path.isdir(pigeon_dir):
        return overlays
    for fname in os.listdir(pigeon_dir):
        if fname.lower().endswith(('.jpg', '.png')):
            img = cv2.imread(os.path.join(pigeon_dir, fname))
            if img is not None:
                overlays.append(img)
    return overlays


def overlay_pigeon(frame, pigeon_img, x, y, scale=0.3):
    """Paste a pigeon image onto the frame at (x, y) with given scale."""
    h, w = frame.shape[:2]
    ph, pw = pigeon_img.shape[:2]

    # Scale pigeon to a reasonable size relative to frame
    new_w = int(w * scale)
    new_h = int(ph * (new_w / pw))
    pigeon_resized = cv2.resize(pigeon_img, (new_w, new_h))

    # Clamp position to keep pigeon within frame
    x1 = max(0, min(x, w - new_w))
    y1 = max(0, min(y, h - new_h))
    x2 = x1 + new_w
    y2 = y1 + new_h

    # Simple paste (no alpha blending — pigeon images are opaque)
    frame[y1:y2, x1:x2] = pigeon_resized
    return frame


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description="Pigeon detection from Gazebo camera")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help="Path to YOLO model weights")
    parser.add_argument("--confidence", type=float, default=0.5,
                        help="Detection confidence threshold")
    parser.add_argument("--duration", type=int, default=60,
                        help="Detection duration in seconds (0 = unlimited)")
    parser.add_argument("--show", action="store_true",
                        help="Show live detection window (requires display)")
    parser.add_argument("--overlay", action="store_true",
                        help="Overlay real pigeon images onto camera frames for sim testing")
    parser.add_argument("--flight-id", type=str, default=None,
                        help="Flight ID (used by webapp backend)")
    args = parser.parse_args()

    # Override output dir if set by backend
    if os.environ.get("DETECTION_OUTPUT_DIR"):
        global OUTPUT_DIR
        OUTPUT_DIR = os.environ["DETECTION_OUTPUT_DIR"]

    # Check model exists
    if not os.path.exists(args.model):
        print(f"ERROR: Model not found: {args.model}")
        print("  Provide --model /path/to/best_v4.pt")
        sys.exit(1)

    # Import YOLO (torch takes ~30s to load on first run — please wait)
    print("Loading YOLO/torch (this can take 30-60s on first run)...")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ERROR: ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)

    # Connect to Gazebo camera
    print("Connecting to Gazebo camera...")
    env = get_gz_env()
    topic = find_camera_topic(env)
    if not topic:
        print("ERROR: Camera topic not found. Is Gazebo running?")
        sys.exit(1)
    print(f"  Camera topic: {topic}")

    # Test capture
    print("  Capturing test frame...")
    frame = capture_frame(topic, env)
    if frame is None:
        print("ERROR: Could not capture camera frame")
        sys.exit(1)
    print(f"  Frame: {frame.shape[1]}x{frame.shape[0]}")

    # Load YOLO model
    print(f"\nLoading YOLO model: {os.path.basename(args.model)}")
    model = YOLO(args.model)
    print("Model loaded!")

    # Load pigeon overlays for sim testing
    pigeon_overlays = []
    if args.overlay:
        pigeon_overlays = load_pigeon_overlays(PIGEON_IMAGES_DIR)
        print(f"  Loaded {len(pigeon_overlays)} pigeon overlay images for sim testing")

    # Output setup
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    detection_dir = os.path.join(OUTPUT_DIR, "detections")
    os.makedirs(detection_dir, exist_ok=True)

    # Detection loop
    print(f"\n{'='*55}")
    print(f"  PIGEON DETECTION — Gazebo Camera Feed")
    print(f"  Model: {os.path.basename(args.model)}")
    print(f"  Confidence: {args.confidence}")
    print(f"  Duration: {'unlimited' if args.duration == 0 else f'{args.duration}s'}")
    print(f"{'='*55}\n")

    start_time = time.time()
    frame_count = 0
    detection_count = 0
    total_pigeons = 0

    try:
        while True:
            elapsed = time.time() - start_time
            if args.duration > 0 and elapsed > args.duration:
                break

            # Capture frame
            frame = capture_frame(topic, env)
            if frame is None:
                print(f"  [{elapsed:6.1f}s] Frame capture failed, retrying...")
                time.sleep(0.5)
                continue

            frame_count += 1

            # Run YOLO inference
            results = model(
                frame,
                conf=args.confidence,
                iou=0.45,
                imgsz=640,
                verbose=False
            )

            # Process detections
            detections = []
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = model.names[cls_id]
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    detections.append({
                        'class': cls_name, 'conf': conf,
                        'bbox': (x1, y1, x2, y2), 'center': (cx, cy)
                    })

            # Log
            n = len(detections)
            if n > 0:
                detection_count += 1
                total_pigeons += n
                print(f"  [{elapsed:6.1f}s] Frame {frame_count}: {n} pigeon(s) detected!")
                for d in detections:
                    print(f"           {d['class']} ({d['conf']:.2f}) at {d['center']}")

                # Save annotated frame
                annotated = frame.copy()
                for d in detections:
                    x1, y1, x2, y2 = d['bbox']
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"Pigeon: {d['conf']:.2f}"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.circle(annotated, d['center'], 5, (0, 0, 255), -1)

                outpath = os.path.join(detection_dir, f"detection_{frame_count:04d}.png")
                cv2.imwrite(outpath, annotated)
                print(f"DETECTION_IMAGE:{outpath}", flush=True)
            else:
                if frame_count % 5 == 0:
                    print(f"  [{elapsed:6.1f}s] Frame {frame_count}: no detections")
                # Save every frame for debugging
                outpath = os.path.join(detection_dir, f"frame_{frame_count:04d}.png")
                cv2.imwrite(outpath, frame)

            # Show live window if requested
            if args.show:
                display = results[0].plot() if detections else frame
                cv2.imshow("Pigeon Detection", display)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print("\n\nStopped by user.")

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*55}")
    print(f"  DETECTION COMPLETE")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Frames processed: {frame_count}")
    print(f"  Frames with detections: {detection_count}")
    print(f"  Total pigeons detected: {total_pigeons}")
    if frame_count > 0:
        print(f"  FPS: {frame_count/elapsed:.2f}")
    print(f"  Detections saved to: {detection_dir}/")
    print(f"{'='*55}")

    if args.show:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
