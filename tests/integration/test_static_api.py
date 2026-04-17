"""Integration tests for static file serving (detection images, recordings)."""
import os


def test_missing_detection_image_returns_404(api_client):
    response = api_client.get("/detection_images/no-flight/no-file.png")
    assert response.status_code == 404


def test_missing_recording_returns_404(api_client):
    response = api_client.get("/recordings/no-flight/no-file.mp4")
    assert response.status_code == 404


def test_path_traversal_blocked(api_client):
    # Attempt to escape OUTPUT_ROOT via ..
    response = api_client.get("/detection_images/..%2F..%2Fetc/passwd")
    # Should 403 or 404 -- either way, definitely not 200
    assert response.status_code in (403, 404)


def test_serves_detection_image_if_exists(api_client, tmp_path):
    """If a detection image exists in the output dir, it's served."""
    from controllers import static_controller
    flight_dir = os.path.join(static_controller.OUTPUT_ROOT, "flight-integration-test")
    detections_dir = os.path.join(flight_dir, "detections")
    os.makedirs(detections_dir, exist_ok=True)
    img_path = os.path.join(detections_dir, "det_test.png")
    with open(img_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nfakepng")

    try:
        response = api_client.get("/detection_images/flight-integration-test/det_test.png")
        assert response.status_code == 200
    finally:
        os.remove(img_path)
        os.rmdir(detections_dir)
        os.rmdir(flight_dir)
