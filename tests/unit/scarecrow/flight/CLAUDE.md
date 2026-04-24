# flight (unit tests)

Tests for `scarecrow/flight/flight.py` (`Flight` orchestrator).

## Files
- `__init__.py` — Package marker (empty).
- `test_flight.py` — `Flight.run()` lifecycle: connect → health → ekf origin → takeoff → offboard → mission body → stop_offboard → land. Mission failure, abort(), on_status callback.
