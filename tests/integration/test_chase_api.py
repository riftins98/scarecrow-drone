"""Integration tests for chase event routes (ADD A.7)."""
from services import ChaseEventService


def test_get_chases_for_flight_empty(api_client):
    response = api_client.get("/api/flights/any-flight/chases")
    assert response.status_code == 200
    assert response.json() == []


def test_get_nonexistent_chase_returns_404(api_client):
    response = api_client.get("/api/chases/9999")
    assert response.status_code == 404


def test_chases_appear_after_service_creates_them(api_client):
    # Service-level creation (chase events have no POST endpoint -- they're
    # created by the flight subprocess via DroneService stdout parsing)
    svc = ChaseEventService()
    svc.start_chase("flight-abc", counter_measure_type="pursuit")
    svc.start_chase("flight-abc", counter_measure_type="movement")

    response = api_client.get("/api/flights/flight-abc/chases")
    assert response.status_code == 200
    chases = response.json()
    assert len(chases) == 2


def test_get_single_chase(api_client):
    svc = ChaseEventService()
    chase = svc.start_chase("flight-xyz", counter_measure_type="pursuit")

    response = api_client.get(f"/api/chases/{chase.id}")
    assert response.status_code == 200
    assert response.json()["flight_id"] == "flight-xyz"
