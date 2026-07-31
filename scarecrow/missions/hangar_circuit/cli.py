"""Command line for the hangar circuit pursuit mission.

Lives in the package rather than the script because the webapp introspects it:
`webapp/backend/services/script_metadata.py` runs each flight script with
`--help` and parses argparse's output to build the pre-flight form. The flags,
their types and their help text are therefore a UI contract, not just
developer convenience.
"""
from __future__ import annotations

import argparse
import time

from scarecrow.flight.altitude import DEFAULT_CEILING_CLEARANCE_M
from scarecrow.missions.hangar_circuit.config import HangarCircuitConfig

DEFAULT_WALL_DISTANCE = 2.0
DEFAULT_START_SIDE = "left"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Circuit the hangar while detecting a pigeon, then pursue on sight."
    )
    # Supplied by the webapp, not by a human -- hidden from --help so it does
    # not appear as a field in the generated pre-flight form.
    parser.add_argument("--flight-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--wall-distance",
        "--wall-dist",
        type=float,
        default=DEFAULT_WALL_DISTANCE,
        dest="wall_distance",
        help=(
            "Target distance to the followed wall in meters during circuit legs "
            f"(default: {DEFAULT_WALL_DISTANCE:.1f})."
        ),
    )
    parser.add_argument(
        "--ceiling-clearance",
        type=float,
        default=None,
        help=(
            "Optional minimum safe upward ceiling clearance in meters. When set, "
            "enforces ceiling safety after takeoff and during the mission. "
            f"Takeoff altitude always uses ceiling minus {DEFAULT_CEILING_CLEARANCE_M:.1f}m."
        ),
    )
    parser.add_argument(
        "--target-alt",
        type=float,
        default=None,
        help=(
            "Explicit takeoff/hold altitude in meters AGL. When set, this "
            "overrides auto altitude from the upward ceiling rangefinder."
        ),
    )
    parser.set_defaults(start_side=DEFAULT_START_SIDE)
    start_side_group = parser.add_mutually_exclusive_group()
    start_side_group.add_argument(
        "--start-side",
        choices=("left", "right"),
        help=(
            "Initial rear-corner side to stabilize against before scanning "
            f"(default: {DEFAULT_START_SIDE})."
        ),
    )
    start_side_group.add_argument(
        "--l",
        dest="start_side",
        action="store_const",
        const="left",
        help="Use the left initial rear corner.",
    )
    start_side_group.add_argument(
        "--r",
        dest="start_side",
        action="store_const",
        const="right",
        help="Use the right initial rear corner.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def config_from_args(args: argparse.Namespace) -> HangarCircuitConfig:
    """Turn parsed CLI arguments into a mission config."""
    return HangarCircuitConfig(
        wall_distance_m=args.wall_distance,
        ceiling_clearance_m=args.ceiling_clearance,
        target_alt_m=args.target_alt,
        start_side=args.start_side,
        flight_id=args.flight_id or f"hangar_circuit_pursuit_{int(time.time())}",
    )
