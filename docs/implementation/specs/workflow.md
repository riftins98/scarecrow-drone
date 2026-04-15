# Workflow Spec

How to implement each phase. Follow these steps in order for every piece of work.

## Step 1: Design Plan (BEFORE code)

1. Read the phase document and relevant CLAUDE.md files
2. Identify existing files, endpoints, models to reuse
3. List files to modify and files to create
4. Only proceed to code after the plan is clear

## Step 2: Implementation

1. Follow the design plan from the phase document
2. Use existing code patterns -- check similar files first
3. Small, focused changes -- don't refactor unrelated code
4. Every change as simple as possible. No over-engineering. Three similar lines is better than a premature abstraction
5. Type hints on all Python function signatures
6. Pydantic models for request/response schemas
7. Before finishing: `git diff` and verify no unintended regressions. Every changed line must be justified

## Step 2b: Database Changes

If adding/renaming/removing tables or columns:

1. Create a migration script in `webapp/backend/database/migrations/` named `NNN_description.py`
2. Script MUST be idempotent -- safe to run multiple times
3. Script MUST work on both empty DBs and existing data
4. Template:

```python
"""Migration: <description>"""
import sqlite3

def up(conn: sqlite3.Connection):
    # Check if already applied
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='my_table'")
    if cursor.fetchone():
        return  # Already exists

    conn.executescript("""
        CREATE TABLE my_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ...
        );
    """)
    conn.commit()
```

Rules:
- New columns: add with DEFAULT values so existing rows don't break
- New tables: create with indexes in the migration
- NEVER drop tables in a migration -- only add/modify

## Step 3: Test

1. Run: `cd /Users/saar.raynw/Desktop/scarecrow-drone && python -m pytest tests/ -x -q`
2. Fix any failures -- do not skip or mark expected-to-fail
3. Add new tests for new code (see `specs/testing.md`)

## Step 4: Verify

1. Start backend: `cd webapp && python -m uvicorn backend.app:app --reload --port 8000`
2. Start frontend: `cd webapp/frontend && npm start`
3. Walk through the feature manually
4. Confirm no regressions in existing features

## Step 5: Commit

1. `git add` only relevant files (never `git add -A` blindly)
2. Commit message: brief description of what was done
3. No Co-Authored-By lines
4. No emojis in commits
