#!/usr/bin/env python3
"""Stream Gazebo camera as an MJPEG HTTP stream.

This script discovers the Gazebo camera topic via `GazeboCamera`, starts
polling frames, encodes them as JPEG and serves a simple MJPEG stream at
`http://localhost:<port>/stream` (and an HTML viewer at `/`).

Usage:
  # start simulator headless (example):
  HEADLESS=1 make px4_sitl gz_x500

  # then run this script
  python3 scripts/stream_camera.py --port 8080 --open

Notes:
- No GUI is required for the simulator; this only opens a browser to view
  the MJPEG served by this script.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import threading
import time
import webbrowser

from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver

import cv2
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scarecrow.sensors.camera.gazebo import GazeboCamera
from scarecrow.logging_setup import get_logger, log_event

_log = get_logger("stream.mjpeg", prefix="stream")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = (
                '<!doctype html>'
                '<html><head><meta charset="utf-8"><title>Camera Stream</title>'
                '<style>'
                'html,body{margin:0;padding:0;width:100%;height:100%;background:#000;overflow:hidden;}'
                '.frame{width:100vw;height:100vh;display:block;object-fit:contain;background:#000;}'
                '</style></head>'
                '<body><img class="frame" src="/stream" alt="camera stream"/></body></html>'
            )
            self.wfile.write(html.encode('utf-8'))
            return

        if self.path != "/stream":
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header('Age', '0')
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()

        boundary = b"--frame\r\n"

        try:
            while True:
                # Read the latest JPEG frame from the server object
                with self.server.frame_lock:
                    frame_jpeg = self.server.latest_frame_jpeg

                if frame_jpeg is None:
                    time.sleep(0.05)
                    continue

                # Write multipart headers + image
                header = (
                    b"Content-Type: image/jpeg\r\n"
                    + b"Content-Length: "
                    + str(len(frame_jpeg)).encode('ascii')
                    + b"\r\n\r\n"
                )
                try:
                    self.wfile.write(boundary)
                    self.wfile.write(header)
                    self.wfile.write(frame_jpeg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                except BrokenPipeError:
                    break

                # Throttle output to the configured stream FPS.
                time.sleep(self.server.stream_interval_s)
        except Exception:
            pass


def _compose_grid(frames: list[np.ndarray | None], names: list[str]) -> np.ndarray | None:
    base = next((frame for frame in frames if frame is not None), None)
    if base is None:
        return None

    height, width = base.shape[:2]
    normalized = []
    for idx, frame in enumerate(frames):
        if frame is None:
            canvas = np.zeros((height, width, 3), dtype=np.uint8)
        else:
            if frame.shape[:2] != (height, width):
                canvas = cv2.resize(frame, (width, height))
            else:
                canvas = frame.copy()

        label = names[idx] if idx < len(names) else "camera"
        cv2.putText(
            canvas,
            label,
            (width - 15 - (len(label) * 12), 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            label,
            (width - 15 - (len(label) * 12), 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        normalized.append(canvas)

    count = len(normalized)
    if count == 1:
        return normalized[0]

    cols = 2 if count <= 4 else 3
    rows = int(math.ceil(count / cols))
    total = rows * cols
    if total > count:
        normalized.extend([np.zeros((height, width, 3), dtype=np.uint8)] * (total - count))

    rows_imgs = []
    for row_idx in range(rows):
        row = normalized[row_idx * cols:(row_idx + 1) * cols]
        rows_imgs.append(cv2.hconcat(row))

    return cv2.vconcat(rows_imgs)


def run_server(cameras: list[GazeboCamera], host: str, port: int, open_browser: bool, fps: float, quality: int, names: list[str]):
    server = ThreadedHTTPServer((host, port), MJPEGHandler)

    # Shared state:
    # - latest_raw_frame: newest frame from Gazebo callback
    # - latest_frame_jpeg: latest encoded JPEG consumed by HTTP clients
    server.latest_raw_frames = [None] * len(cameras)
    server.latest_frame_jpeg = None
    server.frame_lock = threading.Lock()
    server.stream_interval_s = 1.0 / fps
    server.jpeg_quality = quality
    server.stop_event = threading.Event()

    # Camera callback: keep it lightweight; no encoding here.
    def make_on_frame(index):
        def on_frame(frame):
            try:
                with server.frame_lock:
                    server.latest_raw_frames[index] = frame
            except Exception:
                pass
        return on_frame

    # Encoder thread: encode at paced output FPS, reusing latest raw frame.
    def encoder_loop():
        while not server.stop_event.is_set():
            with server.frame_lock:
                frames = list(server.latest_raw_frames)
            frame = _compose_grid(frames, names)
            if frame is None:
                time.sleep(0.01)
                continue
            try:
                ret, jpg = cv2.imencode(
                    '.jpg',
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), int(server.jpeg_quality)]
                )
                if ret:
                    with server.frame_lock:
                        server.latest_frame_jpeg = jpg.tobytes()
            except Exception:
                pass
            time.sleep(server.stream_interval_s)

    for idx, camera in enumerate(cameras):
        camera.on_frame = make_on_frame(idx)

    print("Starting GazeboCamera (discovering topic if needed)...")
    for camera in cameras:
        camera.start()

    encoder_thread = threading.Thread(target=encoder_loop, daemon=True)
    encoder_thread.start()

    log_event(_log, "server_listen", host=host, port=port, fps=fps, quality=quality)
    print(f"Starting MJPEG server at http://{host}:{port}/")
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    if open_browser:
        try:
            webbrowser.open(f"http://{host}:{port}/")
        except Exception:
            pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        server.stop_event.set()
        server.shutdown()
        encoder_thread.join(timeout=2)
        for camera in cameras:
            camera.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0', help='Bind host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080, help='HTTP port (default: 8080)')
    parser.add_argument('--open', dest='open', action='store_true', help='Open browser automatically')
    parser.add_argument('--threads', type=int, default=2, help='Number of camera poll threads (default: 2)')
    parser.add_argument('--quality', type=int, default=68, help='JPEG quality 1-100 (default: 68)')
    parser.add_argument('--fps', type=float, default=12.0, help='Stream FPS limit (default: 12)')
    parser.add_argument('--topic', type=str, default=None,
                        help='Gazebo camera image topic (optional; auto-discover if omitted)')
    parser.add_argument('--topics', type=str, default=None,
                        help='Comma-separated camera topics for split-screen')
    parser.add_argument('--names', type=str, default=None,
                        help='Comma-separated camera names for split-screen labels')
    args = parser.parse_args()

    cameras = []
    if args.topics:
        topic_list = [t.strip() for t in args.topics.split(',') if t.strip()]
        cameras = [GazeboCamera(topic=topic, env=None, num_threads=args.threads) for topic in topic_list]
    else:
        cameras = [GazeboCamera(topic=args.topic, env=None, num_threads=args.threads)]
    if args.names:
        names = [n.strip() for n in args.names.split(',') if n.strip()]
    else:
        names = [f"camera_{i + 1}" for i in range(len(cameras))]
    fps = max(1.0, min(float(args.fps), 60.0))
    quality = max(40, min(int(args.quality), 95))
    run_server(cameras, args.host, args.port, args.open, fps, quality, names)


if __name__ == '__main__':
    main()
