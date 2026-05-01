#!/usr/bin/env python3
"""Stream Gazebo camera to browser via WebRTC (H.264-capable path).

Usage:
  python3 scripts/stream_camera_webrtc.py --port 8080 --open --topic <gazebo_topic>
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time
import webbrowser

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scarecrow.sensors.camera.gazebo import GazeboCamera

PCS: set[RTCPeerConnection] = set()


class SharedFrameBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame = None
        self._updated_at = 0.0

    def update(self, frame) -> None:
        with self._lock:
            self._frame = frame
            self._updated_at = time.time()

    def get(self):
        with self._lock:
            return self._frame, self._updated_at


class GazeboVideoTrack(VideoStreamTrack):
    def __init__(self, buffer: SharedFrameBuffer, fps: float):
        super().__init__()
        self.buffer = buffer
        self.frame_period_s = 1.0 / max(1.0, fps)
        self._last_frame = None

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame, _ = self.buffer.get()
        if frame is None:
            if self._last_frame is None:
                await asyncio.sleep(self.frame_period_s)
                black = VideoFrame.from_ndarray(
                    np.zeros((540, 960, 3), dtype="uint8"),
                    format="bgr24",
                )
                black.pts = pts
                black.time_base = time_base
                return black
            frame = self._last_frame
        else:
            self._last_frame = frame

        video = VideoFrame.from_ndarray(frame, format="bgr24")
        video.pts = pts
        video.time_base = time_base
        return video


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Fixed Camera WebRTC</title>
  <style>
    html, body { margin: 0; padding: 0; width: 100%; height: 100%; background: #000; overflow: hidden; }
    video { width: 100vw; height: 100vh; display: block; object-fit: contain; background: #000; }
  </style>
</head>
<body>
  <video id="video" autoplay playsinline muted></video>
  <script>
    async function start() {
      const pc = new RTCPeerConnection();
      pc.addTransceiver("video", { direction: "recvonly" });
      pc.ontrack = (event) => {
        const el = document.getElementById("video");
        el.srcObject = event.streams[0];
      };
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const res = await fetch("/offer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
      });
      const answer = await res.json();
      await pc.setRemoteDescription(answer);
    }
    start().catch((e) => console.error(e));
  </script>
</body>
</html>
"""


async def index(_request):
    return web.Response(text=HTML, content_type="text/html")


async def offer(request):
    app = request.app
    params = await request.json()
    offer_desc = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    PCS.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            await pc.close()
            PCS.discard(pc)

    await pc.setRemoteDescription(offer_desc)
    track = GazeboVideoTrack(app["frame_buffer"], app["fps"])
    pc.addTrack(track)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )


async def on_shutdown(app):
    coros = [pc.close() for pc in PCS]
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)
    PCS.clear()
    app["camera"].stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--open", dest="open", action="store_true")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--topic", type=str, default=None)
    args = parser.parse_args()

    frame_buffer = SharedFrameBuffer()
    camera = GazeboCamera(topic=args.topic, env=None, num_threads=args.threads)
    camera.on_frame = frame_buffer.update
    camera.start()

    app = web.Application()
    app["frame_buffer"] = frame_buffer
    app["camera"] = camera
    app["fps"] = max(1.0, min(float(args.fps), 30.0))
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)

    if args.open:
        try:
            webbrowser.open(f"http://localhost:{args.port}/")
        except Exception:
            pass

    web.run_app(app, host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
