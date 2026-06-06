# Scarecrow Drone — User Guides

Step-by-step guides for running the simulation and flight system.

| Guide | Audience | Status |
|-------|----------|--------|
| [Simulation (CLI, no webapp)](simulation-cli.md) | Academic reviewers, live demos | Part 1 |
| [Webapp user guide](simulation-webapp.md) | Academic reviewers, HUD console demos | Part 2 |

---

## Building the Word document (DOCX)

The Markdown files in this folder are the **source of truth**. When you need a picture-rich handout for reviewers, generate a DOCX with [pandoc](https://pandoc.org/):

```bash
# From repo root — Part 1 (CLI)
pandoc docs/guides/simulation-cli.md \
  -o docs/guides/simulation-cli.docx \
  --resource-path=docs/guides

# Part 2 (webapp)
pandoc docs/guides/simulation-webapp.md \
  -o docs/guides/simulation-webapp.docx \
  --resource-path=docs/guides
```

**Install pandoc:**

- Ubuntu: `sudo apt install pandoc`
- macOS: `brew install pandoc`
- WSL: same as Ubuntu (inside WSL)

The generated `simulation-cli.docx` is not committed by default. Re-run the command after updating screenshots or guide text.

---

## Screenshot capture checklist

Save PNGs into `docs/guides/images/`. Target width ~1200 px.

### Part 1 — CLI ([simulation-cli.md](simulation-cli.md))

| # | Filename | When to capture |
|---|----------|-----------------|
| 1 | `02-gazebo-gui.png` | After `launch.sh hangar_lite` is ready — Gazebo window showing hangar + drone |
| 2 | `04-stream-viewer.png` | Browser at `http://localhost:8080` during headless launch |
| 3 | `08-flight-output.png` | `ls` of `webapp/output/<flight_id>/` — `detections/`, `map.json`, `map_annotated.png` |

### Part 2 — Webapp ([simulation-webapp.md](simulation-webapp.md))

| # | Filename | When to capture |
|---|----------|-----------------|
| 1 | `webapp-01-dashboard.png` | Full HUD at `http://localhost:3000` — standby or connected |
| 2 | `webapp-02-pre-connect.png` | Control tab: world, display mode, spawn map |
| 3 | `webapp-03-launch-checklist.png` | Connect in progress — launch checklist visible |
| 4 | `webapp-04-mission-active.png` | Flight running: telemetry rail + minimap + detection timer |
| 5 | `webapp-05-history.png` | History tab with mission cards; optional flight detail modal |

**Naming:** lowercase, hyphens; CLI shots use `NN-` prefix, webapp shots use `webapp-NN-` prefix.

After adding or replacing screenshots, regenerate the matching DOCX with the pandoc commands above.
