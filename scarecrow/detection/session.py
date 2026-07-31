"""Camera + detector + tracker as one switchable unit.

In the hangar mission this was a closure over five mutable variables
(`detection_enabled`, `camera`, `detector`, plus a pursuit counter and a
suppression flag), toggled from six different places in a 1100-line function.
Turning detection on meant remembering to wire `camera.on_frame` *and* start
the detector, in that order; turning it off meant the reverse. Getting it wrong
left YOLO running against a dead frame source, or a camera pushing frames into
a stopped detector.

Two responsibilities live here:

- **DetectionSession** -- the on/off switch and confidence/capture policy.
- **TargetSuppressor** -- "ignore this target until it goes away", which is how
  a mission avoids re-pursuing the bird it just failed to catch.
"""
from __future__ import annotations

import time


class DetectionSession:
    """Owns whether YOLO is consuming camera frames.

    `set_enabled` is idempotent, so callers can assert the state they want
    without tracking what it currently is.
    """

    def __init__(self, camera, detector, tracker, *, scan_confidence: float, pursuit_confidence: float) -> None:
        self._camera = camera
        self._detector = detector
        self._tracker = tracker
        self._scan_confidence = scan_confidence
        self._pursuit_confidence = pursuit_confidence
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def tracker(self):
        return self._tracker

    @property
    def detector(self):
        return self._detector

    def set_enabled(self, enabled: bool, reason: str) -> None:
        """Attach or detach the detector from the camera frame stream.

        Order matters in both directions: wire the callback before starting the
        detector, and stop the detector before unwiring it. The reverse leaves
        a window where frames arrive at a detector that is not running.
        """
        if enabled == self._enabled:
            return

        self._enabled = enabled
        if enabled:
            self._camera.on_frame = self._detector.process_frame
            self._detector.start()
            print(f"  Detection enabled: {reason}")
        else:
            self._detector.stop()
            self._camera.on_frame = None
            print(f"  Detection disabled: {reason}")

    def use_scan_confidence(self) -> None:
        """Raise the threshold for wall-follow scanning.

        Scanning wants few false positives -- each one costs a whole pursuit
        detour -- so it runs strict.
        """
        self._detector.confidence = self._scan_confidence

    def use_pursuit_confidence(self) -> None:
        """Lower the threshold once committed to a target.

        During pursuit the bird is known to be there and the cost of losing it
        (an abort and a return-to-entry) is far higher than the cost of a
        marginal frame, so it runs permissive.
        """
        self._detector.confidence = self._pursuit_confidence

    def configure_capture(self, prefix: str | None = None, *, reset_counter: bool = True) -> None:
        """Set the naming prefix for saved frames. Saving stays off.

        Continuous saving is disabled everywhere: writing a frame per detection
        during flight competes with the control loop, and the mission only
        wants a handful of chosen stills.
        """
        self._detector.configure_saving(
            save_detections=False,
            save_no_detections=False,
            max_saved_detections=None,
            detection_prefix=prefix,
            reset_counter=reset_counter,
        )

    def capture_next(self, label: str) -> None:
        """Save the next frame containing a detection, once."""
        self._detector.capture_next_detection(label)

    def clear_tracker(self) -> None:
        self._tracker.clear()

    def latest_target(self, *, max_age_s: float, now: float | None = None):
        return self._tracker.latest(max_age_s=max_age_s, now=now)

    def stop(self) -> None:
        self._detector.stop()


class TargetSuppressor:
    """Ignore the current target until it has been out of sight for a while.

    Without this, a mission that fails to reach a bird resumes scanning, sees
    the same bird immediately, and pursues it again -- forever. Suppression
    lifts only after the target has been *absent* for a hold-off period, so a
    single dropped frame does not count as "gone".
    """

    def __init__(self, *, clear_after_lost_s: float = 2.0, log_interval_s: float = 1.0) -> None:
        self._clear_after_lost_s = clear_after_lost_s
        self._log_interval_s = log_interval_s
        self._active = False
        self._started_at = 0.0
        self._last_log_s = 0.0

    @property
    def active(self) -> bool:
        return self._active

    def suppress(self) -> None:
        self._active = True
        self._started_at = time.time()

    def update(self, target_visible: bool, *, confidence: float | None = None, now: float | None = None) -> bool:
        """Refresh suppression state. Returns True while still suppressing."""
        if not self._active:
            return False

        now = time.time() if now is None else now
        if not target_visible and now - self._started_at >= self._clear_after_lost_s:
            self._active = False
            print("  Detection suppression cleared: failed target no longer visible")
            return False

        if target_visible and now - self._last_log_s >= self._log_interval_s:
            self._last_log_s = now
            confidence_text = "" if confidence is None else f"confidence={confidence:.0%}"
            print(
                "  [planner] not entering pursuit: "
                f"reason=target_suppressed_until_lost {confidence_text}".rstrip()
            )
        return True
