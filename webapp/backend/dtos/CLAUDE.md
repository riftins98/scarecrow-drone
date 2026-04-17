# dtos

Pydantic data transfer objects. Used for API request/response schemas AND for passing data between layers (repositories -> services -> controllers). Each table in the database has a matching DTO.

## Naming Convention
- `XxxCreateDTO` — fields needed to create a new entity (no auto-generated id/timestamps)
- `XxxDTO` — full entity representation with all fields

## Files
- `__init__.py` — Re-exports all DTOs for `from dtos import ...`
- `flight_dto.py` — FlightCreateDTO, FlightDTO, FlightSummaryDTO (summary used for `/api/flights/{id}/summary`)
- `area_map_dto.py` — AreaMapCreateDTO, AreaMapDTO (UC1 Map Area)
- `telemetry_dto.py` — TelemetryCreateDTO, TelemetryDTO (1:1 with flights)
- `chase_event_dto.py` — ChaseEventCreateDTO, ChaseEventDTO (UC5 Chase Birds)
- `detection_dto.py` — DetectionImageDTO, DetectionConfigDTO, DetectionStatusDTO (UC4 Detect Birds)
