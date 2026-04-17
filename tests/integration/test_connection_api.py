"""Integration tests for /api/connection/* routes."""


def test_wifi_status(api_client):
    response = api_client.get("/api/connection/wifi")
    assert response.status_code == 200
    assert response.json() == {"connected": True, "ssid": "simulation"}


def test_ssh_connect(api_client):
    response = api_client.post("/api/connection/ssh")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_ssh_disconnect(api_client):
    response = api_client.delete("/api/connection/ssh")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_connection_status(api_client):
    response = api_client.get("/api/connection/status")
    assert response.status_code == 200
    data = response.json()
    assert "wifiConnected" in data
    assert "sshConnected" in data
    assert "droneReady" in data
    assert "streamActive" in data


def test_video_start(api_client):
    response = api_client.post("/api/connection/video/start")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_video_stop(api_client):
    response = api_client.post("/api/connection/video/stop")
    assert response.status_code == 200
    assert response.json()["success"] is True
