"""Scarecrow Drone webapp backend -- FastAPI app.

Routes are organized into controller modules by domain. Each controller
imports shared service singletons from `dependencies.py`.

Startup: ensures output directory exists and DB migrations have run
(migrations run automatically via `database.db` module import chain).
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from controllers import (
    sim_controller,
    flight_controller,
    drone_controller,
    area_map_controller,
    detection_controller,
    chase_event_controller,
    connection_controller,
    static_controller,
)
from dependencies import sim_service

OUTPUT_ROOT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
)
os.makedirs(OUTPUT_ROOT, exist_ok=True)

app = FastAPI(title="Scarecrow Drone")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sim_controller.router)
app.include_router(flight_controller.router)
app.include_router(drone_controller.router)
app.include_router(area_map_controller.router)
app.include_router(detection_controller.router)
app.include_router(chase_event_controller.router)
app.include_router(connection_controller.router)
app.include_router(static_controller.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "sim_connected": sim_service.is_connected}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
