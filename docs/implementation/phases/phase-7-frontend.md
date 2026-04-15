# Phase 7: Frontend Expansion

**Dependencies**: Phase 1d (API controllers), Phases 3-6 (endpoints exist)
**Estimated size**: Medium
**Simulation required**: No (can develop against running backend with mock data)

## Goal

Add the missing frontend pages and components from ADD Section 6 (UI Draft): Area Mapping, Telemetry View, Detection Gallery, Chase Event Log, enhanced Flight History, routing.

## Pre-read

- `webapp/frontend/src/pages/Dashboard.tsx` — main page pattern
- `webapp/frontend/src/components/SimControl.tsx` — control panel pattern
- `webapp/frontend/src/components/FlightHistory.tsx` — list pattern
- `webapp/frontend/src/components/FlightModal.tsx` — modal/detail pattern
- `webapp/frontend/src/services/api.ts` — API client pattern
- `webapp/frontend/src/types/flight.ts` — type definitions
- `webapp/frontend/src/App.css` — styling

## Tasks

### 1. Add react-router-dom and update App.tsx
### 2. Add TypeScript types (AreaMap, Telemetry, ChaseEvent, DroneStatus)
### 3. Extend api.ts with all new endpoint functions
### 4. Area Mapping page (`pages/AreaMapping.tsx`)
### 5. Telemetry Panel component (`components/TelemetryPanel.tsx`) — WebSocket or polling
### 6. Detection Gallery page (`pages/DetectionGallery.tsx`)
### 7. Chase Event Log component (`components/ChaseEventLog.tsx`) — in FlightModal
### 8. Enhance FlightHistory.tsx — date filter, status filter, delete button
### 9. Abort button in SimControl.tsx (red, confirmation dialog)

See `phase-4-frontend.md` (the original detailed spec) for full implementation details of each component. That file was replaced by the drone phases but the frontend spec content remains valid. Refer to:
- Types: ADD Section 3.2 (all table schemas = TypeScript interfaces)
- API: ADD Appendix A (all endpoint signatures)
- UI: ADD Section 6 (inputs/outputs per page)

## Verification

1. `cd webapp/frontend && npm run build` — zero errors
2. `npm start` — dev server runs
3. All routes work: `/`, `/areas`, `/detections`
4. Area Mapping page: lists maps, start mapping button works
5. Detection Gallery: shows images, filter by flight
6. Flight History: filters work, delete works
7. During flight: telemetry panel shows live data, abort button visible
8. FlightModal: chase events table shows below detection images
