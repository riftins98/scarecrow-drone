"""Integration tests for /api/detection/* routes (ADD A.6)."""


def test_detection_status(api_client):
    response = api_client.get("/api/detection/status")
    assert response.status_code == 200
    data = response.json()
    assert data["running"] is False
    assert data["flightId"] is None


def test_get_detection_config(api_client):
    response = api_client.get("/api/detection/config")
    assert response.status_code == 200
    data = response.json()
    assert "confidence_threshold" in data
    assert 0 <= data["confidence_threshold"] <= 1


def test_update_detection_config(api_client):
    response = api_client.put(
        "/api/detection/config",
        json={"confidence_threshold": 0.75},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    # Verify it was saved
    get_response = api_client.get("/api/detection/config")
    assert get_response.json()["confidence_threshold"] == 0.75


def test_update_config_rejects_out_of_range(api_client):
    response = api_client.put(
        "/api/detection/config",
        json={"confidence_threshold": 1.5},
    )
    assert response.status_code == 200
    assert response.json()["success"] is False
