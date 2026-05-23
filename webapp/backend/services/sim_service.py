"""Manages Gazebo simulation lifecycle."""
import re
import subprocess
import os
import time
import threading
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DEFAULT_WORLD = "drone_garage_pigeon_3d"

LAUNCH_STEPS = [
    ("cleanup", "Cleaning up old sessions"),
    ("airframe", "Copying airframe and config"),
    ("build", "Building PX4"),
    ("gazebo_start", "Starting Gazebo"),
    ("gazebo_world", "Loading world"),
    ("spawn", "Spawning drone model"),
    ("sensors", "Initializing sensors"),
    ("startup", "PX4 startup complete"),
    ("ekf_origin", "Setting EKF origin"),
    ("heading", "Setting heading"),
    ("ready", "Ready for detection"),
]


_STREAM_URL_RE = re.compile(r"https?://[^\s'\"]+:\d+/?")
# Matches the line `real_time_factor: 0.0086609...` from `gz topic -e -t /stats`
_RTF_RE = re.compile(r"^real_time_factor:\s*([\d.]+)")

# Substatus extractors: each maps to a step_id; the function takes a line
# and returns either a short status string ("Compiling [847/1157] foo.cpp")
# or None if this line doesn't update that step's substatus.
_NINJA_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(.+)$")
_CMAKE_FOUND_RE = re.compile(r"^--\s+(?:Found|Looking for|Searching for|Checking for|Could NOT find)\s+(.+)$")


def _build_substatus(line: str) -> Optional[str]:
    """Substatus for the 'build' step (cmake configure + ninja compile)."""
    m = _NINJA_RE.match(line)
    if m:
        done, total, target = m.group(1), m.group(2), m.group(3)
        # target lines can be long; keep only the action verb + tail of path
        target = target.strip()
        if len(target) > 60:
            target = "..." + target[-57:]
        return f"Compiling [{done}/{total}] {target}"
    m = _CMAKE_FOUND_RE.match(line)
    if m:
        return f"Configuring CMake: {m.group(1).strip()[:60]}"
    if "cmake" in line.lower() and "configuring" in line.lower():
        return "Running cmake configure..."
    return None


class SimService:
    def __init__(self):
        self.process = None
        self.connected = False
        self.launching = False
        self._log_lines = []
        # Monotonic offset of the first line still in _log_lines after
        # ring-buffer rolls. Frontend SystemLog uses (cursor, offset) to
        # detect dropped lines.
        self._log_offset = 0
        self._log_lock = threading.Lock()
        # Bumped from the old 200/500 trim values so a full PX4 build's
        # output fits without rolling.
        self._log_max = 4000
        self._completed_steps = []
        self._current_step = None
        # Free-form substatus for the active step (e.g., "Compiling [847/1157]")
        # so the UI can show real-time progress instead of just a spinner.
        self._step_substatus: dict[str, str] = {}
        self._world: str = DEFAULT_WORLD
        self._headless: bool = False
        self._camera: Optional[str] = None
        self._stream_url: Optional[str] = None
        # Most-recent Gazebo /stats real_time_factor (0..1+), or None until
        # the poller has read at least one frame.
        self._rtf: Optional[float] = None
        # Subprocess running `gz topic -e -t /stats` for the lifetime of
        # the current sim. Killed on stop().
        self._stats_proc: Optional[subprocess.Popen] = None

    # Camera names we'll pass through to launch_with_stream.sh as ``--<name>``
    # flags. Anything not in this allowlist is silently rejected to keep
    # untrusted input from sneaking flags into the launcher CLI.
    _ALLOWED_CAMERAS = {"fixed", "center"}
    _DEFAULT_CAMERA = "fixed"

    def launch(self, world: str = DEFAULT_WORLD, headless: bool = False,
               camera: Optional[str] = None) -> bool:
        """Launch PX4 + Gazebo in background.

        Args:
            world: Name of a world in worlds/ (without .sdf extension).
            headless: If True, run Gazebo headless and start a browser
                stream server. The stream URL is published via
                ``stream_url`` once it appears in the launcher output.
            camera: Which streamable camera to point the headless stream
                worker at (e.g. "fixed", "center"). Ignored when not
                headless. Defaults to "fixed" if omitted or invalid.
        """
        if self.connected and self.process and self.process.poll() is None:
            return True
        if self.launching:
            return False

        self.stop()
        time.sleep(1)

        # Pick the launcher: headless uses launch_with_stream.sh (gives us a
        # browser-watchable camera feed); GUI uses launch.sh (Gazebo window).
        # launch_with_stream.sh requires at least one camera flag (--fixed or
        # --center) — without it the stream worker errors out and port 8080
        # stays empty, leaving the UI's stream link broken.
        if headless:
            launch_script = os.path.join(REPO_ROOT, "scripts", "shell", "launch_with_stream.sh")
            cam = camera if camera in self._ALLOWED_CAMERAS else self._DEFAULT_CAMERA
            launch_args = [world, "--headless", f"--{cam}"]
            self._camera = cam
        else:
            launch_script = os.path.join(REPO_ROOT, "scripts", "shell", "launch.sh")
            launch_args = [world]
            self._camera = None

        if not os.path.exists(launch_script):
            raise FileNotFoundError(f"launch script not found at {launch_script}")

        env = os.environ.copy()
        env.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
        env.setdefault("__NV_PRIME_RENDER_OFFLOAD", "1")
        # Spawn drone 5m in front of pigeon billboard, facing north wall (+x, heading=0)
        env["PX4_GZ_MODEL_POSE"] = "5,-4.5,0,0,0,0"

        self.process = subprocess.Popen(
            ["bash", launch_script, *launch_args],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
        )

        with self._log_lock:
            self._log_lines = []
            self._log_offset = 0
        self._completed_steps = []
        self._current_step = "cleanup"
        self._step_substatus = {}
        self.launching = True
        self._world = world
        self._headless = headless
        self._stream_url = None

        t = threading.Thread(target=self._wait_for_ready, daemon=True)
        t.start()
        return True

    def _mark_step(self, step_id):
        # Idempotent: re-marking the active step doesn't advance past it.
        if step_id == self._current_step or step_id in self._completed_steps:
            return
        # When we jump to step_id, mark every earlier step in LAUNCH_STEPS as
        # done (the launcher's output order isn't always linear, so skipping
        # past an intermediate step means it happened off-camera).
        step_ids = [sid for sid, _ in LAUNCH_STEPS]
        try:
            target_idx = step_ids.index(step_id)
        except ValueError:
            target_idx = len(step_ids)
        for sid in step_ids[:target_idx]:
            if sid not in self._completed_steps:
                self._completed_steps.append(sid)
        self._current_step = step_id

    def _wait_for_ready(self):
        """Wait for PX4 to be ready, reading output and tracking stages."""
        try:
            for line in self.process.stdout:
                line = line.strip()
                with self._log_lock:
                    self._log_lines.append(line)
                    overflow = len(self._log_lines) - self._log_max
                    if overflow > 0:
                        # Drop oldest `overflow` lines, advance the offset
                        # so absolute indices remain stable.
                        self._log_lines = self._log_lines[overflow:]
                        self._log_offset += overflow

                # Capture stream URL from headless launcher banner
                # (e.g., "Stream: http://localhost:8080/")
                if self._headless and self._stream_url is None and "Stream:" in line:
                    m = _STREAM_URL_RE.search(line)
                    if m:
                        self._stream_url = m.group(0).rstrip("/")

                # Substatus updates (live progress within the active step)
                if self._current_step == "build":
                    sub = _build_substatus(line)
                    if sub:
                        self._step_substatus["build"] = sub
                elif self._current_step == "gazebo_start" and ("gz sim" in line or "Gazebo" in line):
                    if "Headless" in line:
                        self._step_substatus["gazebo_start"] = "Starting headless gz sim"
                    elif "Waiting for Gazebo" in line:
                        self._step_substatus["gazebo_start"] = "Waiting for Gazebo to come up"
                elif self._current_step == "gazebo_world" and "world" in line.lower():
                    self._step_substatus["gazebo_world"] = line[:80]
                elif self._current_step == "spawn":
                    if "model pose" in line.lower():
                        self._step_substatus["spawn"] = f"Spawning at {line.split(':', 1)[-1].strip()[:40]}"
                    elif "model:" in line.lower():
                        self._step_substatus["spawn"] = f"Spawning {line.split('model:', 1)[-1].strip()[:40]}"
                elif self._current_step == "sensors":
                    if "ekf2" in line.lower() and "origin" in line.lower():
                        self._step_substatus["sensors"] = "EKF2 establishing NED origin"
                    elif "uxrce_dds" in line.lower():
                        self._step_substatus["sensors"] = "Initializing uxrce_dds_client"
                    elif "mavlink" in line.lower() and "mode:" in line.lower():
                        self._step_substatus["sensors"] = "Starting MAVLink"
                elif self._current_step == "startup" and "commander" in line.lower():
                    self._step_substatus["startup"] = "Sending commander init commands"

                # Track launch stages. Order matters: more-specific PX4-startup
                # markers must beat the loose cmake/build-output matchers above.
                if "Startup script returned" in line:
                    pass  # handled below
                elif "INFO  [init] Gazebo simulator" in line or "Starting gazebo" in line:
                    self._mark_step("gazebo_start")
                elif "INFO  [init] Gazebo world is ready" in line or "Gazebo world is ready" in line:
                    self._mark_step("gazebo_world")
                elif "INFO  [init] Spawning Gazebo model" in line:
                    self._mark_step("spawn")
                elif "INFO  [gz_bridge]" in line:
                    # The actual gz_bridge runtime module logs with this prefix;
                    # cmake-stage output never does.
                    self._mark_step("sensors")
                elif "Clean" in line and "Cleaning" not in line:
                    self._mark_step("airframe")
                elif "Copying airframe" in line:
                    self._mark_step("build")
                elif "Building PX4" in line:
                    self._mark_step("build")
                # NOTE: removed "ninja" matcher -- it triggered on cmake's
                # "-GNinja" generator argument echoed during configure.

                if "Startup script returned" in line:
                    self._mark_step("startup")
                    self._mark_step("ekf_origin")
                    # Send EKF origin and heading
                    time.sleep(2)
                    self._send_pxh_command("commander set_ekf_origin 0 0 0")
                    time.sleep(1)
                    self._mark_step("heading")
                    self._send_pxh_command("commander set_heading 0")
                    time.sleep(1)
                    self._mark_step("ready")
                    self._completed_steps.append("ready")
                    self._current_step = None
                    self.connected = True
                    self.launching = False
                    # Sim is up — start the RTF poller. Cheap (single
                    # subprocess streaming text we regex-match) so the
                    # value updates a few times a second.
                    self._start_rtf_poller()
                    continue

                if self.process.poll() is not None:
                    self.launching = False
                    return
        except Exception as e:
            print(f"[sim_service] Launch thread error: {e}", flush=True)
        finally:
            if not self.connected:
                print(f"[sim_service] Launch failed. Last 20 lines:", flush=True)
                for line in self._log_lines[-20:]:
                    print(f"  {line}", flush=True)
            self.launching = False

    def _send_pxh_command(self, cmd: str):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(cmd + "\n")
                self.process.stdin.flush()
            except Exception:
                pass

    def switch_camera(self, camera: str) -> dict:
        """Hot-swap the headless stream to a different camera.

        Kills only the currently running stream_camera_webrtc.py worker —
        leaves PX4 and Gazebo untouched — then spawns a fresh worker
        pointed at the new camera's topic. Both cameras are spawned at
        world load, so their topics exist for the lifetime of the sim.

        Returns:
            {"success": True, "camera": "<cam>"} on success
            {"success": False, "error": "..."}   on failure
        """
        if not self.is_connected:
            return {"success": False, "error": "sim not connected"}
        if not self._headless:
            return {"success": False, "error": "not in headless mode"}
        if camera not in self._ALLOWED_CAMERAS:
            return {"success": False, "error": f"unknown camera: {camera!r}"}
        if camera == self._camera:
            return {"success": True, "camera": camera, "noop": True}

        # Use the long-form topic that matches what launch_with_stream.sh
        # ends up running with after sourcing env.sh. The short form
        # /model/<cam>/... is also published by gz, but in some
        # configurations the camera subscriber only receives frames from
        # the world-prefixed form. Mirror the launcher exactly.
        topic = (
            f"/world/{self._world}/model/{camera}_cam"
            "/link/camera_link/sensor/camera/image"
        )

        # Kill the existing stream worker. -f matches anything with
        # "stream_camera" in the command line (matches both the MJPEG and
        # WebRTC variants spawned by launch_with_stream.sh).
        subprocess.run(["pkill", "-f", "stream_camera"], capture_output=True)
        # Wait for the port to actually free up. `pkill` only sends a
        # signal; the OS can take a moment to release the listening
        # socket (TIME_WAIT, lingering FDs). 2s upper bound is plenty.
        for _ in range(20):
            check = subprocess.run(
                ["ss", "-tln", "sport", "= :8080"],
                capture_output=True, text=True,
            )
            if ":8080" not in check.stdout:
                break
            time.sleep(0.1)

        # Pick the same python the launcher would have picked.
        venv_python = os.path.join(REPO_ROOT, ".venv", "bin", "python")
        python_bin = venv_python if os.path.isfile(venv_python) else "python3"

        streamer = os.path.join(REPO_ROOT, "scripts", "stream_camera_webrtc.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = REPO_ROOT
        # The original launcher sources scripts/shell/env.sh which sets
        # GZ_PARTITION=px4. Without this the streamer talks to the default
        # gz partition, doesn't see the camera topics, and serves a black
        # frame. Force it ourselves rather than relying on uvicorn's env.
        env["GZ_PARTITION"] = "px4"

        # Redirect the streamer's stdout/stderr to a log file (same path the
        # original launcher uses) so failed swaps are debuggable.
        log_path = os.path.join(REPO_ROOT, "output", "stream_camera.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        try:
            log_fh = open(log_path, "a", buffering=1)
            log_fh.write(f"\n[switch_camera] respawning streamer for camera={camera} topic={topic}\n")
            log_fh.flush()
            # Detach: we don't keep a handle. The previous worker was
            # similarly detached from this process; we just pkill them
            # when we want to swap or shut down.
            subprocess.Popen(
                [python_bin, streamer,
                 "--port", "8080",
                 "--fps", "15",
                 "--threads", "2",
                 "--topic", topic],
                cwd=REPO_ROOT,
                stdout=log_fh,
                stderr=log_fh,
                stdin=subprocess.DEVNULL,
                env=env,
                close_fds=True,
            )
        except FileNotFoundError as e:
            return {"success": False, "error": f"streamer not found: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

        self._camera = camera
        return {"success": True, "camera": camera}

    def _start_rtf_poller(self):
        """Spawn `gz topic -e -t /stats` and parse `real_time_factor` lines
        into ``self._rtf``. Runs forever in a background thread; killed
        in ``stop()``. Only one poller at a time."""
        if self._stats_proc and self._stats_proc.poll() is None:
            return  # already running
        env = os.environ.copy()
        env.setdefault("GZ_PARTITION", "px4")
        try:
            self._stats_proc = subprocess.Popen(
                ["gz", "topic", "-e", "-t", "/stats"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError:
            # `gz` not on PATH (rare; the sim wouldn't have launched).
            # Leave RTF as None — frontend will show -- and move on.
            return

        proc = self._stats_proc

        def _parse():
            try:
                for raw in proc.stdout:
                    m = _RTF_RE.match(raw.strip())
                    if m:
                        try:
                            self._rtf = float(m.group(1))
                        except ValueError:
                            pass
            except Exception:
                pass

        threading.Thread(target=_parse, daemon=True).start()

    def _stop_rtf_poller(self):
        if self._stats_proc:
            try:
                self._stats_proc.kill()
            except Exception:
                pass
            self._stats_proc = None
        self._rtf = None

    def stop(self):
        self.connected = False
        self.launching = False
        self._completed_steps = []
        self._current_step = None
        self._step_substatus = {}
        self._stream_url = None
        self._camera = None
        self._stop_rtf_poller()
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

        subprocess.run(["pkill", "-f", "gz sim"], capture_output=True)
        subprocess.run(["pkill", "-x", "px4"], capture_output=True)
        # Also kill stream camera workers spawned by launch_with_stream.sh
        subprocess.run(["pkill", "-f", "stream_camera"], capture_output=True)
        for f in ["/tmp/px4_lock-0", "/tmp/px4-sock-0"]:
            try:
                os.remove(f)
            except OSError:
                pass

    @property
    def is_connected(self) -> bool:
        if self.process and self.process.poll() is not None:
            self.connected = False
        return self.connected

    @property
    def launch_progress(self) -> dict:
        steps = []
        for step_id, label in LAUNCH_STEPS:
            if step_id in self._completed_steps:
                status = "done"
            elif step_id == self._current_step:
                status = "active"
            else:
                status = "pending"
            steps.append({
                "id": step_id,
                "label": label,
                "status": status,
                "substatus": self._step_substatus.get(step_id, ""),
            })
        return {"steps": steps}

    def get_log(self, n=50) -> list:
        with self._log_lock:
            return self._log_lines[-n:]

    def get_log_since(self, since: int = 0) -> dict:
        """Return launcher stdout lines with absolute index >= since.

        Same cursor protocol as DetectionService.get_log() — frontend
        passes the last cursor, gets back {lines, start, cursor, dropped}.
        """
        with self._log_lock:
            base = self._log_offset
            total = base + len(self._log_lines)
            requested = max(since, 0)
            dropped = max(0, base - requested)
            start = max(requested, base)
            slice_from = start - base
            lines = list(self._log_lines[slice_from:])
            return {
                "lines": lines,
                "start": start,
                "cursor": total,
                "dropped": dropped,
                "running": self.launching or self.connected,
                "world": self._world,
            }

    @property
    def world(self) -> str:
        return self._world

    @property
    def headless(self) -> bool:
        return self._headless

    @property
    def camera(self) -> Optional[str]:
        """Camera flag stem used for the current headless stream (e.g.
        "fixed"), or None for GUI mode."""
        return self._camera

    @property
    def stream_url(self) -> Optional[str]:
        """Browser-viewable camera stream URL, or None for GUI mode / not ready yet."""
        return self._stream_url

    @property
    def rtf(self) -> Optional[float]:
        """Most recent Gazebo real_time_factor (0..1+). None before the
        poller has read the first frame or after stop()."""
        return self._rtf
