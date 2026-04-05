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

import cv2
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")

# Default model path — search common locations
def _find_default_model():
    candidates = [
        os.path.join(REPO_ROOT, "best_v4.pt"),  # project root
        os.path.join(REPO_ROOT, "models", "best_v4.pt"),
        os.path.join(os.path.dirname(REPO_ROOT), "scarecrow_drone", "live_detection", "best_v4.pt"),
        os.path.join(os.path.expanduser("~"), "scarecrow-drone", "best_v4.pt"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return os.path.join(REPO_ROOT, "best_v4.pt")  # fallback

DEFAULT_MODEL = _find_default_model()

# Pigeon overlay images for sim testing
PIGEON_IMAGES_DIR = os.path.join(REPO_ROOT, "models", "pigeon_billboard", "materials", "textures")


# ---------- Gazebo helpers (from demo_flight.py) ----------

def get_gz_env():
    env = os.environ.copy()
    env["GZ_PARTITION"] = "px4"
    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=3
        )
        ip = result.stdout.strip().split()[0]
        if ip:
            env["GZ_IP"] = ip
    except Exception:
        pass
    return env


def find_camera_topic(env):
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"], capture_output=True, text=True, timeout=5, env=env
        )
        for line in result.stdout.split('\n'):
            if "camera_link/sensor/camera/image" in line:
                return line.strip()
    except Exception:
        pass
    return None


def capture_frame(topic, env):
    """Capture one camera frame from Gazebo and return as BGR numpy array."""
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", topic],
            capture_output=True, timeout=30, env=env
        )
        raw = result.stdout
    except Exception:
        return None

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
    args = parser.parse_args()

    # Check model exists
    if not os.path.exists(args.model):
        print(f"ERROR: Model not found: {args.model}")
        print("  Provide --model /path/to/best_v4.pt")
        sys.exit(1)

    # Import YOLO
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
