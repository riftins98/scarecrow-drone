"""Area map data transfer objects."""
from typing import Optional
from pydantic import BaseModel


class AreaMapCreateDTO(BaseModel):
    name: str
    boundaries: Optional[str] = None
    home_point: Optional[str] = None


class AreaMapDTO(BaseModel):
    id: int
    name: str
    created_at: str
    updated_at: str
    boundaries: Optional[str] = None
    area_size: Optional[float] = None
    status: str = "draft"
