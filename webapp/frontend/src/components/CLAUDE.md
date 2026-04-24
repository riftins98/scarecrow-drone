# components

Reusable UI widgets composed by the Dashboard page.

## Files
- `SimControl.tsx` — Sim connect/disconnect button + flight start/stop controls. Polls `/api/sim/status` and `/api/drone/status`.
- `FlightHistory.tsx` — List of past flights (GET `/api/flights`). Click opens `FlightModal`.
- `FlightModal.tsx` — Modal with per-flight detail: detection images, telemetry summary, recorded video link.
