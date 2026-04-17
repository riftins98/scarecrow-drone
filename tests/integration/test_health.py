"""Health check endpoint -- smoke test for the whole stack."""


def test_health_returns_ok(api_client):
    response = api_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "sim_connected" in data
