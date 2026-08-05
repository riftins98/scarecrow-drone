"""In-process Gazebo topic subscriptions, replacing per-sample CLI polling.

Every simulated sensor in this package used to read Gazebo the same way::

    while running:
        subprocess.run(["gz", "topic", "-e", "-n", "1", "-t", topic])

That is a fork + exec per sample, per polling thread, in a loop with no sleep.
Each spawn pays the ``gz`` CLI's own startup: loading gz-transport, discovering
the topic, connecting, waiting for one message, exiting. The lidar is read at
control-loop rate and the camera at frame rate, so the sensor layer alone was
spawning hundreds of processes a second -- which is what put an 8-core machine
at load average 21 and held the simulator at RTF 0.13.

Gazebo already exposes the thing the CLI is wrapping. ``gz.transport13`` gives
a Node that subscribes once and delivers a decoded protobuf per message, for
the lifetime of the flight, in-process. Same data, no spawns, and no text
parsing: the lidar's 1440 ranges arrive as a repeated float field rather than
1440 lines to parse with ``str.split``.

The CLI path stays as an automatic fallback. The bindings ship with the
conda-forge ``gz-transport13-python`` package that pixi installs, but the apt
metapackage in the delivery image is a separate question, and the Raspberry Pi
has no Gazebo at all. Callers get the fast path when it is there and the old
behaviour when it is not, without knowing which.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Optional

# Resolved once. The version suffix is part of the module name, so a Gazebo
# upgrade lands here rather than in every sensor.
try:  # pragma: no cover - import success depends on the host environment
    from gz.transport13 import Node as _Node
except Exception:  # pragma: no cover
    _Node = None


def transport_available() -> bool:
    """True when in-process subscriptions can be used."""
    return _Node is not None


def apply_gz_env(env: Optional[dict]) -> None:
    """Export the gz discovery variables into this process.

    The CLI path passed ``GZ_PARTITION`` / ``GZ_IP`` per subprocess. An
    in-process Node reads them from its own environment when it is
    constructed, so without this a subscription silently finds no publisher
    and the sensor just never produces a reading -- a failure that looks
    exactly like a sensor that is not publishing yet.
    """
    if not env:
        return
    for key, value in env.items():
        if key.startswith("GZ_") and value:
            os.environ[key] = value


class GzSubscription:
    """One in-process subscription to a Gazebo topic.

    The Node is held as an attribute deliberately: gz-transport tears the
    subscription down when its Node is collected, so a Node created as a local
    would unsubscribe as soon as ``start()`` returned.

    Callbacks arrive on a gz-transport thread, not the caller's. Consumers must
    guard their own state -- the sensors here already hold a lock around the
    latest sample, which is why the callback contract could stay unchanged.
    """

    def __init__(
        self,
        topic: str,
        msg_type: Any,
        callback: Callable[[Any], None],
        env: Optional[dict] = None,
    ) -> None:
        self._topic = topic
        self._msg_type = msg_type
        self._callback = callback
        self._env = env
        self._node = None
        self._lock = threading.Lock()

    @property
    def topic(self) -> str:
        return self._topic

    @property
    def active(self) -> bool:
        return self._node is not None

    def start(self) -> bool:
        """Subscribe. Returns False if the caller should use the CLI fallback.

        Never raises: a missing binding, a bad topic name and a transport-level
        failure are all "the fast path is unavailable", and the caller's answer
        to all three is the same.
        """
        if _Node is None:
            return False
        with self._lock:
            if self._node is not None:
                return True
            apply_gz_env(self._env)
            try:
                node = _Node()
                if not node.subscribe(self._msg_type, self._topic, self._on_message):
                    return False
            except Exception:
                return False
            self._node = node
            return True

    def stop(self) -> None:
        """Unsubscribe. Safe to call when never started, and twice."""
        with self._lock:
            node, self._node = self._node, None
        if node is None:
            return
        try:
            node.unsubscribe(self._topic)
        except Exception:
            pass

    def _on_message(self, msg: Any) -> None:
        # A raising callback on a transport thread would kill delivery for the
        # rest of the flight with no traceback the pilot ever sees. Dropping
        # the sample matches the old behaviour, where a parse failure just
        # meant the next poll tried again.
        try:
            self._callback(msg)
        except Exception:
            pass
