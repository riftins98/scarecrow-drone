"""Manages Gazebo simulation lifecycle."""
import subprocess
import os
import time
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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


class SimService:
    def __init__(self):
        self.process = None
        self.connected = False
        self.launching = False
        self._log_lines = []
        self._completed_steps = []
        self._current_step = None

    def launch(self) -> bool:
        """Launch PX4 + Gazebo in background."""
        if self.connected and self.process and self.process.poll() is None:
            return True
        if self.launching:
            return False

        self.stop()
        time.sleep(1)

        launch_script = os.path.join(REPO_ROOT, "scripts", "shell", "launch.sh")
        if not os.path.exists(launch_script):
            raise FileNotFoundError(f"launch.sh not found at {launch_script}")

        env = os.environ.copy()
        env.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
        env.setdefault("__NV_PRIME_RENDER_OFFLOAD", "1")
        # Spawn drone 5m in front of pigeon billboard, facing north wall (+x, heading=0)
        env["PX4_GZ_MODEL_POSE"] = "5,-4.5,0,0,0,0"

        self.process = subprocess.Popen(
            ["bash", launch_script, "drone_garage"],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
        )

        self._log_lines = []
        self._completed_steps = []
        self._current_step = "cleanup"
        self.launching = True

        t = threading.Thread(target=self._wait_for_ready, daemon=True)
        t.start()
        return True

    def _mark_step(self, step_id):
        if self._current_step and self._current_step not in self._completed_steps:
            self._completed_steps.append(self._current_step)
        self._current_step = step_id

    def _wait_for_ready(self):
        """Wait for PX4 to be ready, reading output and tracking stages."""
        try:
            for line in self.process.stdout:
                line = line.strip()
                self._log_lines.append(line)
                if len(self._log_lines) > 500:
                    self._log_lines = self._log_lines[-200:]

                # Track launch stages
                if "Clean" in line and "Cleaning" not in line:
                    self._mark_step("airframe")
                elif "Copying airframe" in line:
                    self._mark_step("build")
                elif "Building PX4" in line or "ninja" in line.lower():
                    self._mark_step("build")
                elif "Starting gazebo" in line or "Starting gz" in line:
                    self._mark_step("gazebo_start")
                elif "Gazebo world is ready" in line:
                    self._mark_step("gazebo_world")
                elif "Spawning" in line:
                    self._mark_step("spawn")
                elif "gz_bridge" in line:
                    self._mark_step("sensors")
                elif "Startup script returned" in line:
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
                    continue

                if self.process.poll() is not None:
                    self.launching = False
                    return
        except Exception:
            pass
        finally:
            self.launching = False

    def _send_pxh_command(self, cmd: str):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(cmd + "\n")
                self.process.stdin.flush()
            except Exception:
                pass

    def stop(self):
        self.connected = False
        self.launching = False
        self._completed_steps = []
        self._current_step = None
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

        subprocess.run(["pkill", "-f", "gz sim"], capture_output=True)
        subprocess.run(["pkill", "-x", "px4"], capture_output=True)
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
            steps.append({"id": step_id, "label": label, "status": status})
        return {"steps": steps}

    def get_log(self, n=50) -> list:
        return self._log_lines[-n:]
