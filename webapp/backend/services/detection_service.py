"""Manages pigeon detection subprocess."""
import json
import os
import re
import subprocess
import threading
import time
from typing import Optional, Callable

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DEFAULT_SCRIPT = "demo_flight_v2.py"
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts", "flight")

# --- Log-line parsers -------------------------------------------------------
# Flight scripts print rich human-readable status to stdout in addition to the
# structured TELEMETRY: line. These regexes mine that text so the webapp's
# telemetry rail can show live PHASE / AGL / CEILING readouts that no single
# TELEMETRY field carries. Matched against each stdout line in _monitor().

# Phase banners, e.g. "--- Phase 1: stabilize before hover ---" or
# "--- Phase 3: hover near ceiling for 5.0s ---". We keep the descriptive
# part after the colon and uppercase a short label from it.
_PHASE_BANNER_RE = re.compile(r"---\s*Phase\s*\d+\s*:\s*(.+?)\s*---")
# Live altitude-above-ground from descent/climb chatter, e.g.
# "[descent] agl=1.83m  rear=0.50m ...".
_AGL_RE = re.compile(r"\bagl=([\d.]+)\s*m", re.IGNORECASE)
# Ceiling clearance from the ceiling scripts, e.g.
# "ceiling clearance 1.50 m" or "Target ceiling clearance reached: 1.50m".
_CEILING_RE = re.compile(r"ceiling clearance[^\d]*([\d.]+)\s*m", re.IGNORECASE)
# Room-circuit leg progress, e.g. "Leg 2 complete (31.4s)".
_LEG_RE = re.compile(r"\bLeg\s*(\d+)\s*complete", re.IGNORECASE)

# Lidar wall distances. Two log families across the scripts:
#   labeled:  "Front: 1.2m  Left: 0.6m  Right: 0.8m"   (sensor_check, room_circuit_v2 stabilize, demo v1)
#   key=val:  "rear=0.50m right=0.62m", "front=1.20m", "wall=2.50m" / "wall=inf"
# One regex per direction handles both separators (":" or "=") and the
# optional "inf" sentinel (drone sees no wall on that side).
# Numeric values always carry a trailing "m" ("wall=2.50m"); the "inf"
# sentinel ("wall=inf descending") does not, so the unit is optional after inf.
_DIST_RES = {
    "front": re.compile(r"\bfront\s*[:=]\s*(?:(inf)|([\d.]+)\s*m)", re.IGNORECASE),
    "left":  re.compile(r"\bleft\s*[:=]\s*(?:(inf)|([\d.]+)\s*m)", re.IGNORECASE),
    "right": re.compile(r"\bright\s*[:=]\s*(?:(inf)|([\d.]+)\s*m)", re.IGNORECASE),
    "rear":  re.compile(r"\brear\s*[:=]\s*(?:(inf)|([\d.]+)\s*m)", re.IGNORECASE),
    # "wall=" is the active-side distance in the wall-follow controllers; map it
    # to the same WALL readout regardless of which physical side it tracks.
    "wall":  re.compile(r"\bwall\s*[:=]\s*(?:(inf)|([\d.]+)\s*m)", re.IGNORECASE),
}
# Live commanded velocities from the control loops, e.g.
# "fwd=+0.30 lat=-0.10 yaw=+5.0" (wall_follow_v2, room_circuit_v2).
_VEL_RES = {
    "fwd": re.compile(r"\bfwd=([+-]?[\d.]+)", re.IGNORECASE),
    "lat": re.compile(r"\blat=([+-]?[\d.]+)", re.IGNORECASE),
    "yaw": re.compile(r"\byaw=([+-]?[\d.]+)", re.IGNORECASE),
}
# Pursuit outcome (demo_flight_pursuit):
#   "*** TARGET REACHED! Front distance: 1.45m ***"
#   "Pursuit ended: <reason>"
_TARGET_REACHED_RE = re.compile(r"TARGET REACHED!\s*Front distance:\s*([\d.]+)\s*m", re.IGNORECASE)
_PURSUIT_ENDED_RE = re.compile(r"Pursuit ended:\s*(.+?)\s*$", re.IGNORECASE)
# Wall-follow terminal stop reason (wall_follow_v2): "Wall follow stopped: <reason>".
_STOP_REASON_RE = re.compile(r"Wall follow stopped:\s*(.+?)\s*$", re.IGNORECASE)
# Detection throughput (detect_pigeons summary): "FPS: 12.34".
_FPS_RE = re.compile(r"\bFPS:\s*([\d.]+)", re.IGNORECASE)


def _parse_dist(inf_grp: Optional[str], num_grp: Optional[str]) -> Optional[float]:
    """Parse a distance match into meters. The "inf" sentinel (no wall on that
    side) -> None; a numeric group -> rounded float; nothing usable -> None."""
    if inf_grp:
        return None
    if num_grp:
        try:
            return round(float(num_grp), 2)
        except ValueError:
            return None
    return None


def _phase_label(description: str) -> str:
    """Turn a phase-banner description into a short uppercase rail label.

    "stabilize before hover" -> "STABILIZE"
    "hover near ceiling for 5.0s" -> "HOVER"
    "lidar-locked landing" -> "LANDING"
    Falls back to the first meaningful word uppercased.
    """
    words = re.findall(r"[A-Za-z]+", description)
    # Skip filler / adjective leading words so the noun survives:
    # "stabilize before hover" -> STABILIZE, "lidar-locked landing" -> LANDING.
    skip = {
        "the", "a", "an", "to", "for", "near", "at", "before", "after", "with",
        "lidar", "locked", "upward", "downward", "until",
    }
    for w in words:
        if w.lower() not in skip:
            return w.upper()
    return description.strip().upper()


class DetectionService:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.running = False
        self.flight_id: Optional[str] = None
        self.pigeons_detected = 0
        self.frames_processed = 0
        self.detection_images = []
        self.video_path: Optional[str] = None
        self.latest_telemetry: dict = {}
        self._on_detection: Optional[Callable] = None
        self._last_error: Optional[str] = None
        self._output_lines: list = []
        # Monotonic offset of the first line still held in _output_lines.
        # Frontend uses this as a cursor: ask for lines >= cursor, get the
        # new ones plus a new cursor. Survives ring-buffer drops.
        self._output_offset: int = 0
        # Lock keeps the offset/buffer pair consistent between the monitor
        # thread (which appends) and request handlers (which read).
        self._output_lock = threading.Lock()
        # Max lines retained in memory. Frontends poll ~1Hz; flight scripts
        # at full chatter emit a few lines per second, so ~30min of history
        # fits comfortably below 2000.
        self._output_max = 2000
        # Script chosen for this run (None until start() is called).
        self.current_script: Optional[str] = None
        self.current_script_args: dict = {}

    def start(self, flight_id: str,
              on_detection: Optional[Callable] = None,
              script_name: str = DEFAULT_SCRIPT,
              script_args: Optional[dict] = None) -> bool:
        """Start a flight script as a subprocess.

        Args:
            flight_id: Per-flight identifier (also passed to scripts that
                accept --flight-id).
            on_detection: Callback invoked when a DETECTION_IMAGE line is
                parsed. Signature: ``(flight_id, img_path) -> None``.
            script_name: Filename inside scripts/flight/ (defaults to the v2
                detection mission for backwards compat).
            script_args: ``{name: value}`` map of CLI args to pass. Each key
                gets passed as ``--<key-with-dashes> <value>``. Bool values
                become bare flags (or are omitted when False). ``flight_id``
                is always added (unless the script doesn't take it).
        """
        if self.running:
            return False

        # Resolve and validate the script.
        flight_script = os.path.join(SCRIPTS_DIR, script_name)
        if not os.path.isfile(flight_script):
            self._last_error = f"script not found: {script_name}"
            return False
        if not script_name.endswith(".py"):
            self._last_error = f"not a python script: {script_name}"
            return False

        self.flight_id = flight_id
        self.pigeons_detected = 0
        self.frames_processed = 0
        self.detection_images = []
        self.video_path = None
        self.latest_telemetry = {}
        self._on_detection = on_detection
        self._last_error = None
        self._output_lines = []
        self.current_script = script_name
        self.current_script_args = dict(script_args or {})
        # Reset the output cursor for a fresh flight. Without this the
        # frontend would still hold the previous flight's cursor and miss
        # the first chunk of the new run.
        with self._output_lock:
            self._output_lines = []
            self._output_offset = 0

        # Output dir per flight
        output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
        os.makedirs(output_dir, exist_ok=True)

        env = os.environ.copy()
        env["GZ_PARTITION"] = "px4"

        cmd = ["python3", flight_script]
        cmd.extend(self._format_cli_args(script_args or {}))
        # Always pass --flight-id; scripts that don't accept it will error,
        # but the standard ones do. The dict-based args interface already
        # lets the user override this if they want.
        if not any(arg == "--flight-id" for arg in cmd):
            cmd.extend(["--flight-id", flight_id])

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=REPO_ROOT,
        )

        self.running = True
        t = threading.Thread(target=self._monitor, daemon=True)
        t.start()
        return True

    @staticmethod
    def _format_cli_args(script_args: dict) -> list[str]:
        """Convert a {name: value} dict into a list of ``--flag value`` tokens.

        Conventions:
        - Keys with underscores become dashes: ``target_alt`` -> ``--target-alt``.
        - bool True -> bare flag (``--show``).
        - bool False -> omitted entirely (matches argparse store_true semantics).
        - None / empty string -> omitted.
        - Lists -> repeated flag with each value.
        """
        out: list[str] = []
        for raw_name, value in script_args.items():
            flag = "--" + raw_name.replace("_", "-")
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                if value:
                    out.append(flag)
                continue
            if isinstance(value, (list, tuple)):
                for item in value:
                    out.extend([flag, str(item)])
                continue
            out.extend([flag, str(value)])
        return out

    def _monitor(self):
        """Monitor detection subprocess stdout for protocol lines.

        Flight scripts emit these lines for webapp state:
          DETECTION_IMAGE:/path/to/img.png       -- a bird was detected
          TELEMETRY:{"battery":...,"distance":...,"detections":N}
          VIDEO_PATH:/path/to/flight_camera.mp4  -- video built after landing

        Also tolerant of older v1-style lines for backwards compat.
        """
        try:
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                with self._output_lock:
                    self._output_lines.append(line)
                    overflow = len(self._output_lines) - self._output_max
                    if overflow > 0:
                        # Drop the oldest `overflow` lines and advance the
                        # offset so absolute indices remain stable.
                        self._output_lines = self._output_lines[overflow:]
                        self._output_offset += overflow

                # v2 stdout protocol
                if "DETECTION_IMAGE:" in line:
                    img_path = line.split("DETECTION_IMAGE:", 1)[-1].strip()
                    self.detection_images.append(img_path)
                    if self._on_detection:
                        self._on_detection(self.flight_id, img_path)

                elif line.startswith("TELEMETRY:"):
                    try:
                        payload = json.loads(line.split("TELEMETRY:", 1)[1].strip())
                        # Merge, don't replace: log-parsed extras (agl, ceiling,
                        # leg) from other lines must survive a TELEMETRY tick.
                        self.latest_telemetry.update(payload)
                        if "detections" in payload:
                            self.pigeons_detected = int(payload["detections"])
                    except (ValueError, KeyError):
                        pass

                elif line.startswith("VIDEO_PATH:"):
                    self.video_path = line.split("VIDEO_PATH:", 1)[1].strip()

                # Shared: both v1 and v2 print "[detection] Frame N: ..."
                elif "Frame " in line:
                    match = re.search(r"Frame (\d+)", line)
                    if match:
                        self.frames_processed = max(self.frames_processed, int(match.group(1)))

                # v1 legacy summary lines
                elif "Pigeons detected:" in line:
                    match = re.search(r"Pigeons detected: (\d+)", line)
                    if match:
                        self.pigeons_detected = int(match.group(1))

                elif "Frames processed:" in line:
                    match = re.search(r"Frames processed: (\d+)", line)
                    if match:
                        self.frames_processed = int(match.group(1))

                # Mine human log lines for live readouts the TELEMETRY: JSON
                # doesn't carry (phase banners, descent agl, ceiling clearance,
                # circuit legs). Runs after the elif-chain so it sees every
                # line, and merges into latest_telemetry rather than replacing.
                self._parse_log_extras(line)

        except Exception as e:
            self._last_error = str(e)
        finally:
            self.running = False

    def _parse_log_extras(self, line: str) -> None:
        """Extract live readouts from a human stdout line into latest_telemetry.

        These supplement the structured TELEMETRY: payload with values the
        scripts only print as prose: the current phase banner, live AGL during
        climb/descent, ceiling clearance, circuit leg progress, lidar wall
        distances (front/left/right/rear/wall), commanded velocities, and
        pursuit/wall-follow outcomes. Each is merged in place so a value set
        here survives until overwritten and rides alongside whatever the next
        TELEMETRY tick carries.
        """
        m = _PHASE_BANNER_RE.search(line)
        if m:
            self.latest_telemetry["phase"] = _phase_label(m.group(1))
            return

        m = _AGL_RE.search(line)
        if m:
            try:
                self.latest_telemetry["agl"] = round(float(m.group(1)), 2)
            except ValueError:
                pass

        m = _CEILING_RE.search(line)
        if m:
            try:
                self.latest_telemetry["ceiling"] = round(float(m.group(1)), 2)
            except ValueError:
                pass

        m = _LEG_RE.search(line)
        if m:
            try:
                self.latest_telemetry["leg"] = int(m.group(1))
            except ValueError:
                pass

        # Lidar wall distances. A single chatter line may carry several
        # (e.g. "Front: 1.2m Left: 0.6m Right: 0.8m"), so check each direction.
        # "inf" (no wall on that side) clears the readout to None.
        for key, regex in _DIST_RES.items():
            dm = regex.search(line)
            if dm:
                self.latest_telemetry[key] = _parse_dist(dm.group(1), dm.group(2))

        # Commanded velocities from the control loop (fwd/lat/yaw).
        for key, regex in _VEL_RES.items():
            vm = regex.search(line)
            if vm:
                try:
                    self.latest_telemetry[key] = round(float(vm.group(1)), 2)
                except ValueError:
                    pass

        # Pursuit outcome.
        m = _TARGET_REACHED_RE.search(line)
        if m:
            self.latest_telemetry["target"] = "REACHED"
            try:
                self.latest_telemetry["target_dist"] = round(float(m.group(1)), 2)
            except ValueError:
                pass
        else:
            m = _PURSUIT_ENDED_RE.search(line)
            if m:
                # Short uppercase reason token, e.g. "target_lost" -> "TARGET LOST".
                self.latest_telemetry["target"] = m.group(1).strip().replace("_", " ").upper()

        # Wall-follow terminal stop reason.
        m = _STOP_REASON_RE.search(line)
        if m:
            self.latest_telemetry["stop_reason"] = m.group(1).strip().replace("_", " ").upper()

        # Detection FPS (summary line).
        m = _FPS_RE.search(line)
        if m:
            try:
                self.latest_telemetry["fps"] = round(float(m.group(1)), 1)
            except ValueError:
                pass

    def stop(self) -> dict:
        """Detach from the flight process -- let it land and finish on its own.
        The flight script still needs to execute its landing sequence, build the
        video, and exit. The auto-finalize in /api/flight/status picks up the
        final state once the subprocess exits.
        """
        # Do NOT kill the process -- the flight script handles its own landing.
        self.running = False

        result = {
            "pigeons_detected": self.pigeons_detected,
            "frames_processed": self.frames_processed,
            "detection_images": list(self.detection_images),
            "video_path": self.video_path,
        }

        # Fallback: if the subprocess already built the video and printed
        # VIDEO_PATH: before the monitor got a chance to parse it, look for
        # the file on disk.
        if not result["video_path"] and self.flight_id:
            output_dir = os.path.join(REPO_ROOT, "webapp", "output", self.flight_id)
            video = os.path.join(output_dir, "flight_camera.mp4")
            if os.path.exists(video):
                result["video_path"] = video
                self.video_path = video

        return result

    def kill(self) -> bool:
        """Hard-stop the flight script for a panic reset. Unlike stop() (which
        detaches and lets the script land itself), this terminates the
        subprocess immediately so it stops commanding the drone — the caller is
        about to teleport / disarm and doesn't want the script fighting it.

        Also clears the per-flight state (flight_id, telemetry, counters, log)
        so the app returns to a clean pre-flight condition and a new flight can
        be started right away.

        Returns True if a process was running and got killed."""
        self.running = False
        proc = self.process
        had_proc = proc is not None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        self.process = None

        # Wipe flight state so the UI no longer shows a stale flight and
        # start() isn't confused by leftover ids/telemetry.
        self.flight_id = None
        self.current_script = None
        self.current_script_args = {}
        self.latest_telemetry = {}
        self.pigeons_detected = 0
        self.frames_processed = 0
        self.detection_images = []
        self.video_path = None
        with self._output_lock:
            self._output_lines = []
            self._output_offset = 0

        return had_proc

    @property
    def status(self) -> dict:
        with self._output_lock:
            tail = self._output_lines[-10:]
        return {
            "running": self.running,
            "flight_id": self.flight_id,
            "pigeons_detected": self.pigeons_detected,
            "frames_processed": self.frames_processed,
            "last_error": self._last_error,
            "log": tail,
            # Pass through the latest TELEMETRY: payload so the frontend
            # can show altitude / heading / battery in real time. Empty
            # dict before the first telemetry tick arrives.
            "telemetry": dict(self.latest_telemetry),
        }

    def get_log(self, since: int = 0) -> dict:
        """Return all stdout lines with absolute index >= since.

        Returns:
            {
                "lines": [str, ...],   # lines with index in [start, cursor)
                "start": int,          # absolute index of the first returned line
                "cursor": int,         # next index to request (== start + len(lines))
                "dropped": int,        # how many lines were lost to buffer overflow
                                       # before `start` (frontend can show a gap)
                "running": bool,
                "flight_id": str | None,
            }
        """
        with self._output_lock:
            base = self._output_offset
            total = base + len(self._output_lines)
            requested = max(since, 0)
            # If the caller is asking for lines we've already dropped, snap
            # forward to the oldest one we still have and report the gap.
            dropped = max(0, base - requested)
            start = max(requested, base)
            slice_from = start - base
            lines = list(self._output_lines[slice_from:])
            return {
                "lines": lines,
                "start": start,
                "cursor": total,
                "dropped": dropped,
                "running": self.running,
                "flight_id": self.flight_id,
            }
