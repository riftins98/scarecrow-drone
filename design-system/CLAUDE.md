# design-system

Single source of truth for the webapp's visual direction. Generated/maintained via the `ui-ux-pro-max` skill (installed under `.claude/skills/ui-ux-pro-max/`). Future Claude sessions should read the relevant `MASTER.md` *before* writing any UI code so the design stays consistent across sessions and contributors.

## Subdirectories
- `scarecrow/` — Design system for the Scarecrow webapp (military / HUD / monospace dark aesthetic)

## How to use it

When building or redesigning a UI element:
1. Read `design-system/scarecrow/MASTER.md` first.
2. If you're working on a specific page, also check `design-system/scarecrow/pages/<page>.md`. If that file exists, its rules **override** MASTER for that page.
3. Run the pre-delivery checklist at the end of MASTER.md before declaring UI work done.

## Regenerating / extending

The reasoning engine is `.claude/skills/ui-ux-pro-max/scripts/search.py`. Examples:
```bash
# Generate a fresh design system for a new project
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system --persist -p "<project>"

# Add a page-specific override
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system --persist -p "Scarecrow" --page "<page-name>"

# Lookup-only (no persist)
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "dashboard real-time monitoring" --domain style
```

`python3` resolves on Windows via the `python3.bat` shim at `~/.local/bin/python3.bat` (forwards to `python.exe`).

## Note

The skill's auto-generated MASTER for "drone fleet" produced a generic light-mode template that didn't match the existing App.css direction. The current `scarecrow/MASTER.md` was hand-rewritten to codify the actual military/HUD baseline already shipping, plus an additive "Enhancement Layer" for ambient backgrounds and motion. Don't blindly regenerate — diff first.
