"""Hangar circuit CLI contract.

The webapp builds its pre-flight form by running the flight script with
--help and parsing argparse's output
(webapp/backend/services/script_metadata.py), so these flags and defaults are
a UI contract, not just developer convenience.

The parser moved into scarecrow.missions.hangar_circuit.cli with the rest of
the mission; the script is now only an entry point.
"""
import pytest

from scarecrow.missions.hangar_circuit.cli import (
    DEFAULT_START_SIDE,
    DEFAULT_WALL_DISTANCE,
    config_from_args,
    parse_args,
)


def test_parse_args_defaults():
    """Mission defaults the webapp renders as the form's initial values."""
    args = parse_args([])

    assert args.wall_distance == DEFAULT_WALL_DISTANCE
    assert args.ceiling_clearance is None
    assert args.flight_id is None
    assert args.start_side == DEFAULT_START_SIDE


def test_parse_args_accepts_wall_dist_alias():
    assert parse_args(["--wall-dist", "1.8"]).wall_distance == 1.8


def test_parse_args_accepts_ceiling_clearance_override():
    assert parse_args(["--ceiling-clearance", "1.0"]).ceiling_clearance == 1.0


def test_parse_args_accepts_start_side_override():
    assert parse_args(["--start-side", "right"]).start_side == "right"
    assert parse_args(["--r"]).start_side == "right"
    assert parse_args(["--l"]).start_side == "left"


def test_start_side_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--l", "--r"])


def test_config_from_args_maps_every_flag():
    config = config_from_args(
        parse_args(
            [
                "--wall-distance", "1.5",
                "--ceiling-clearance", "1.0",
                "--target-alt", "2.2",
                "--start-side", "right",
                "--flight-id", "abc123",
            ]
        )
    )

    assert config.wall_distance_m == 1.5
    assert config.ceiling_clearance_m == 1.0
    assert config.target_alt_m == 2.2
    assert config.start_side == "right"
    assert config.flight_id == "abc123"


def test_config_from_args_generates_a_flight_id_when_absent():
    """Run from a terminal there is no webapp flight id, but output still needs a directory."""
    config = config_from_args(parse_args([]))

    assert config.flight_id
    assert config.flight_id.startswith("hangar_circuit_pursuit_")
    assert config.flight_id in config.output_dir
