#!/usr/bin/env python3
"""Render an annotated map image from a saved map.json."""
from __future__ import annotations

import argparse

from scarecrow.navigation.map_unit import MapUnit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate a saved scarecrow map.json")
    parser.add_argument("map_json_path", help="Path to the map.json file to render")
    parser.add_argument("--show", action="store_true", help="Display the plot when a GUI is available")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output_path = MapUnit.annotate_map(args.map_json_path, show=args.show)
    print(f"Map annotated successfully: {output_path}")
