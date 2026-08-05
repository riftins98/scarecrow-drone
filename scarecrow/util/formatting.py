"""Log-line formatting shared by flight missions.

IMPORTANT: the webapp parses flight-script stdout with regexes -- see
`webapp/backend/services/detection_service.py::_parse_log_extras` and
`scripts/flight/CLAUDE.md`. The exact shape of these strings is a wire format,
not cosmetics. Changing "agl=1.20m" to "AGL 1.20 m" silently removes a gauge
from the telemetry rail with no error anywhere.

That is precisely why they live here rather than being retyped per script:
one definition, one place to keep in step with the parser.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


def format_meters(value: float | None, precision: int = 1) -> str:
    """Render a distance, or "?" when it is missing or non-finite.

    Lidar returns `inf` for "no wall within range", which is meaningful rather
    than broken, so it must not crash a format string or print as "inf".
    """
    if value is None or not math.isfinite(value):
        return "?"
    return f"{value:.{precision}f}m"


def format_altitude(altitude_ref: Mapping[str, Any]) -> str:
    """Render the shared altitude reference as ``agl=X.XXm alt_err=+Y.YYm``.

    Degrades in steps rather than raising: no usable AGL prints "agl=?", and a
    known AGL with no target prints just the AGL. A status line is the wrong
    place to fail.
    """
    agl = altitude_ref.get("agl_m")
    error = altitude_ref.get("error_m")
    if not isinstance(agl, (int, float)) or not math.isfinite(agl):
        return "agl=?"
    if not isinstance(error, (int, float)) or not math.isfinite(error):
        return f"agl={agl:.2f}m"
    return f"agl={agl:.2f}m alt_err={error:+.2f}m"
