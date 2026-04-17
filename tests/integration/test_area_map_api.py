"""IT-02: Integration tests for /api/areas/* routes."""


def test_list_areas_empty(api_client):
    response = api_client.get("/api/areas")
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_area(api_client):
    create_response = api_client.post("/api/areas", json={"name": "Garage"})
    assert create_response.status_code == 200
    area = create_response.json()
    assert area["name"] == "Garage"
    assert area["status"] == "draft"
    area_id = area["id"]

    get_response = api_client.get(f"/api/areas/{area_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Garage"


def test_get_nonexistent_area_returns_404(api_client):
    response = api_client.get("/api/areas/9999")
    assert response.status_code == 404


def test_list_after_creating(api_client):
    api_client.post("/api/areas", json={"name": "A"})
    api_client.post("/api/areas", json={"name": "B"})
    response = api_client.get("/api/areas")
    assert response.status_code == 200
    areas = response.json()
    assert len(areas) == 2
    names = {a["name"] for a in areas}
    assert names == {"A", "B"}


def test_update_area(api_client):
    created = api_client.post("/api/areas", json={"name": "A"}).json()
    response = api_client.put(
        f"/api/areas/{created['id']}",
        json={"status": "active", "area_size": 42.5},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "active"
    assert updated["area_size"] == 42.5


def test_update_nonexistent_returns_404(api_client):
    response = api_client.put("/api/areas/9999", json={"status": "active"})
    assert response.status_code == 404


def test_delete_area(api_client):
    created = api_client.post("/api/areas", json={"name": "A"}).json()
    response = api_client.delete(f"/api/areas/{created['id']}")
    assert response.status_code == 200
    assert response.json()["success"] is True
    # Should now 404
    assert api_client.get(f"/api/areas/{created['id']}").status_code == 404


def test_delete_nonexistent_returns_404(api_client):
    response = api_client.delete("/api/areas/9999")
    assert response.status_code == 404


def test_start_mapping(api_client):
    response = api_client.post("/api/areas/mapping/start", json={"name": "Room"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["mappingId"] > 0


def test_mapping_status(api_client):
    response = api_client.get("/api/areas/mapping/status")
    assert response.status_code == 200
    data = response.json()
    assert "active" in data
    assert "mapId" in data
    assert "status" in data


def test_flights_for_area(api_client):
    area = api_client.post("/api/areas", json={"name": "Room"}).json()
    # Initially no flights
    response = api_client.get(f"/api/areas/{area['id']}/flights")
    assert response.status_code == 200
    assert response.json() == []
