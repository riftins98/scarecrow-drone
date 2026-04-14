# database

SQLite persistence layer for flight history and detection results.

## Files
- `db.py` — Tables: `flights` (id, times, pigeons_detected, frames_processed, status, video_path) and `detection_images` (id, flight_id, image_path, timestamp). Functions: create/end flight, add detection image, get flights/flight details.
