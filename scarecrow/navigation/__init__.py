"""Navigation modules -- unified flight navigation facade and mapping."""

from .map_unit import MapUnit, MappingPoint

__all__ = [
    "CeilingClearanceResult",
    "LidarHoldLandingResult",
    "NavigationUnit",
    "WallFollowResult",
    "MapUnit",
    "MappingPoint",
]


def __getattr__(name: str):
    if name in {
        "CeilingClearanceResult",
        "LidarHoldLandingResult",
        "NavigationUnit",
        "WallFollowResult",
    }:
        from .navigation_unit import (
            CeilingClearanceResult,
            LidarHoldLandingResult,
            NavigationUnit,
            WallFollowResult,
        )

        return {
            "CeilingClearanceResult": CeilingClearanceResult,
            "LidarHoldLandingResult": LidarHoldLandingResult,
            "NavigationUnit": NavigationUnit,
            "WallFollowResult": WallFollowResult,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
