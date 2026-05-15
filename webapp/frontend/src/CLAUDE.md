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
- `HudHeader.tsx` — Top banner. Callsign on left, system-state pill in center (STANDBY / BOOT SEQUENCE / SYS NOMINAL / MISSION ACTIVE), local-time clock + four indicator lights (PWR/NET/EKF/DET) on right. DET light pulses when flying.
- `Ticker.tsx` — Horizontal scrolling tag strip between header and telemetry. Left tag shows current state with a glowing bullet.
- `TelemetryRail.tsx` — Horizontal gauge row. Four gauges (ALT 0.00m, BAT slowly drains, SIG 100%, RTF 100%) plus a red GPS / DENIED badge. Values are mocked; only BAT animates so the rail still feels live.
- `Sidebar.tsx` — Vertical nav. "OPS" section (Control, History) is functional; "DIAGNOSTICS" section (World Map, Settings) is greyed out as "locked" placeholders.

Operational components:
- `SimControl.tsx` — Sim launcher panel. Pre-connect: world dropdown + GUI/Headless radio + launch checklist with SVG icons (no emoji). Post-connect: script picker + dynamic argparse form (driven by `/api/sim/options`) + Start/Stop. In headless mode shows a "Open camera stream" link.
- `Minimap.tsx` — Top-down decorative SVG of the garage interior. Drone (olive arrow) follows a hand-built waypoint loop that hugs walls and routes around four obstacles (box A 60-80/60-74, box B 130-144/50-72, box C 120-150/120-134, pillar at 55,140 r=6). ~30s per lap. Trail accumulates the full lap then resets when the drone wraps back to the start.
- `SystemLog.tsx` — Terminal-style scrolling log feed. Spawns INFO/OK/WARN/EKF/NAV/DET lines from canned pools at intervals (idle 2.4s, connected 1.4s, flying 0.7s). Pure visual atmosphere.
- `FlightHistory.tsx` — Mission log. Renders each flight as a wide "mission card" with a colored left stripe (olive/red/teal by status), M-### mission id, status pill, three stats (DUR/FRAMES/HITS), and a detection-density bar.
- `FlightModal.tsx` — Flight detail modal. Three tabs: Summary, Detections (image grid), Recording (video).

## pages/
- `Dashboard.tsx` — Top-level page. Owns `simStatus`, `flightStatus`, `flights`, `selectedFlight` state. Polls `/api/sim/status` every 3s and `/api/flight/status` every 2s when connected. Layout: HudHeader → Ticker → TelemetryRail → (Sidebar | main). Control tab renders SimControl + Minimap side by side, then SystemLog full-width below.

## services/
- `api.ts` — All backend API calls. `connectSim(params)`, `disconnectSim()`, `getSimStatus()`, `getSimOptions()`, `startFlight(params)`, `stopFlight()`, `getFlightStatus()`, `getFlights()`, `getFlight(id)`, `getFlightImages(id)`, `getFlightRecording(id)`, plus URL helpers for detection images and recordings. Uses `REACT_APP_API_BASE` env var (defaults to `http://127.0.0.1:8000`).

## types/
- `flight.ts` — Shared types: `Flight`, `SimStatus`, `FlightStatus`, `LaunchStep` (with `substatus` for live progress), `SimOptions`, `WorldInfo`, `ScriptInfo`, `ScriptArg`, `ScriptArgValues`, `ConnectSimParams`, `StartFlightParams`.

## Conventions
- All clocks (`HudHeader`, `SystemLog`, anywhere else) use **local time** via `Date.getHours()` etc. Never `toISOString()` — that returns UTC and drifts from the user's watch.
- No emoji as icons. Use inline SVGs (Lucide-style line icons).
- New animations must be killable via `@media (prefers-reduced-motion: reduce)` — the App.css block at the end of the Enhancement Layer disables all infinite/ambient animations there.
