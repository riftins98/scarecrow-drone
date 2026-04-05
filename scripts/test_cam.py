#!/usr/bin/env python3
"""Test camera capture from Gazebo — debug script."""
import subprocess, os, re, struct
import numpy as np
import cv2

env = os.environ.copy()
env["GZ_PARTITION"] = "px4"
try:
    result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3)
    env["GZ_IP"] = result.stdout.strip().split()[0]
except:
    pass

topic = "/world/indoor_room/model/holybro_x500_0/link/camera_link/sensor/camera/image"
print("Capturing frame...")
result = subprocess.run(
    ["gz", "topic", "-e", "-n", "1", "-t", topic],
    capture_output=True, timeout=30, env=env
)
raw = result.stdout
print(f"Raw bytes: {len(raw)}")

# Parse width/height from text portion
text = raw.decode("latin-1", errors="replace")
width = height = 0
for line in text.split("\n"):
    line = line.strip()
    if line.startswith("width:"):
        try: width = int(line.split(":")[1].strip())
        except: pass
    elif line.startswith("height:"):
        try: height = int(line.split(":")[1].strip())
        except: pass
print(f"Size: {width}x{height}")

expected = width * height * 3
print(f"Expected pixel bytes: {expected}")

# Find data field and extract bytes
data_start = raw.find(b'data: "') + 7
data_end = raw.rfind(b'"')
if data_start <= 7 or data_end <= data_start:
    print("Could not find data field")
    exit(1)

chunk = raw[data_start:data_end]
print(f"Data chunk: {len(chunk)} bytes")

# Try decode with error handling - process in smaller chunks
try:
    frame_bytes = chunk.decode("unicode_escape").encode("latin-1")
    print(f"Decoded: {len(frame_bytes)} bytes")
except UnicodeDecodeError as e:
    print(f"unicode_escape failed at position {e.start}: {e.reason}")
    # Decode up to the error point, skip bad byte, continue
    result_bytes = bytearray()
    pos = 0
    while pos < len(chunk):
        try:
            part = chunk[pos:].decode("unicode_escape").encode("latin-1")
            result_bytes.extend(part)
            break
        except UnicodeDecodeError as e2:
            # Decode the good part
            good = chunk[pos:pos+e2.start].decode("unicode_escape").encode("latin-1")
            result_bytes.extend(good)
            result_bytes.append(chunk[pos+e2.start])
            pos += e2.start + 1
    frame_bytes = bytes(result_bytes)
    print(f"Decoded with recovery: {len(frame_bytes)} bytes")

if len(frame_bytes) >= expected:
    pixels = np.frombuffer(frame_bytes[:expected], dtype=np.uint8).reshape((height, width, 3))
    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    os.makedirs("output", exist_ok=True)
    cv2.imwrite("output/test_capture.png", bgr)
    print(f"SUCCESS! Saved output/test_capture.png ({bgr.shape})")
else:
    print(f"Not enough bytes: {len(frame_bytes)} < {expected}")
