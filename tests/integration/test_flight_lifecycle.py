"""IT-01: Full flight lifecycle via API end-to-end."""
from unittest.mock import patch


def test_abort_lifecycle(api_client):
    """Start a flight, abort it, verify status is 'aborted' and data preserved."""
    with patch("services.sim_service.SimService.is_connected", True), \
         patch("services.detection_service.DetectionService.start") as mock_start:
        def fake_start(flight_id, *args, **kwargs):
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
