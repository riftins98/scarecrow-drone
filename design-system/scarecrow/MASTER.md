# Design System Master File — Scarecrow

> **LOGIC:** When building a specific page, first check `design-system/scarecrow/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

**Project:** Scarecrow — autonomous drone fleet ops console
**Aesthetic:** Military / HUD / industrial control panel (dark, skeuomorphic, monospace)
**Reference Style:** HUD / Sci-Fi FUI + Real-Time Monitoring
**Source of Truth for Existing Look:** `webapp/frontend/src/App.css`

---

## North Star

The interface should feel like a piece of **operations hardware**, not a SaaS product. Cool charcoal metal, olive-drab and gunmetal accents, terminal typography, glow only where data is *live*. Visually quiet at rest, alive when telemetry flows.

Two layers in this system:
1. **Baseline (shipped)** — codifies what's already in `App.css`. Don't drift from this without intent.
2. **Enhancement Layer** — additive: ambient background depth + more motion on live state. Use these on new work; retrofit existing components opportunistically.

---

## 1. Color Palette (Baseline — locked)

| Role | Hex | CSS Variable | Where it's used |
|------|-----|--------------|------------------|
| Background base (dark) | `#1a1a1a` | `--bg-0` | Body bottom of gradient |
| Background mid | `#1c1c1c` → `#2d2d2d` → `#1a1a1a` | `--bg-gradient` | Body `linear-gradient(135deg, …)` |
| Surface (panel) | `#2a2a2a` → `#1f1f1f` | `--surface-1` | `.drone-control`, `.flight-card`, modals |
| Surface inset (status, inputs) | `#1a1a1a` → `#151515` | `--surface-inset` | `.status-panel`, `.script-config` |
| Border, default | `#3a3a3a` | `--border-1` | Most card/panel borders |
| Border, hover/active | `#4a4a4a` / `#5a6b3a` | `--border-2` | Hover state |
| Text, primary | `#c0c0c0` | `--text-1` | Body copy, values |
| Text, secondary | `#909090` | `--text-2` | Dates, labels |
| Text, muted | `#606060` / `#707070` | `--text-3` | Captions, "no data" |
| **Primary accent — Olive Drab** | `#8b9a5b` | `--accent-primary` | Headings, connected state, active checklist, primary CTA |
| Primary accent dark | `#6b7a3b` → `#4a5a2a` → `#3a4a1a` | `--accent-primary-grad` | `.btn-start` gradient |
| **Active / Live — Slate Teal** | `#7a9a9a` | `--accent-live` | In-flight indicator, "active" checklist, pulse dot |
| **Connect — Steel Blue** | `#3a5a6b` → `#2a4a5a` → `#1a3a4a` | `--accent-connect` | Connect button |
| **Stop — Oxidized Red** | `#6b3a3a` → `#5a2a2a` → `#4a1a1a` | `--accent-stop` | Stop button |
| **Abort — Alert Red** | `#8b2a2a` → `#6b1a1a` → `#4a0a0a` | `--accent-abort` | Abort (pulses) |
| Disconnected / fault | `#8b4a4a` | `--accent-fault` | Disconnected status dot |
| Warning | `#a08060` / `#d8a05a` | `--accent-warning` | Connection warnings, script warnings |

**Rules of use**
- Olive drab = "system nominal" or "do the safe primary action." Never use for warnings.
- Slate teal = anything **happening right now** (in-flight, streaming, polling).
- Reds escalate: oxidized → stop deliberately; alert red → abort, must pulse.
- Steel blue is reserved for **connect**, not generic info. Don't redecorate other buttons in it.

---

## 2. Typography (Baseline — locked)

- **Family:** `'Consolas', 'Courier New', monospace` — everywhere, including body. This is non-negotiable for the HUD feel.
- **Headings:** uppercase, `letter-spacing: 2px–4px`, `text-shadow: 2px 2px 4px rgba(0,0,0,0.5)` for top-level, olive-drab color.
- **Labels (LABEL):** uppercase, `letter-spacing: 1–2px`, ~`0.75rem–0.85rem`, color `--text-2` or `--text-3`.
- **Values:** `--text-1`, normal case, `0.9rem–1rem`, weight 500.
- **Timer / counter:** Courier New, ~`1.8rem`, olive-drab with a `text-shadow: 0 0 10px rgba(139,154,91,0.5)` glow.

Do not introduce Google Fonts (Cinzel, Josefin, Inter, etc.) — they break the terminal aesthetic.

---

## 3. Surfaces, borders, shadows (Baseline — locked)

The defining trick of the current look is the **brushed-metal bevel**: a 180° gradient + inner highlight + outer drop shadow. Preserve it.

```css
/* Standard panel */
background: linear-gradient(180deg, #2a2a2a 0%, #1f1f1f 100%);
border: 1px solid #3a3a3a;
border-radius: 4px;  /* never higher than 4px on surfaces; we are not soft */
box-shadow:
  inset 0 1px 0 rgba(255,255,255,0.05),  /* top highlight = "metal" */
  0 4px 20px rgba(0,0,0,0.4);            /* outer depth */
```

```css
/* Standard button */
background: linear-gradient(180deg, [accent-top] 0%, [accent-mid] 50%, [accent-bot] 100%);
border: 1px solid [accent-border];
border-radius: 2px;  /* buttons are sharper than panels */
box-shadow:
  inset 0 1px 0 rgba(255,255,255,0.1),
  0 4px 8px rgba(0,0,0,0.3);
```

```css
/* Inset (recessed) panel — status display, code-style */
background: linear-gradient(180deg, #1a1a1a 0%, #151515 100%);
border: 1px solid #2a2a2a;
border-radius: 2px;
```

Border radii: **2px buttons / 2–4px panels / 4px modal**. Never round, never pill.

---

## 4. Motion (Baseline — keep, then extend)

Baseline transitions: `all 0.2s ease` on hover, `0.3s ease` on bars filling.

Three named animations to standardize on:

| Name | Use | Spec |
|------|-----|------|
| `pulse` | "Live" indicators (in-flight dot, active checklist icon) | 1.5s infinite, box-shadow ring 0→12px transparent |
| `abort-pulse` | Abort button only | 1.5s infinite, glow 5px → 15px alert-red |
| `scan-glow` *(new)* | Subtle olive-drab outer glow on hover of primary surfaces | 200–300ms ease |

Respect `prefers-reduced-motion: reduce` — disable infinite pulses, keep instantaneous state changes visible via color only.

---

## 5. Enhancement Layer — "more in the background, more animation"

This is the *new* direction. Additive, doesn't break baseline. Apply progressively.

### 5a. Background depth (the "more stuff" layer)

Stack these behind `.dashboard` content, in this z-order (lowest → highest):

1. **Base gradient** (already shipped): `linear-gradient(135deg, #1c1c1c, #2d2d2d 50%, #1a1a1a)` on `body`.
2. **Metal cross-hatch** (already shipped): two repeating-linear-gradients at 2px on `.App`.
3. **Faint HUD grid** *(new)*: a single fixed full-viewport `::before` on `.App`, `pointer-events: none`, `opacity: 0.04–0.06`:
   ```css
   background-image:
     linear-gradient(rgba(139,154,91,0.5) 1px, transparent 1px),
     linear-gradient(90deg, rgba(139,154,91,0.5) 1px, transparent 1px);
   background-size: 80px 80px;
   ```
4. **Drifting scanline** *(new)*: a thin 2px olive-drab line that slowly travels top → bottom every ~12s. `position: fixed`, `pointer-events: none`, `opacity: 0.08`. Pause on `prefers-reduced-motion`.
5. **Corner reticles** *(new, optional)*: four small SVG bracket marks in the viewport corners — pure decoration, `opacity: 0.15`, `--accent-primary`. Sells the "instrument panel" framing.
6. **Vignette** *(new)*: radial gradient on `.App::after`, `pointer-events: none`, darkens edges by ~12% so the center reads as "focused on the panel."

Performance: every layer uses `transform` or `opacity`, no filters, no large blurs. All decorative layers must have `pointer-events: none` and `user-select: none`.

### 5b. Motion catalog (the "more animation" layer)

Use sparingly — the *whole point* of motion here is to signal **liveness**, not delight.

| Trigger | Animation | Where |
|---------|-----------|-------|
| Telemetry value updated | 250ms olive-drab flash on the value cell | flight stats, status counters |
| Status transitions (idle → connecting → connected) | 300ms color cross-fade + status-dot glow ramp | `.status-indicator` |
| Live in-flight | Existing `pulse` (keep) + add slowly drifting tick marks around the timer | `.flight-timer` |
| New flight appears in history | 400ms slide-in from below + 600ms olive-drab border flash | `.flight-card` |
| Panel mount | 250ms upward fade (8px translateY) | new panels appearing post-connect |
| Hover on cards/buttons | Existing glow (keep) + add 1px upward translateY for tactile feel | already present on flight-card; extend |
| Loading / pending state | Marching-ants 1px dashed border (olive-drab @ 0.3 opacity), 8s linear | "Compiling [N/1157]…" rows |
| Detection event | 800ms red-orange pulse on the relevant panel border + audible-optional tick | future: detection overlays |
| Stream connecting | Scanline sweep across the stream-link box | `.stream-link` while video loads |

Animation timing standards:
- Micro feedback (hover, click): **150–200ms**
- State change (connect, mount): **250–300ms**
- Decorative ambient (scanline, grid): **8–12s** linear, never faster

---

## 6. Iconography

- **No emoji.** Replace any existing emoji-as-icon with SVG (Lucide preferred — its line style matches the terminal aesthetic).
- Stroke width 1.5–2px, color `currentColor`, sized 16/20/24px.
- Status-dot pattern (small glowing circle) is the canonical "state indicator" — prefer it over icons for binary on/off.

---

## 7. Component contracts

### Buttons (`.btn`)
- Always uppercase, `letter-spacing: 3px`, padding `15px 50px` for primary, `12px 30px` for nav.
- Each variant uses its own 3-stop vertical gradient (see palette). On hover: shift the gradient one tone lighter and add a colored glow shadow.
- Disabled state: collapse to flat `#3a3a3a → #2a2a2a` gradient, text `#505050`, no shadow, `cursor: not-allowed`.

### Panels (`.drone-control`, `.flight-card`, modals)
- Use the standard panel surface recipe (§3). Modals add a stronger outer shadow (`0 10px 40px rgba(0,0,0,0.5)`).

### Inputs (selects, text, checkboxes)
- `background: #2a2a2a`, `border: 1px solid #3a3a3a`, `border-radius: 4px`, focus border `#5a8` (teal — matches `--accent-live`).
- Checkboxes/radios use `accent-color: #5a8`.

### Status indicator
- Dot is 10px, 50% radius, 1px border `--border-1`.
- Connected: `--accent-primary` fill + `0 0 8px --accent-primary` glow.
- Disconnected: `--accent-fault` fill + matching glow.
- Live (in-flight): `--accent-live` fill, glow, plus `pulse` animation.

### Checklist rows
- Done = `--accent-primary` text + icon with 6px text-shadow glow.
- Active = `--accent-live` text + icon pulsing.
- Pending = `#505050` text, no glow.

---

## 8. Layout

- Max content width: **1200px** on dashboard, **800px** on history, **500px** on solo panels.
- Section gap: 30px. Component gap: 15px. Tight interior padding (15–30px), spacious vertical rhythm.
- Centered single-column on every page. No sidebars (yet). If a sidebar is added it must be `--surface-1` with a 1px `--border-1` divider, no shadow.

---

## 9. Responsive

Required breakpoints (test all four):
- 375px — phone (panels collapse to full width, padding 15px)
- 768px — tablet (single column, controls remain centered)
- 1024px — small desktop (current layout works as-is)
- 1440px+ — large desktop (don't widen past 1200px content; let the HUD background fill)

Touch targets ≥ 44px on mobile. Buttons currently meet this; verify on retrofit.

---

## 10. Anti-patterns (do NOT use)

- ❌ Soft / rounded "blob" UI (claymorphism, neumorphism). We are a tool, not a meditation app.
- ❌ AI purple/pink gradients.
- ❌ Glassmorphism (`backdrop-filter: blur(20px)` + transparency). Visually wrong for an ops console; also a perf hit.
- ❌ Bright neon for non-alert state (cyan #0FF, magenta, pure white text).
- ❌ Sans-serif body (Inter, Roboto, etc.) — kills the terminal aesthetic.
- ❌ Serif display fonts (Cinzel, Playfair, Garamond) — we're not a real-estate brand.
- ❌ Border-radius > 4px on surfaces, > 2px on buttons.
- ❌ Emoji as functional icons.
- ❌ Animations faster than 150ms (jittery) or slower than 400ms for state changes (feels broken).
- ❌ Decorative motion that doesn't represent real state. If it pulses, *something* is happening.

---

## 11. Pre-delivery checklist

Run through this before declaring any UI work done:

- [ ] All text uses Consolas / Courier New monospace
- [ ] No emoji icons (Lucide SVGs only)
- [ ] All clickable elements have `cursor: pointer` and a visible hover state
- [ ] Transitions are 150–300ms ease (no jumps, no slow-mo)
- [ ] Focus states visible (1px solid `--accent-live` outline at minimum)
- [ ] Text contrast ≥ 4.5:1 against panel surfaces (check `--text-3` against dark surfaces — borderline)
- [ ] `prefers-reduced-motion: reduce` disables `pulse`, `abort-pulse`, scanline, and any ambient drift
- [ ] Tested at 375 / 768 / 1024 / 1440px
- [ ] No horizontal scroll at any breakpoint
- [ ] No layer added to the background without `pointer-events: none`
- [ ] No new font imports
- [ ] No border-radius > 4px

---

## 12. Open questions for future sessions

- Whether to introduce a subtle CRT scanline texture *over* content (currently rejected — too costume-y).
- Whether to add a real waveform / signal visualization in the dashboard header, replacing the static subtitle.
- Whether the abort button's pulse should change cadence with flight altitude / detection state (probably yes, but needs spec).
