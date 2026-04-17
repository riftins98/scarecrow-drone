"""DetectionImageRepository tests (supports UC4 detection)."""
from repositories import DetectionImageRepository


class TestDetectionImageRepository:
    def test_create_returns_image_with_id(self, repo_db):
        repo = DetectionImageRepository()
        img = repo.create("f1", "/tmp/det_0001.png")
        assert img.id > 0
        assert img.flight_id == "f1"
        assert img.image_path == "/tmp/det_0001.png"
        assert img.timestamp is not None

    def test_get_by_flight_id_returns_all_for_flight(self, repo_db):
        repo = DetectionImageRepository()
        repo.create("f1", "/tmp/det_0001.png")
        repo.create("f1", "/tmp/det_0002.png")
        repo.create("f2", "/tmp/det_0003.png")
        images = repo.get_by_flight_id("f1")
        assert len(images) == 2
        assert all(img.flight_id == "f1" for img in images)

    def test_get_by_flight_id_empty_returns_empty(self, repo_db):
        repo = DetectionImageRepository()
        assert repo.get_by_flight_id("no-flight") == []

    def test_images_ordered_by_timestamp(self, repo_db):
        repo = DetectionImageRepository()
        first = repo.create("f1", "/tmp/a.png")
        second = repo.create("f1", "/tmp/b.png")
        images = repo.get_by_flight_id("f1")
        assert images[0].id == first.id
        assert images[1].id == second.id
