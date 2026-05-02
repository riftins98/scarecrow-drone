---
name: commit
description: Update all CLAUDE.md files to reflect current code, then stage and commit changes
disable-model-invocation: true
allowed-tools: Bash(git *) Read Glob Grep Edit Write
argument-hint: [commit message]
---

## Step 1: Update CLAUDE.md Files

Before committing, scan all directories that have a CLAUDE.md and update them to reflect the current state of the code in that directory.

For each CLAUDE.md file found via `find . -name "CLAUDE.md" -not -path "./px4/*" -not -path "./.venv*" -not -path "./node_modules/*"`:

1. Read the current CLAUDE.md
2. List the actual files and subdirectories in that folder
3. Update the CLAUDE.md to accurately describe what exists NOW:
   - File list with one-line descriptions of what each file does
   - Subdirectory list with pointers to their CLAUDE.md (if they have one)
   - Remove references to files that no longer exist
   - Add entries for new files that aren't listed
4. Keep descriptions that explain non-obvious things (algorithms, gotchas, constraints)
5. Don't add filler — if a file's purpose is obvious from its name, a short description is fine

### Handling New Directories

After updating existing CLAUDE.md files, check for **new directories** that were added since the last commit (via `git status` — look for `??` untracked directory entries, or subdirectories mentioned in updated parent CLAUDE.md files that don't have their own CLAUDE.md yet).

For each new directory without a CLAUDE.md:

1. **Ask the user** whether to create a CLAUDE.md for it. Present the directory path and a brief summary of what it contains (file list).
2. If the user approves:
   - Create the CLAUDE.md with accurate content describing the files and purpose of the directory
   - Update the parent directory's CLAUDE.md to reference the new sub-CLAUDE.md (e.g., "see `subdir/CLAUDE.md`")
3. If the user declines or skips, move on without creating the file. Do not create CLAUDE.md files the user hasn't approved.

**Do NOT**:
- Add boilerplate or padding
- Change descriptions that are already accurate
- Create CLAUDE.md files without user approval

## Step 2: Stage and Commit

1. Run `git status` to see all changes
2. Run `git diff --stat` to review what changed
3. Stage all relevant files with `git add` (be specific — don't blindly `git add -A`)
4. Skip files that shouldn't be committed (.env, .db files, __pycache__, node_modules, .venv)
5. Commit with the provided message, or generate one if not provided

## Commit Message Rules

- If the user provided a message via `$ARGUMENTS`, use it as-is
- If no message provided, generate one based on the changes:
  - Start lowercase
  - Brief (one line, under 72 chars)
  - Describe what was done, not how
  - Examples: `add area_maps migration and repository`, `refactor backend into layered architecture`
- **NEVER** reference phase numbers from the implementation plan ("phase 0", "phase 1", etc.). Commits should describe the actual work, not internal planning artifacts. Git history must be independently understandable.
- **NEVER** add Co-Authored-By lines
- **NEVER** add emojis
- **NEVER** add Signed-off-by or other attribution

## Commit Command Format

```bash
git commit -m "the commit message"
```

Do NOT use heredoc, do NOT add multi-line messages unless the changes are complex enough to warrant a body paragraph.
