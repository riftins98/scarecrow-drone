"""Chase event lifecycle for UC5 (Chase Birds)."""
from datetime import datetime
from typing import Optional

from dtos.chase_event_dto import ChaseEventCreateDTO, ChaseEventDTO
from repositories import ChaseEventRepository


class ChaseEventService:
    VALID_OUTCOMES = {"dispersed", "lost", "aborted"}
    VALID_MEASURES = {"pursuit", "movement", "combined"}

    def __init__(self, chase_event_repo: Optional[ChaseEventRepository] = None):
        self.chase_event_repo = chase_event_repo or ChaseEventRepository()

    def start_chase(
        self,
        flight_id: str,
        counter_measure_type: str,
        detection_image_id: Optional[int] = None,
    ) -> ChaseEventDTO:
        if counter_measure_type not in self.VALID_MEASURES:
            raise ValueError(f"Invalid counter_measure_type: {counter_measure_type}")
        return self.chase_event_repo.create(ChaseEventCreateDTO(
            flight_id=flight_id,
            detection_image_id=detection_image_id,
            counter_measure_type=counter_measure_type,
        ))

    def end_chase(self, chase_id: int, outcome: str) -> Optional[ChaseEventDTO]:
        if outcome not in self.VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome: {outcome}")
        self.chase_event_repo.update(
            chase_id,
            outcome=outcome,
            end_time=datetime.now().isoformat(),
        )
        return self.chase_event_repo.get_by_id(chase_id)

    def get_chases_for_flight(self, flight_id: str) -> list[ChaseEventDTO]:
        return self.chase_event_repo.get_by_flight_id(flight_id)

    def get_chase(self, chase_id: int) -> Optional[ChaseEventDTO]:
        return self.chase_event_repo.get_by_id(chase_id)
