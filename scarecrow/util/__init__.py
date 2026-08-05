"""Small shared primitives with no drone or simulation dependencies.

Everything here is pure: no I/O, no MAVSDK, no Gazebo. That is deliberate --
these are the pieces flight scripts kept redefining privately, and keeping them
dependency-free is what makes them safe to import from anywhere in the package.
"""

from .formatting import format_altitude, format_meters
from .math_utils import clamp, normalize_angle

__all__ = [
    "clamp",
    "normalize_angle",
    "format_meters",
    "format_altitude",
]
