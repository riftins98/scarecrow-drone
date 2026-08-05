"""TF-Luna frame parsing.

The upward TF-Luna sets the mission's flight altitude (ceiling minus
clearance), so a parsing error here becomes a wrong altitude under a real roof.
The frame parser is pure precisely so it can be verified without hardware.
"""
from scarecrow.sensors.rangefinder.tfluna import (
    FRAME_HEADER,
    MIN_TRUSTED_STRENGTH,
    TFLunaRangefinder,
)


def _frame(distance_cm: int, strength: int = 500, temp: int = 0) -> bytes:
    """Build the 7 payload bytes that follow the two header bytes."""
    payload = bytes(
        [
            distance_cm & 0xFF,
            (distance_cm >> 8) & 0xFF,
            strength & 0xFF,
            (strength >> 8) & 0xFF,
            temp & 0xFF,
            (temp >> 8) & 0xFF,
        ]
    )
    checksum = (FRAME_HEADER + FRAME_HEADER + sum(payload)) & 0xFF
    return payload + bytes([checksum])


def test_parses_distance_in_meters():
    """Sensor reports centimetres; the whole codebase works in metres."""
    reading = TFLunaRangefinder._parse_frame(_frame(250))

    assert reading is not None
    assert reading.distance_m == 2.50
    assert reading.strength == 500


def test_distance_is_little_endian():
    """A byte-order mistake turns 3.00m into 116.65m and flies into the roof."""
    reading = TFLunaRangefinder._parse_frame(_frame(300))

    assert reading is not None
    assert reading.distance_m == 3.00


def test_rejects_bad_checksum():
    payload = bytearray(_frame(250))
    payload[-1] ^= 0xFF

    assert TFLunaRangefinder._parse_frame(bytes(payload)) is None


def test_rejects_saturation():
    """65535cm means "no return", not a 655m ceiling."""
    assert TFLunaRangefinder._parse_frame(_frame(65535)) is None


def test_rejects_zero_distance():
    assert TFLunaRangefinder._parse_frame(_frame(0)) is None


def test_rejects_weak_return():
    """A low-strength reading is a number the sensor itself does not trust."""
    weak = int(MIN_TRUSTED_STRENGTH) - 1

    assert TFLunaRangefinder._parse_frame(_frame(250, strength=weak)) is None
    assert TFLunaRangefinder._parse_frame(_frame(250, strength=weak + 1)) is not None


def test_rejects_short_payload():
    assert TFLunaRangefinder._parse_frame(b"\x00\x01") is None
