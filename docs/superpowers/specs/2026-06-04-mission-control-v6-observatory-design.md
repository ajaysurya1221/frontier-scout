# Mission Control v6 ("Observatory") — Design Spec

> **For agentic workers:** implement via `superpowers:subagent-driven-development`.
> **Source of truth:** the v6 prototype + handoff in `design_handoff_mission_control_v6/`
> (`README.md` §1–§6, `Frontier Scout Mission Control v6.html`, `fs6-*.jsx`, `screenshots/`).
> **Prototype wins** when it disagrees with this spec or the prompt. When the prototype and
> the current Python disagree, **change the Python.** The handoff folder is local design
> scratch (git-excluded) — never ship it.

**Goal:** Port four v6 changes into the existing Textual app (`frontier_scout/tui3/`):
(1) a terminal-portable scan spinner + radar sweep, (2) an Adoption Matrix crosshair +
selected-cell lock frame, (3) a sharper failed-scout state, (4) the sparkline ramp glyphs.

**Architecture:** Additive. New glyphs + spinner constants in `kit.py`; one new timer-driven
widget (`ScanSpinner`) in `widgets.py`; a `motion` flag on `AppState`; markup changes in
`scout_view.py` (matrix + scanning + failure) and `panes.py` (cap-scan). Everything routes
through `glyphs()` / `_ASCIIFY` and `app._paint`. No new dependencies; narrow diffs;
don't touch unrelated tabs.

---

## Settled decisions

- **Motion-off:** add `motion: bool = True` to `AppState`; `data.initial_state` sets it
  `False` when env `FRONTIER_SCOUT_REDUCED_MOTION` is truthy. Motion on → spinner/sweep
  animate; motion off → spinner holds frame 0 and the sweep is a static mid-lit bar (no
  interval). **No Tweaks UI** (Tweaks panel is not ported); the flag + env are the only hooks.
- **Spinner mechanism:** a `ScanSpinner(Static)` widget that owns its `set_interval` in
  `on_mount` (Textual auto-cancels the interval on unmount) and repaints itself via
  `self.update(...)` — never `remove_children`+remount, so no `DuplicateIds`. It renders the
  frame **and** the sweep (one widget; ≤2 intervals, or one combined tick). When motion is
  off it sets no interval and renders the steady frame.
- **Corner glyphs:** `⌜⌝⌞⌟` in `UNI`, `+` in `ASCII`, and `_ASCIIFY: ⌜⌝⌞⌟ → "+"`.

---

## Features (each maps to a v6 README section)

### 1. Portable scan spinner + radar sweep (README §1)
- **kit.py:** add module constants `SPIN_UNI = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]`,
  `SPIN_ASCII = ["|","/","-","\\"]`, and `spinner_frames(unicode: bool = True) -> list[str]`.
  The sweep reuses the existing `seg_on`/`seg_off` (`▰`/`▱`, `#`/`-`) — no new glyph.
- **widgets.py:** `ScanSpinner(Static)` — `on_mount` installs the interval(s) (≈0.09 frame,
  ≈0.07 sweep) when `app.state.motion`, else none; each tick advances the frame index +
  sweep head and `self.update()`s painted markup. Sweep = fixed-width run of `seg_off` with
  the `head` cell bright (`seg_on`, mint/phosphor) and `head-1/-2` a dim tail; `head =
  (head+1) % width`. All glyphs from `glyphs(app.state.unicode)`; color via `app._paint`.
- **scout_view.py:** render `ScanSpinner` in the Scout scanning surface (the `ScanProgress`
  analogue — per `screenshots/02-scanning.png`: spinner + sweep + staged checklist), shown
  while `app._scanning`. Replaces the v5 rotated `◉`.
- **panes.py:** render `ScanSpinner` in the capability-tab scanning block (Guard/Deps/
  Settings `r`-scan — the `CapScanning` analogue).

### 2. Adoption Matrix — crosshair + lock frame (README §2)
- **`scout_view._adoption_matrix`:** when `app.state.current` is set, paint the matching
  **fit-row** label and **risk-column** label in `fit_tone(current.fit)` / `risk_tone(current.risk)`
  **bold**; all other axis labels stay muted. (Selection drives it — Textual has no
  verdict-hover; that is correct + sufficient.)
- **`scout_view._cell_markup`:** when the cell holds the selected verdict (`sel`), frame its
  dot run with corner glyphs — `⌜…⌝` above / `⌞…⌟` below — toned **mint** (or **red** for the
  HOLD/danger corner). The selected dot stays `radar_core` (`◉`) as the primary signal; the
  frame is reinforcement. The readout line under the grid still names the selection (never
  color-only).

### 3. Failed-scout state (README §3)
- **scout_view scan-failure surface:** a signal-lost motif — `✕` (red) + a short `seg_off`
  run (`▱▱▱▱▱` / `-----`) — and a keyed recovery ladder: `r` retry · `P` switch engine ·
  `·` run `--demo`. Reuse the existing recovery actions / `_failure_compass`; the body line
  is unchanged. Pure markup, no spend on the render path.

### 4. Sparkline ramp glyphs (README §5 — bundled kit.py already has it)
- **kit.py:** `UNI["spark"] = "▁▂▃▄▅▆▇█"`, `ASCII["spark"] = ".:-=+*#%"`, and
  `_ASCIIFY: ▁→. ▂→: ▃→- ▄→= ▅→+ ▆→* ▇→#` (`█` stays mapped via `bar_full → "#"`; not re-added).

---

## Files touched
| File | Change |
|---|---|
| `tui3/kit.py` | spark glyphs; `SPIN_*` + `spinner_frames()`; corner glyphs + `_ASCIIFY` |
| `tui3/widgets.py` | `ScanSpinner` timer-driven widget |
| `tui3/state.py` | `AppState.motion: bool = True` |
| `tui3/data.py` | `initial_state` reads `FRONTIER_SCOUT_REDUCED_MOTION` → `motion` |
| `tui3/scout_view.py` | scanning (`ScanSpinner`), `_adoption_matrix` crosshair, `_cell_markup` lock frame, failure ladder |
| `tui3/panes.py` | cap-scan `ScanSpinner` block |
| `tui3/theme.tcss` | only if `ScanSpinner` needs a `height: auto` rule (minimal) |
| `tests/test_tui3_*` | new coverage (below) |

## Degradation contract (README §6 — re-verify after porting)
color / **mono** (`mono()` strips color, keeps bold/dim) / unicode / **ascii** (`asciify`) /
**light**. Spinner → `|/-\` ascii; sweep → `#`/`-`; corners → `+`; ramp → `.:-=+*#%`; mono →
single phosphor hue. The glyph + tone + **word** is always the signal. Cosmetic-only
(glow/text-shadow, gradients, heat tint, scanlines/vignette, border-radius, transitions,
hover wipe, caret slide) → **map to nothing**. **No entrance/content animation;** motion lives
only in the spinner/sweep and pauses when motion is off.

## Test plan (add; keep existing `tests/test_tui3_*` green)
- **kit:** `spinner_frames(True) == SPIN_UNI`; `spinner_frames(False) == SPIN_ASCII`;
  `glyphs(False)["spark"] == ".:-=+*#%"`; `asciify("▁▂▃▄▅▆▇█")` is all-ASCII (`.:-=+*##`);
  `asciify("█") == "#"`; each corner glyph folds to `"+"`.
- **matrix:** with a selected verdict, `_adoption_matrix` markup tones the matching fit-row +
  risk-col labels (bold); `_cell_markup` emits the corner glyphs around the selected cell;
  both fold in mono/ascii.
- **spinner:** `ScanSpinner` mounts; a tick advances the frame; holds frame 0 when
  `motion=False`; renders correct glyphs on the ascii path.
- **failure:** the scan-fail markup contains `✕`, a `seg_off` run, and the `r`/`P`/`--demo` ladder.

## Out of scope
Tweaks panel (accent/theme/glyphs/density/width/instrument/motion); cosmetic web effects;
entrance/content animation; unrelated tabs; new dependencies.

## Definition of done
All four features render correctly across **tiny/micro/narrow/mid/wide** and in
**color/mono/ascii/light**; `tests/test_tui3_*` pass; the new coverage above is added; diffs
are narrow; no Tweaks panel; no new deps. Verified via a Pilot boot + render check + ruff.
Lands via branch → PR → relax→merge→restore (protected `main`).
