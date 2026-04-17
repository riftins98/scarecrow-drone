"""Detection data transfer objects."""
from typing import Optional
from pydantic import BaseModel


class DetectionImageDTO(BaseModel):
    id: int
    flight_id: str
    image_path: str
    timestamp: str


class DetectionConfigDTO(BaseModel):
    confidence_threshold: float = 0.3
    model_path: Optional[str] = None


class DetectionStatusDTO(BaseModel):
    running: bool
    flight_id: Optional[str] = None
    detection_count: int = 0
