"""Flight data transfer objects."""
from typing import Optional
from pydantic import BaseModel


class FlightCreateDTO(BaseModel):
    area_map_id: Optional[int] = None


class FlightDTO(BaseModel):
    id: str
    area_map_id: Optional[int] = None
    start_time: str
    end_time: Optional[str] = None
    duration: float = 0
    pigeons_detected: int = 0
    frames_processed: int = 0
    status: str = "in_progress"
    video_path: Optional[str] = None


class FlightSummaryDTO(BaseModel):
    flight_id: str
    duration: float
    total_detections: int
    avg_speed: Optional[float] = None
