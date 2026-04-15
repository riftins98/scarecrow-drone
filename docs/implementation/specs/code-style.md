# Code Style Spec

Naming, imports, comments, and commit rules for all code changes.

## Python
- **Naming**: snake_case for functions, variables, files. PascalCase for classes
- **Imports**: absolute imports from project root
  ```python
  # GOOD
  from webapp.backend.repositories.flight_repository import FlightRepository
  from scarecrow.controllers.wall_follow import WallFollowController

  # BAD
  from ..repositories.flight_repository import FlightRepository
  ```
- **Type hints**: required on all function signatures
  ```python
  def create_flight(area_map_id: Optional[int] = None) -> FlightDTO:
  ```
- **Pydantic models**: for all request/response schemas in API controllers
- **Docstrings**: only on public classes and non-obvious functions. Follow existing pattern:
  ```python
  """One-line summary.

  Longer description if needed.

  Args:
      param: Description.

  Returns:
      Description.
  """
  ```
- **Comments**: only where logic is non-obvious. No `# removed`, `# deprecated`, `# TODO` without issue reference
- **No print()**: use logging for production code. print() is acceptable in flight scripts that output to stdout for subprocess monitoring

## TypeScript / React
- **Naming**: camelCase for functions/variables, PascalCase for components/types
- **Path aliases**: use relative imports from `src/`
- **Types**: define in `src/types/`, export named interfaces
- **Components**: functional components with hooks, no class components

## General
- No emojis in code, comments, or commits
- No Co-Authored-By or attribution lines in commits
- Commit messages: brief, lowercase start, describe what was done
  ```
  add area_maps table and migration infrastructure
  refactor backend into layered architecture
  add unit tests for wall follow controller
  ```
- Don't refactor unrelated code while implementing a feature
- Don't add error handling for scenarios that can't happen
- Don't create abstractions for one-time operations

## File Organization
- One class per file for major classes (controllers, services, repositories)
- Related small utilities can share a file
- `__init__.py` should export public API of the package
- Test files mirror source structure: `scarecrow/controllers/wall_follow.py` -> `tests/unit/test_wall_follow.py`
