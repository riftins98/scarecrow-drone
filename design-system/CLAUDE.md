# design-system

Single source of truth for the webapp's visual direction. Read the relevant `MASTER.md` *before* writing any UI code so the design stays consistent across contributors.

## Subdirectories
- `scarecrow/` — Design system for the Scarecrow webapp (military / HUD / monospace dark aesthetic)

## How to use it

When building or redesigning a UI element:
1. Read `design-system/scarecrow/MASTER.md` first.
2. If you're working on a specific page, also check `design-system/scarecrow/pages/<page>.md`. If that file exists, its rules **override** MASTER for that page.
3. Run the pre-delivery checklist at the end of MASTER.md before declaring UI work done.

## Extending

`scarecrow/MASTER.md` is hand-maintained. Edit it directly.

It was originally seeded by a generator, and that is worth knowing only as a
warning: the generated MASTER for "drone fleet" was a generic light-mode
template that did not match the App.css direction already shipping. It was
rewritten by hand to codify the actual military/HUD baseline, plus an additive
"Enhancement Layer" for ambient backgrounds and motion. The generator was
developer tooling and is not part of this repository — MASTER is now the
source, not its output.
