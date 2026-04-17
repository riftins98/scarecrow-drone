"""Telemetry data transfer objects."""
from typing import Optional
from pydantic import BaseModel


class TelemetryCreateDTO(BaseModel):
    flight_id: str
    battery_level: Optional[float] = None
    distance: float = 0
    detections: int = 0


class TelemetryDTO(BaseModel):
    flight_id: str
    battery_level: Optional[float] = None
    distance: float = 0
    detections: int = 0
