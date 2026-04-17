"""UT-18: AreaMapService tests."""
from dtos import AreaMapCreateDTO
from repositories import FlightRepository
from services import AreaMapService


class TestAreaMapService:
    def test_create_and_get(self, repo_db):
        svc = AreaMapService()
        created = svc.create_map(AreaMapCreateDTO(name="Garage"))
        fetched = svc.get_map(created.id)
        assert fetched.name == "Garage"
        assert fetched.status == "draft"

    def test_get_all_maps(self, repo_db):
        svc = AreaMapService()
        svc.create_map(AreaMapCreateDTO(name="A"))
        svc.create_map(AreaMapCreateDTO(name="B"))
        all_maps = svc.get_all_maps()
        assert len(all_maps) == 2

    def test_update_map(self, repo_db):
        svc = AreaMapService()
        area = svc.create_map(AreaMapCreateDTO(name="A"))
        updated = svc.update_map(area.id, status="active", area_size=42.0)
        assert updated.status == "active"
        assert updated.area_size == 42.0

    def test_delete_map(self, repo_db):
        svc = AreaMapService()
        area = svc.create_map(AreaMapCreateDTO(name="A"))
        assert svc.delete_map(area.id) is True
        assert svc.get_map(area.id) is None

    def test_start_mapping_creates_area_in_progress(self, repo_db):
        svc = AreaMapService()
        result = svc.start_mapping(name="TestRoom")
        assert result["success"] is True
        assert result["mappingId"] > 0
        area = svc.get_map(result["mappingId"])
        assert area.status == "mapping_in_progress"

    def test_get_flights_for_area(self, repo_db):
        svc = AreaMapService()
        flight_repo = FlightRepository()
        area = svc.create_map(AreaMapCreateDTO(name="Room"))
        flight_repo.create(area_map_id=area.id)
        flight_repo.create(area_map_id=area.id)
        flights = svc.get_flights_for_area(area.id)
        assert len(flights) == 2
