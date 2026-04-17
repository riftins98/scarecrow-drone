"""Chase event data transfer objects."""
from typing import Optional
from pydantic import BaseModel


class ChaseEventCreateDTO(BaseModel):
    flight_id: str
    detection_image_id: Optional[int] = None
    counter_measure_type: str


class ChaseEventDTO(BaseModel):
    id: int
    flight_id: str
    detection_image_id: Optional[int] = None
    start_time: str
    end_time: Optional[str] = None
    counter_measure_type: str
    outcome: Optional[str] = None
