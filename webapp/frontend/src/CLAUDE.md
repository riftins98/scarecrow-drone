# src

React app source. Single page (Dashboard) with three main widgets: SimControl, FlightHistory, FlightModal.

## Subdirectories
- `components/` — Reusable UI widgets (SimControl, FlightHistory, FlightModal).
- `pages/` — Route-level screens (Dashboard is the only page today).
- `services/` — API client wrapping axios calls to the backend.
- `types/` — Shared TypeScript type definitions.

## Files
- `index.tsx` — React app entry, mounts `App` into `#root`.
- `App.tsx` — Top-level component; renders the Dashboard page.
- `App.css` — Global styles.
- `react-app-env.d.ts` — CRA-generated ambient type declarations.
