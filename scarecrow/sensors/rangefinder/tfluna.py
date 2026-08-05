"""TF-Luna rangefinder over UART, for the Raspberry Pi.

The drone carries two TF-Lunas: one downward (wired to PX4 as the height
sensor, not read here) and one upward, which is what this driver serves. The
upward one sets the mission's flight altitude -- ceiling distance minus the
configured clearance -- so a wrong reading here flies the drone into a roof.

WIRING / PI SETUP
    TF-Luna TX -> Pi GPIO15 (RXD, pin 10)
    TF-Luna RX -> Pi GPIO14 (TXD, pin 8)
    5V and GND from the Pi
Enable the PL011 UART and free it from the login console:
    sudo raspi-config  -> Interface Options -> Serial Port
        login shell over serial: NO
        serial hardware enabled: YES
The device is then /dev/serial0 (aliases /dev/ttyAMA0).

PROTOCOL
Each frame is 9 bytes at 115200 baud, published at 100Hz by default:
    0x59 0x59 | distL distH | strengthL strengthH | tempL tempH | checksum
Distance is centimetres, low byte first. The checksum is the low byte of the
sum of the preceding eight.
"""
from __future__ import annotations

import threading
import time

from .base import RangefinderReading, RangefinderSource

FRAME_HEADER = 0x59
FRAME_LENGTH = 9

# Below this the TF-Luna reports a distance it does not actually trust --
# typically a dark, angled or absent surface. Datasheet-recommended floor.
MIN_TRUSTED_STRENGTH = 100.0

# The sensor saturates at 65535cm when it sees nothing at all.
_SATURATED_DISTANCE_CM = 65535

DEFAULT_PORT = "/dev/serial0"
DEFAULT_BAUDRATE = 115200


class TFLunaRangefinder(RangefinderSource):
    """Reads an upward-facing TF-Luna on a serial port.

    Runs a background reader thread and keeps only the most recent valid
    reading: the mission always wants "what is the ceiling distance now", never
    a backlog. A stale queue would make the drone hold altitude against a
    ceiling it has already flown past.
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        *,
        min_strength: float = MIN_TRUSTED_STRENGTH,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._min_strength = min_strength
        self._serial = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._latest: RangefinderReading | None = None

    @property
    def topic(self) -> str | None:
        """Device path. Named `topic` so it mirrors the Gazebo driver."""
        return self._port

    def start(self, *, discover_timeout_s: float = 15.0) -> None:
        """Open the port and begin reading.

        pyserial is imported here, not at module scope, so this module can be
        imported on a dev machine that has no serial stack -- the sensor suite
        selection code imports both backends before choosing one.
        """
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - depends on host
            raise RuntimeError(
                "pyserial is required for the TF-Luna rangefinder: pip install pyserial"
            ) from exc

        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=0.2)
        except Exception as exc:  # pragma: no cover - depends on host
            raise RuntimeError(
                f"could not open TF-Luna on {self._port}: {exc}. "
                "Check the serial console is disabled (raspi-config) and the "
                "user is in the 'dialout' group."
            ) from exc

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def get_reading(self) -> RangefinderReading | None:
        with self._lock:
            return self._latest

    def _read_loop(self) -> None:  # pragma: no cover - requires hardware
        while self._running:
            try:
                if self._serial.read(1) != bytes([FRAME_HEADER]):
                    continue
                if self._serial.read(1) != bytes([FRAME_HEADER]):
                    continue
                payload = self._serial.read(FRAME_LENGTH - 2)
                if len(payload) != FRAME_LENGTH - 2:
                    continue
                reading = self._parse_frame(payload, min_strength=self._min_strength)
                if reading is not None:
                    with self._lock:
                        self._latest = reading
            except Exception:
                # A serial glitch must not kill the reader thread; the mission
                # sees a stale reading and its own timeouts take over.
                time.sleep(0.05)

    @staticmethod
    def _parse_frame(
        payload: bytes, *, min_strength: float = MIN_TRUSTED_STRENGTH
    ) -> RangefinderReading | None:
        """Parse the 7 bytes after the two header bytes. None if unusable.

        Pure and side-effect free so it can be unit-tested without a device --
        which matters, because this is the one place a wiring or endianness
        mistake turns into a wrong flight altitude.
        """
        if len(payload) != FRAME_LENGTH - 2:
            return None

        distance_cm = payload[0] | (payload[1] << 8)
        strength = float(payload[2] | (payload[3] << 8))

        checksum = (FRAME_HEADER + FRAME_HEADER + sum(payload[:6])) & 0xFF
        if checksum != payload[6]:
            return None

        # Saturation means "no return", which is not a distance. Reporting it
        # as 655m would compute a nonsensical target altitude.
        if distance_cm == _SATURATED_DISTANCE_CM or distance_cm <= 0:
            return None
        if strength < min_strength:
            return None

        return RangefinderReading(
            distance_m=distance_cm / 100.0,
            strength=strength,
        )
