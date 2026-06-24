# src

React app source. State management lives in the top-level `Dashboard` page; child components are presentational and bubble events up via callbacks. API access is centralized in `services/api.ts` — components never `fetch()` directly. Visual direction is locked in [design-system/scarecrow/MASTER.md](../../../design-system/scarecrow/MASTER.md): military / HUD / monospace dark theme.

## Subdirectories
- `components/` — Presentational React components (one file per component)
- `pages/` — Top-level screens that own page-level state (Dashboard)
- `services/` — API client
- `types/` — Shared TypeScript types and DTOs

## Files
- `index.tsx` — React entry: mounts `<App>` into the DOM
- `App.tsx` — Root component. Renders the ambient HUD background layers (`hud-grid`, `hud-scanline`, `hud-noise`, `hud-vignette`, four `hud-reticle` SVG corner brackets) under `<Dashboard>`. All decorative; `pointer-events: none` and `aria-hidden`.
- `App.css` — Global stylesheet. Baseline section codifies the existing military/HUD look; "Enhancement Layer" section (below the marker comment) holds the ambient background and motion catalog defined in `design-system/scarecrow/MASTER.md`.
- `react-app-env.d.ts` — CRA-generated TS ambient types

## components/

App-shell components:
- `HudHeader.tsx` — Top banner. Callsign on left, system-state pill in center (STANDBY / BOOT SEQUENCE / SYS NOMINAL / MISSION ACTIVE), local-time clock + four indicator lights (BAT/ALT/DETS/DET) on right. DET light pulses when flying; DETS lights green once any pigeon is detected.
- `Ticker.tsx` — Horizontal scrolling tag strip between header and telemetry. Left tag shows current state with a glowing bullet.
- `TelemetryRail.tsx` — Horizontal gauge row driven by the backend log parser (`flightStatus.telemetry` + `frames_processed`), defined data-style in `RAIL_SPEC` (one entry per readout: label, value getter, renderer, hover `tip`, `core` flag). Gauges show **only while a script is actively running** (`flightStatus.running` — NOT `flight_id`, which the backend keeps set after a flight ends); otherwise the rail shows a single "AWAITING TELEMETRY" cell with a teal bar sweeping on a loop (killed under `prefers-reduced-motion`). While running: a fixed **core** set (PHASE/ALT/HDG/DIST/DETS/FRAMES/BAT) reads `--` until data arrives; every other readout (TARGET/STOP/AGL/CEILING/FRONT/LEFT/RIGHT/REAR/WALL/VEL/LEG/FPS) is **sticky** (appears once its value first shows, then stays pinned so nothing pops in/out; the set resets when the run stops or `flight_id` changes). Lidar distances <0.5m go red. Every gauge has an **instant** hover tooltip via `useTooltip()` (a single `position:fixed` cursor-following node at the document layer — native `title=` was too slow and the rail's `overflow-x:auto` clips in-flow tooltips). The old Gazebo RTF gauge was removed end to end (no `simStatus.rtf`).
- `Sidebar.tsx` — Vertical nav. "OPS" section (Control, History) is functional; "DIAGNOSTICS" section has a single greyed-out "World Map" placeholder (the Settings item was removed).
- `CameraStream.tsx` — Embeds the headless Gazebo WebRTC camera by iframing the launcher's own viewer page (same origin, so no CORS). States: no-url (GUI mode / URL not surfaced yet), standby (sim launching), live. Has live camera-switch plumbing (`setSimCamera`) and remounts the iframe via a nonce to force a fresh load.

Operational components:
- `SimControl.tsx` — Sim launcher panel. Pre-connect: custom HUD-styled world and stream-camera dropdowns (not native `<select>` popups), GUI/Headless radio, and launch checklist with SVG icons (no emoji). Spawn selection is owned by the right-side map card in `Dashboard` and passed into `ConnectSimParams`. Post-connect: pursuit parameters + Start/Stop, plus a full-width red **RESET DRONE** panic button (`api.resetDrone()` → `/api/sim/reset`) always available while connected: kills the flight, disarms via PX4 console, teleports the drone back to the current spawn, and reapplies launch-time drone values.
- `SpawnPicker.tsx` — Top-down world map (via `garageMap`) for choosing the drone's start location. Draws the SDF-derived floor, valid interior (olive, clickable), wall margin (red hatched), and static obstacles (aircraft silhouettes or boxes) from a `SpawnMap`. Clicks in the margin OR on obstacles are rejected (mirrors backend `world_geometry.validate_spawn`). Reused pre-connect in the right-side map card and post-connect in the re-spawn panel.
- `Minimap.tsx` — Top-down map of the active mapped world, drawn to scale via the shared `garageMap` helpers. The drone marker sits at its **live** world pose (`simStatus.dronePose`, queried from Gazebo), falling back to the session spawn when no live pose is available; a trail follows it while flying. Takes `simStatus`/`flightStatus`/`options`.
- `RespawnPanel.tsx` — Connected-only "Re-spawn" card shown while the drone is not flying. Reuses `SpawnPicker`, calls `/api/sim/spawn`, and updates where RESET returns without relaunching the sim.
- `garageMap.ts` — Shared, non-component module: dynamic `SpawnMap` viewBox + `worldToSvg`/`svgToWorld` mapping (meters↔SVG, oriented to match the Gazebo GUI: +x up, +y left), `inObstacle` (mirrors backend obstacle validation), and `airplanePath`/`obstaclePolygon` drawing helpers. Used by both `SpawnPicker` and `Minimap` so the two maps stay consistent.
- `spawnMapLookup.ts` — Small compatibility helper that resolves the active world's `SpawnMap` from modern `worlds[].spawn` data, indexed `spawnMaps`, or legacy top-level spawn fields.
- `SystemLog.tsx` — Terminal-style read-only stdout feed. Uses SSE (`/api/sim/log/stream` before connected, `/api/flight/log/stream` after connected) for near-real-time launcher/flight-script lines, with cursor polling endpoints as fallback. Clears visible rows when the backend cursor resets, so a new/cleared launch log does not leave stale terminal lines on screen.
- `FlightHistory.tsx` — Mission log. Renders each flight as a wide "mission card" with a colored left stripe (olive/red/teal by status), M-### mission id, status pill, three stats (DUR/FRAMES/HITS), and a detection-density bar.
- `FlightModal.tsx` — Flight detail modal. Tabs: Summary, Detections, and Mission Map when the flight has a saved map. Summary shows compact mission fields (status/date/duration, pigeons detected/deterred, pursuit flows + image count, frames). Detections groups pursuit images by parsed filename phases (detected/start/centered/reached).

## pages/
- `Dashboard.tsx` — Top-level page. Owns `simStatus`, `flightStatus`, `flights`, `selectedFlight`, and pre-connect spawn preview state. Polls `/api/sim/status` every 3s and `/api/flight/status` every 2s when connected. Layout: HudHeader → Ticker → TelemetryRail → (Sidebar | main). Control tab renders the connect/mission panel plus either the pre-connect spawn picker or live Minimap; when connected and not flying it also shows the separate RespawnPanel.

## services/
- `api.ts` — All backend API calls. `connectSim(params)` (params may carry `spawn:{x,y}`), `disconnectSim()`, `getSimStatus()`, `getSimOptions()`, `setSimCamera(camera)`, `setSpawn(x,y)` (re-spawn → `/api/sim/spawn`), `resetDrone()` (panic reset → `/api/sim/reset`), `startFlight(params)`, `stopFlight()`, `getFlightStatus()`, `getFlights()`, `getFlight(id)`, `getFlightImages(id)`, log polling/stream URL helpers for SystemLog, plus URL helpers for detection images and mission maps. Uses `REACT_APP_API_BASE` env var (defaults to `http://127.0.0.1:8000`).

## types/
- `flight.ts` — Shared types: `Flight` (including mission summary fields `pigeonsDeterred` and `pursuitFlowCount`), `SimStatus`, `FlightStatus`, `LaunchStep` (with `substatus` for live progress), spawn map DTOs (`SpawnMap`, `SpawnBounds`, `SpawnObstacle`, `SpawnPoint`), `SimOptions`, `WorldInfo`, `ScriptInfo`, `ScriptArg`, `ScriptArgValues`, `ConnectSimParams`, `StartFlightParams`.

## Conventions
- All clocks (`HudHeader`, `SystemLog`, anywhere else) use **local time** via `Date.getHours()` etc. Never `toISOString()` — that returns UTC and drifts from the user's watch.
- No emoji as icons. Use inline SVGs (Lucide-style line icons).
- New animations must be killable via `@media (prefers-reduced-motion: reduce)` — the App.css block at the end of the Enhancement Layer disables all infinite/ambient animations there.
