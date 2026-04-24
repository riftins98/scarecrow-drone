# implementation

Phased implementation plan for finishing the ADD, plus the manual sim-verification checklist.

## Subdirectories
- `phases/` — One markdown file per phase, from Phase 0 (database) through Phase 9 (documentation). Each phase is a self-contained spec.
- `specs/` — Cross-cutting specs: ADD gap analysis, code style, security, testing strategy, workflow.

## Files
- `README.md` — Entry point: lists the phases, their order, and how to pick up work.
- `MANUAL_SIM_CHECKLIST.md` — Human-run checklist for verifying drone behavior in Gazebo after code changes. Used because full sim tests aren't practical in CI (30-60s startup, GUI dependency, flaky world loads).
