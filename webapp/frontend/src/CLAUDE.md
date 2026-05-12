# src

React app source. State management is in the top-level `Dashboard` page; child components are presentational and bubble events up via callbacks. API access is centralized in `services/api.ts` — components never `fetch()` directly.

## Subdirectories
- `components/` — Presentational React components (one file per component)
- `pages/` — Top-level screens that own page-level state (Dashboard)
- `services/` — API client and other shared services
- `types/` — Shared TypeScript types and DTOs

## Files
- `index.tsx` — React entry: mounts `<Dashboard>` into the DOM
- `App.tsx` — Root component wrapper
- `App.css` — Global stylesheet (dark theme, all styles classes used by every component)
- `react-app-env.d.ts` — CRA-generated TS ambient types

## components/
- `SimControl.tsx` — The sim launcher panel. Pre-connect: world dropdown + GUI/Headless radio. Post-connect: script picker + dynamic argparse form (driven by `/api/sim/options`) + Start/Stop. In headless mode shows a "Open camera stream" link to the backend-captured URL.
- `FlightHistory.tsx` — Past flights list. Calls `getFlights()` and renders rows; click → `onSelectFlight` callback.
- `FlightModal.tsx` — Flight detail modal: shows detection images and the post-landing recording.

## pages/
- `Dashboard.tsx` — Top-level page. Owns `simStatus`, `flightStatus`, `flights`, `selectedFlight` state. Polls `/api/sim/status` every 3s and `/api/flight/status` every 2s when connected. Renders SimControl + FlightHistory in tabs.

## services/
- `api.ts` — All backend API calls. `connectSim(params)`, `disconnectSim()`, `getSimStatus()`, `getSimOptions()`, `startFlight(params)`, `stopFlight()`, `getFlightStatus()`, `getFlights()`, `getFlight(id)`, `getFlightImages(id)`, `getFlightRecording(id)`, plus URL helpers for detection images and recordings. Uses `REACT_APP_API_BASE` env var (defaults to `http://127.0.0.1:8000`).

## types/
- `flight.ts` — Shared types: `Flight`, `SimStatus`, `FlightStatus`, `LaunchStep` (with `substatus` for live progress), `SimOptions`, `WorldInfo`, `ScriptInfo`, `ScriptArg`, `ScriptArgValues`, `ConnectSimParams`, `StartFlightParams`.
