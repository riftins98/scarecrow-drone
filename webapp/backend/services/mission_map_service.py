"""On-demand mission map rendering for flight history results."""
import os
from pathlib import Path
from typing import Optional

from scarecrow.navigation.map_unit import MapUnit

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = (REPO_ROOT / "webapp" / "output").resolve()


def _flight_output_dir(flight_id: str) -> Path:
    return OUTPUT_ROOT / flight_id


def validate_map_json_path(flight_id: str, map_json_path: str) -> Path:
    """Resolve map_json_path and ensure it stays under the flight output dir."""
    candidate = Path(map_json_path).resolve()
    flight_dir = _flight_output_dir(flight_id).resolve()
    if not str(candidate).startswith(str(flight_dir)):
        raise ValueError("map_json_path escapes flight output directory")
    if not candidate.is_file():
        raise FileNotFoundError(f"map file not found: {candidate}")
    return candidate


def resolve_map_json_path(
    flight_id: str,
    map_json_path: Optional[str] = None,
) -> Optional[Path]:
    """Return a validated map.json path for a flight, with disk fallback."""
    if map_json_path:
        try:
            return validate_map_json_path(flight_id, map_json_path)
        except (ValueError, FileNotFoundError):
            pass
    fallback = _flight_output_dir(flight_id) / "map.json"
    if fallback.is_file():
        return fallback.resolve()
    return None


def render_flight_map_png(
    flight_id: str,
    map_json_path: Optional[str] = None,
    *,
    debug: bool = False,
) -> bytes:
    """Render the annotated mission map PNG for a completed flight."""
    path = resolve_map_json_path(flight_id, map_json_path)
    if path is None:
        raise FileNotFoundError("No mission map available for this flight")
    return MapUnit.render_annotated_png_bytes(path, debug=debug)
