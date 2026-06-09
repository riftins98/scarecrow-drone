"""Compatibility wrapper for target pursuit controller imports."""
from .pursuit.target import (
    TargetObservation,
    TargetPursuitConfig,
    TargetPursuitController,
    TargetPursuitResult,
    TargetPursuitState,
)

__all__ = [
    "TargetObservation",
    "TargetPursuitConfig",
    "TargetPursuitController",
    "TargetPursuitResult",
    "TargetPursuitState",
]
