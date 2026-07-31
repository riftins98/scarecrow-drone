"""Scarecrow Drone webapp backend -- FastAPI app.

Routes are organized into controller modules by domain. Each controller
imports shared service singletons from `dependencies.py`.

Startup: ensures output directory exists and DB migrations have run
(migrations run automatically via `database.db` module import chain).
"""
import os

from fastapi import FastAPI, HTTPException
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


# --- Frontend -------------------------------------------------------------
#
# Serve the built React app from the backend when a build exists, so the whole
# product is one origin on one port. This is what makes the Docker delivery
# "open the URL and use it": no Node, no dev server, no second port, and no
# CORS. In development the React dev server on :3000 is still used instead --
# there is no build/ directory there unless someone ran `npm run build`.
#
# Mounted LAST so every API router above wins the route match.
FRONTEND_BUILD = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "build")
)

if os.path.isdir(FRONTEND_BUILD):
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(FRONTEND_BUILD, "static")),
        name="static",
    )

    # Paths owned by the API and the file-serving routers. The catch-all must
    # never answer for these: a request that looks like one of them but does
    # not match a route is an error, and must stay an error.
    #
    # This is not cosmetic. `/detection_images/..%2F..%2Fetc/passwd` decodes to
    # more path segments than the two-segment file route accepts, so it misses
    # that route and fell through to the catch-all, which happily returned
    # index.html with a 200 -- turning a blocked traversal attempt into a
    # success status. Covered by tests/integration/test_static_api.py.
    RESERVED_PREFIXES = (
        "api/",
        "detection_images/",
        "recordings/",
        "mission_maps/",
        "docs",
        "redoc",
        "openapi.json",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve the SPA, falling back to index.html for client-side routes.

        A file is returned when one exists (favicon, manifest, asset-manifest);
        anything else gets index.html so a deep link or a refresh does not 404.
        """
        if full_path.startswith(RESERVED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = os.path.realpath(os.path.join(FRONTEND_BUILD, full_path))
        # Containment check: full_path is attacker-controlled, so a crafted
        # "../../etc/passwd" must not escape the build directory.
        if (
            full_path
            and candidate.startswith(FRONTEND_BUILD + os.sep)
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)

        return FileResponse(os.path.join(FRONTEND_BUILD, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
