"""UT-13: AreaMapRepository CRUD tests."""
from dtos import AreaMapCreateDTO
from repositories import AreaMapRepository, FlightRepository


class TestAreaMapRepository:
    def test_create_returns_area_map(self, repo_db):
        repo = AreaMapRepository()
        area = repo.create(AreaMapCreateDTO(name="Garage"))
        assert area.id > 0
        assert area.name == "Garage"
        assert area.status == "draft"
        assert area.created_at is not None

    def test_create_with_boundaries(self, repo_db):
        repo = AreaMapRepository()
        area = repo.create(AreaMapCreateDTO(
            name="Room", boundaries='[{"x":0,"y":0}]'
        ))
        fetched = repo.get_by_id(area.id)
        assert fetched.boundaries == '[{"x":0,"y":0}]'

    def test_get_by_id_nonexistent_returns_none(self, repo_db):
        repo = AreaMapRepository()
        assert repo.get_by_id(9999) is None

    def test_get_all_returns_all_areas(self, repo_db):
        repo = AreaMapRepository()
        a1 = repo.create(AreaMapCreateDTO(name="A"))
        a2 = repo.create(AreaMapCreateDTO(name="B"))
        all_areas = repo.get_all()
        names = {a.name for a in all_areas}
        assert "A" in names
        assert "B" in names

    def test_update_status_and_size(self, repo_db):
        repo = AreaMapRepository()
        area = repo.create(AreaMapCreateDTO(name="A"))
        repo.update(area.id, status="active", area_size=42.5)
        updated = repo.get_by_id(area.id)
        assert updated.status == "active"
        assert updated.area_size == 42.5

    def test_update_refreshes_updated_at(self, repo_db):
        import time
        repo = AreaMapRepository()
        area = repo.create(AreaMapCreateDTO(name="A"))
        original_updated = area.updated_at
        time.sleep(1.1)  # SQLite datetime('now') has second resolution
        repo.update(area.id, status="active")
        updated = repo.get_by_id(area.id)
        assert updated.updated_at > original_updated

    def test_delete_removes_area(self, repo_db):
        repo = AreaMapRepository()
        area = repo.create(AreaMapCreateDTO(name="A"))
        assert repo.delete(area.id) is True
        assert repo.get_by_id(area.id) is None

    def test_delete_nonexistent_returns_false(self, repo_db):
        repo = AreaMapRepository()
        assert repo.delete(9999) is False

    def test_get_flights_for_area(self, repo_db):
        area_repo = AreaMapRepository()
        flight_repo = FlightRepository()
        area = area_repo.create(AreaMapCreateDTO(name="A"))
        flight_repo.create(area_map_id=area.id)
        flight_repo.create(area_map_id=area.id)
        flight_repo.create()  # no area — shouldn't appear
        flights = area_repo.get_flights_for_area(area.id)
        assert len(flights) == 2
        assert all(f.area_map_id == area.id for f in flights)
