"""IT-01: Full flight lifecycle via API end-to-end."""
from unittest.mock import patch


def test_full_detection_flight_lifecycle(api_client):
    """connect sim -> start flight -> check status -> stop flight -> see in history."""
    # 1. Pretend sim is connected and detection.start succeeds without real subprocess
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start") as mock_start:
        # Configure the mock to set the service state as if it really started
        def fake_start(flight_id, on_detection=None):
            from dependencies import detection_service
            detection_service.running = True
            detection_service.flight_id = flight_id
            detection_service.pigeons_detected = 0
            detection_service.frames_processed = 0
            return True
        mock_start.side_effect = fake_start

        # Start a flight
        start_response = api_client.post("/api/flight/start")
        assert start_response.status_code == 200
        flight_id = start_response.json()["flightId"]

    # 2. Flight should show in history immediately as "in_progress"
    list_response = api_client.get("/api/flights")
    assert list_response.status_code == 200
    flights = list_response.json()
    assert any(f["id"] == flight_id and f["status"] == "in_progress" for f in flights)

    # 3. Status endpoint reflects active flight
    status_response = api_client.get("/api/flight/status")
    assert status_response.status_code == 200
    assert status_response.json()["isFlying"] is True

    # 4. Stop the flight
    with patch("services.detection_service.DetectionService.stop") as mock_stop:
        def fake_stop():
            from dependencies import detection_service
            detection_service.running = False
            return {
                "pigeons_detected": 3,
                "frames_processed": 50,
                "video_path": "/tmp/flight.mp4",
            }
        mock_stop.side_effect = fake_stop

        stop_response = api_client.post("/api/flight/stop")
        assert stop_response.status_code == 200
        stop_data = stop_response.json()
        assert stop_data["pigeonsDetected"] == 3
        assert stop_data["framesProcessed"] == 50

    # 5. Flight now shows as completed in history
    detail_response = api_client.get(f"/api/flights/{flight_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "completed"
    assert detail["pigeonsDetected"] == 3
    assert detail["framesProcessed"] == 50

    # 6. Summary endpoint returns aggregated data
    summary_response = api_client.get(f"/api/flights/{flight_id}/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["flight_id"] == flight_id


def test_abort_lifecycle(api_client):
    """Start a flight, abort it, verify status is 'aborted' and data preserved."""
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start") as mock_start:
        def fake_start(flight_id, on_detection=None):
            from dependencies import detection_service
            detection_service.running = True
            detection_service.flight_id = flight_id
            return True
        mock_start.side_effect = fake_start

        response = api_client.post("/api/drone/start")
        assert response.status_code == 200
        flight_id = response.json()["flightId"]

    # Abort
    with patch("services.detection_service.DetectionService.stop") as mock_stop:
        def fake_stop():
            from dependencies import detection_service
            detection_service.running = False
        mock_stop.side_effect = fake_stop

        abort_response = api_client.post("/api/drone/abort")
        assert abort_response.status_code == 200

    # Flight should be marked aborted
    detail = api_client.get(f"/api/flights/{flight_id}").json()
    assert detail["status"] == "aborted"
    assert detail["endTime"] is not None


def test_area_map_to_flight_flow(api_client):
    """Create area map, start flight linked to it, verify link persists."""
    area_response = api_client.post("/api/areas", json={"name": "Garage"})
    area_id = area_response.json()["id"]

    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start", return_value=True):
        start_response = api_client.post("/api/drone/start", json={"areaMapId": area_id})
        flight_id = start_response.json()["flightId"]

    # Flight should be linked to area
    flight = api_client.get(f"/api/flights/{flight_id}").json()
    assert flight["areaMapId"] == area_id

    # Area's flights endpoint returns it
    area_flights = api_client.get(f"/api/areas/{area_id}/flights").json()
    assert any(f["id"] == flight_id for f in area_flights)
