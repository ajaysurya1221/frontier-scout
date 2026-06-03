# Mission Control v6 ("Observatory") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
> **Spec:** `docs/superpowers/specs/2026-06-04-mission-control-v6-observatory-design.md`. **Behavioral authority:** the v6 handoff in `design_handoff_mission_control_v6/` (`README.md` §1–§6, the prototype `fs6-*.jsx` + `Frontier Scout Mission Control v6.html`, `screenshots/`). Prototype wins; when prototype and current Python disagree, change the Python. The handoff folder is git-excluded — never commit it.

**Goal:** Add the four v6 changes to the Textual app: a terminal-portable scan spinner + radar sweep, an Adoption Matrix crosshair + selected-cell lock frame, a sharper failed-scout ladder, and the sparkline ramp glyphs.

**Architecture:** Additive. New glyphs + spinner constants in `kit.py`; a `motion` flag on `AppState` (+ env override in `data.initial_state`); one new timer-driven widget `ScanSpinner` in `widgets.py`; markup/surface changes in `scout_view.py` and `panes.py`. Every glyph routes through `glyphs()`/`_ASCIIFY`; every renderable through `app._paint`. No new deps; don't port Tweaks; don't touch unrelated tabs.

**Tech Stack:** Python 3.11, Textual (`Static`/`set_interval`), Rich markup, pytest (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest`).

**Conventions:** branch `feat/tui-v6-observatory` (already created, protected `main`). Commit per task. Run tests with `/opt/miniconda3/bin/python` (bare `python` is not on PATH). The 3 `test_implement.py` failures are env-only — ignore.

---

### Task 1: kit.py glyph layer — spark + spinner frames + corner glyphs

**Files:**
- Modify: `frontier_scout/tui3/kit.py` (`UNI` ~36, `ASCII` ~43, `_ASCIIFY` ~60; append spinner constants after `glyphs()` ~54)
- Test: `tests/test_tui3_kit_v6.py` (create)

- [ ] **Step 1: Write the failing test** — `tests/test_tui3_kit_v6.py`

```python
from frontier_scout.tui3.kit import (
    SPIN_UNI, SPIN_ASCII, spinner_frames, glyphs, asciify,
)


def test_spinner_frames_select_by_mode():
    assert spinner_frames(True) == SPIN_UNI
    assert spinner_frames(False) == SPIN_ASCII
    assert SPIN_ASCII == ["|", "/", "-", "\\"]
    assert len(SPIN_UNI) >= 4


def test_spark_ramp_glyphs():
    assert glyphs(True)["spark"] == "▁▂▃▄▅▆▇█"
    assert glyphs(False)["spark"] == ".:-=+*#%"
    folded = asciify("▁▂▃▄▅▆▇█")
    assert folded.isascii(), folded
    assert folded == ".:-=+*##"      # ▇→# and █→# (bar_full) — monotonic, no conflict
    assert asciify("█") == "#"        # gauge/bar_full fallback unchanged


def test_matrix_corner_glyphs():
    g = glyphs(True)
    assert (g["corner_tl"], g["corner_tr"], g["corner_bl"], g["corner_br"]) == ("⌜", "⌝", "⌞", "⌟")
    assert glyphs(False)["corner_tl"] == "+"
    for c in ("⌜", "⌝", "⌞", "⌟"):
        assert asciify(c) == "+"
```

- [ ] **Step 2: Run — expect FAIL** (`KeyError: 'spark'` / `ImportError: SPIN_UNI`)

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_kit_v6.py -q
```

- [ ] **Step 3: Add the glyphs.** In `UNI` (after the `seg_*`/`cap_*` line), add:

```python
    "spark": "▁▂▃▄▅▆▇█",
    "corner_tl": "⌜", "corner_tr": "⌝", "corner_bl": "⌞", "corner_br": "⌟",
```

In `ASCII` (mirror):

```python
    "spark": ".:-=+*#%",
    "corner_tl": "+", "corner_tr": "+", "corner_bl": "+", "corner_br": "+",
```

In `_ASCIIFY` (add a line; `█` is intentionally NOT re-added — it already maps via `bar_full → "#"`):

```python
    "▁": ".", "▂": ":", "▃": "-", "▄": "=", "▅": "+", "▆": "*", "▇": "#",
    "⌜": "+", "⌝": "+", "⌞": "+", "⌟": "+",
```

After `def glyphs(...)` (~line 54), add the spinner constants + helper:

```python
# Frame-cycling spinner (terminal-native; replaces the v5 CSS-rotated ◉). A list,
# so it lives next to UNI/ASCII rather than inside them. The radar sweep reuses
# the existing seg_on/seg_off glyphs — no new glyph needed.
SPIN_UNI = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPIN_ASCII = ["|", "/", "-", "\\"]


def spinner_frames(unicode: bool = True) -> list[str]:
    """Active spinner frames — braille in unicode, ``|/-\\`` in ascii."""
    return SPIN_UNI if unicode else SPIN_ASCII
```

- [ ] **Step 4: Run — expect PASS.** Also run the existing kit suite to confirm no regression:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_kit_v6.py tests/ -k "kit or gauge" -q
```

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/tui3/kit.py tests/test_tui3_kit_v6.py
git commit -m "feat(tui3): v6 kit glyphs — spark ramp, spinner frames, matrix corners"
```

---

### Task 2: motion flag — AppState + reduced-motion env

**Files:**
- Modify: `frontier_scout/tui3/state.py` (`AppState` ~147, after `color: bool = True`)
- Modify: `frontier_scout/tui3/data.py` (`initial_state` ~69)
- Test: `tests/test_tui3_provider.py` (append — it already imports `AppState`; or `tests/test_tui3_kit_v6.py`)

- [ ] **Step 1: Write the failing test** (append to `tests/test_tui3_provider.py`)

```python
def test_appstate_has_motion_default_on():
    from frontier_scout.tui3.state import AppState
    assert AppState(repo="/x", repo_name="x").motion is True


def test_initial_state_honors_reduced_motion_env(monkeypatch, tmp_path):
    from frontier_scout.tui3 import data as _data
    monkeypatch.setenv("FRONTIER_SCOUT_REDUCED_MOTION", "1")
    assert _data.initial_state(tmp_path, demo=True).motion is False
    monkeypatch.delenv("FRONTIER_SCOUT_REDUCED_MOTION", raising=False)
    assert _data.initial_state(tmp_path, demo=True).motion is True
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: motion` / `TypeError: unexpected keyword 'motion'`)

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -k motion -q
```

- [ ] **Step 3: Implement.** In `state.py` `AppState`, after `color: bool = True`:

```python
    motion: bool = True  # spinner/sweep animate; False = reduced-motion (hold a steady frame)
```

In `data.py` `initial_state`, before the `return AppState(...)`, compute the flag and pass it:

```python
    import os
    motion = os.environ.get("FRONTIER_SCOUT_REDUCED_MOTION", "").strip().lower() not in (
        "1", "true", "yes", "on",
    )
```

Add `motion=motion,` to the `AppState(...)` keyword args.

- [ ] **Step 4: Run — expect PASS.**

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -k motion -q
```

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/tui3/state.py frontier_scout/tui3/data.py tests/test_tui3_provider.py
git commit -m "feat(tui3): motion flag on AppState + FRONTIER_SCOUT_REDUCED_MOTION env"
```

---

### Task 3: ScanSpinner widget (frame spinner + glyph radar sweep)

**Files:**
- Modify: `frontier_scout/tui3/widgets.py` (append the class; it already imports `Static`)
- Test: `tests/test_tui3_spinner.py` (create — uses Pilot like `tests/test_tui3_r_refresh.py`)

- [ ] **Step 1: Write the failing test** — `tests/test_tui3_spinner.py`

```python
from __future__ import annotations
import asyncio
from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.widgets import ScanSpinner


def _run(coro):
    return asyncio.run(coro)


def test_scan_spinner_advances_when_motion_on():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            sp = ScanSpinner("scanning")
            await app.screen.mount(sp)
            await pilot.pause()
            f0 = sp._frame
            sp._tick_frame()           # one frame tick
            assert sp._frame != f0     # advanced
            assert "scanning" in str(sp.content)   # label present
    _run(go())


def test_scan_spinner_holds_frame_when_motion_off():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.state = app.state.with_(motion=False, unicode=False)
            sp = ScanSpinner("scanning")
            await app.screen.mount(sp)
            await pilot.pause()
            # ascii path: spinner frame is from SPIN_ASCII; sweep uses '#'/'-'
            txt = str(sp.content)
            assert sp._frame == 0
            assert ("|" in txt or "/" in txt or "-" in txt or "\\" in txt)
    _run(go())
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError: ScanSpinner`)

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_spinner.py -q
```

- [ ] **Step 3: Implement.** Append to `widgets.py` (add the import at top: `from frontier_scout.tui3.kit import glyphs, spinner_frames`):

```python
class ScanSpinner(Static):
    """Frame-cycling spinner + glyph radar-sweep, driven by a Textual timer.

    Replaces the v5 CSS-rotated ◉ (a terminal can't rotate a glyph). Renders the
    active spinner frame plus a sweep — a fixed-width run of ``seg_off`` pips with
    one bright ``seg_on`` cell travelling across it (a dim two-cell tail behind it).
    Self-updates via ``.update()`` (never remove+remount → no DuplicateIds); the
    interval auto-cancels on unmount. When ``app.state.motion`` is False the spinner
    holds frame 0 and the sweep is a static mid-lit bar (no interval).
    """

    def __init__(self, label: str = "scanning", *, width: int = 12, **kw) -> None:
        super().__init__("", **kw)
        self._label = label
        self._w = width
        self._frame = 0
        self._head = 0

    def on_mount(self) -> None:
        self._repaint()
        if getattr(self.app.state, "motion", True):
            self.set_interval(0.09, self._tick_frame)
            self.set_interval(0.07, self._tick_sweep)

    def _tick_frame(self) -> None:
        self._frame = (self._frame + 1) % len(spinner_frames(self.app.state.unicode))
        self._repaint()

    def _tick_sweep(self) -> None:
        self._head = (self._head + 1) % self._w
        self._repaint()

    def _repaint(self) -> None:
        uni = self.app.state.unicode
        gl = glyphs(uni)
        motion = getattr(self.app.state, "motion", True)
        frame = spinner_frames(uni)[self._frame if motion else 0]
        head = self._head if motion else self._w // 2
        cells = []
        for i in range(self._w):
            if i == head:
                cells.append(f"[#24d6a8]{gl['seg_on']}[/]")          # bright head
            elif motion and i in (head - 1, head - 2):
                cells.append(f"[#24d6a8 dim]{gl['seg_on']}[/]")      # dim tail
            else:
                cells.append(f"[#152232]{gl['seg_off']}[/]")        # track
        self.update(self.app._paint(
            f"[#24d6a8 b]{frame}[/] {''.join(cells)}  [#6e8aa1]{self._label}…[/]"
        ))
```

- [ ] **Step 4: Run — expect PASS.**

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_spinner.py -q
```

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/tui3/widgets.py tests/test_tui3_spinner.py
git commit -m "feat(tui3): ScanSpinner widget — portable frame spinner + glyph radar sweep"
```

---

### Task 4: Scout scan-progress surface (render ScanSpinner while scanning)

**Files:**
- Modify: `frontier_scout/tui3/scout_view.py` (`build_scout` ~137; add `_scan_progress(app, gl)` near `_empty` ~437)
- Test: `tests/test_tui3_spinner.py` (append)

**Context:** `build_scout` (137–171) has no scanning branch today (scan feedback is the footer/header). `app._scanning` (bool, set in `app.run_scout`) is the signal. Read `fs6-scout.jsx` `ScanProgress` + `screenshots/02-scanning.png` for the staged checklist intent (watch → match → decide). The progress surface replaces the `_empty` body while `_scanning` is true and there are no verdicts yet.

- [ ] **Step 1: Write the failing test** (append to `tests/test_tui3_spinner.py`)

```python
def test_scout_home_shows_spinner_while_scanning():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.state = app.state.with_(verdicts=(), scope="all")
            app._scanning = True
            await app._render_pane()
            await pilot.pause()
            assert app.query(ScanSpinner), "no ScanSpinner mounted while scanning"
    _run(go())
```

- [ ] **Step 2: Run — expect FAIL** (no `ScanSpinner` in the tree).

- [ ] **Step 3: Implement.** Add `_scan_progress(app, gl)` to `scout_view.py` returning a `Vertical(classes="scout-progress")` that mounts a `ScanSpinner` (import it: `from frontier_scout.tui3.widgets import ClickStatic, ScanSpinner`) plus a staged checklist (`watch · match · decide`, glyphs via `gl`, painted via `_S`). In `build_scout`, between `_scanbar` and the `if not verdicts:` block, add:

```python
    if getattr(app, "_scanning", False):
        root.compose_add_child(_scan_progress(app, gl))
        return root
```

(So during a scan the progress surface shows instead of the empty/list. Keep it above the existing `if not verdicts:` early return.)

- [ ] **Step 4: Run — expect PASS.** Plus the broad tui3 suite to confirm no scanning-path regression:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_spinner.py tests/ -k "tui3 and (scout or scan or pressing)" -q
```

- [ ] **Step 5: Commit** (`feat(tui3): Scout scan-progress surface with ScanSpinner`).

---

### Task 5: Cap-scan spinner (panes scanning block)

**Files:**
- Modify: `frontier_scout/tui3/app.py` (`_refresh_worker` ~1192 — set/clear a cap-scan flag), `frontier_scout/tui3/panes.py` (cap-tab render — Guard ~216, Deps ~292, Settings ~471)
- Test: `tests/test_tui3_r_refresh.py` (append)

**Context:** Cap tabs render an empty state ("Press r to …") + `_scan_btn`; there's no "scanning" display. Add a per-tab flag set when `_refresh_worker(kind)` starts and cleared on `WorkDone`/`WorkFailed`, and render a `ScanSpinner` when the active cap-tab is scanning. Read `fs6-tabs.jsx` `CapScanning`.

- [ ] **Step 1: Write the failing test** (append `tests/test_tui3_r_refresh.py`)

```python
def test_cap_tab_shows_spinner_while_scanning():
    from frontier_scout.tui3.widgets import ScanSpinner
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("4")          # Guard
            await pilot.pause()
            app._cap_scanning = "guard"     # simulate worker-in-flight
            app.state = app.state.with_(guard_cache=None)
            await app._render_pane()
            await pilot.pause()
            assert app.query(ScanSpinner), "no ScanSpinner on a scanning cap tab"
    _run(go())
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement.** In `app.py`: init `self._cap_scanning: str | None = None` in `__init__`; in `_refresh_worker(kind)` set `self._cap_scanning = kind` before launching the worker; clear it (`self._cap_scanning = None`) in the `WorkDone`/`WorkFailed` handlers. In `panes.py`, in each cap builder (`_guard`, `_deps`, `_settings`), when `getattr(app, "_cap_scanning", None) == <tab>`, compose a `ScanSpinner(f"scanning {tab}")` (import `ScanSpinner`) ahead of the empty/cache render and return early. Keep mouse+key parity: the existing `_scan_btn` and `r` binding are unchanged.

- [ ] **Step 4: Run — expect PASS** + `-k "tui3 and r_refresh"`.

- [ ] **Step 5: Commit** (`feat(tui3): cap-tab scan spinner (Guard/Deps/Settings)`).

---

### Task 6: Adoption Matrix axis crosshair

**Files:**
- Modify: `frontier_scout/tui3/scout_view.py` `_adoption_matrix` (~249 — the risk-axis header row + per-row fit labels)
- Test: `tests/test_tui3_matrix.py` (append) — note this file tests pure helpers; add a render-markup test via the existing `_adoption_matrix` (it needs an `app`; mount via Pilot like `test_tui3_r_refresh`, or assert on `_S` output — prefer a small Pilot test in `tests/test_tui3_r_refresh.py` if `_adoption_matrix` needs `app`).

**Context (README §2a):** when `app.state.current` is set, paint its **fit-row** label and **risk-column** label in `fit_tone(current.fit)` / `risk_tone(current.risk)` and **bold**; all other axis labels muted. `fit_tone`/`risk_tone` are in `kit.py`. The risk-axis header cells and the per-row fit labels are built in `_adoption_matrix` (see the V5 widget-column header). Compare each label against `current.fit` / `current.risk`.

- [ ] **Step 1: Write the failing test** (Pilot, in `tests/test_tui3_r_refresh.py`)

```python
def test_matrix_crosshair_tones_selected_axes():
    from frontier_scout.tui3.state import Verdict
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(140, 40)) as pilot:   # wide → matrix
            await pilot.pause()
            v = Verdict.from_payload({"tool_name": "x", "verdict": "adopt", "fit": "high", "risk": "low"})
            app.state = app.state.with_(verdicts=(v,), scope="all", sel=0)
            await app._render_pane(); await pilot.pause()
            txt = _pane_text(app)
            # fit_tone(high)=mint #24d6a8, risk_tone(low)=mint; the matched labels are bold-toned
            assert "#24d6a8 b]high" in txt or "#24d6a8 b]low" in txt, txt
    _run(go())
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the crosshair in `_adoption_matrix`: when `app.state.current` exists, render the matching risk-column header label and fit-row label as `[{_hex(fit_tone(cur.fit))} b]{label}[/]` / `[{_hex(risk_tone(cur.risk))} b]{label}[/]`; others stay `[{_hex('muted')}]…[/]`. (Mono keeps `b`; ascii unaffected — labels are words.)
- [ ] **Step 4: Run — expect PASS** + `-k "tui3 and matrix"`.
- [ ] **Step 5: Commit** (`feat(tui3): Adoption Matrix axis crosshair on selection`).

---

### Task 7: Adoption Matrix selected-cell lock frame

**Files:**
- Modify: `frontier_scout/tui3/scout_view.py` `_cell_markup` (~197)
- Test: `tests/test_tui3_matrix.py` (append — `_cell_markup` is callable with a fake `app`; reuse the file's `_v` helper + a minimal `app` stub exposing `_paint`/`state.unicode`, or a Pilot test)

**Context (README §2b):** when a cell holds the selected verdict (`sel` is in the cell's indices), frame its dot run with the corner glyphs — `corner_tl … corner_tr` above the dots, `corner_bl … corner_br` below — toned mint (red for the HOLD/danger corner: `fit=="low" and risk=="high"`). The selected dot stays `radar_core` (already implemented at line ~237). Glyphs via `gl["corner_*"]`.

- [ ] **Step 1: Write the failing test** asserting `_cell_markup(...)` for a cell containing the selected verdict includes `gl["corner_tl"]` (`⌜`), and that `asciify` of the markup yields `+`. (Mirror the existing matrix-test harness.)
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the corner frame in `_cell_markup` (wrap the dot run with the four corner glyphs when the cell is selected; tone mint, or red for the danger corner).
- [ ] **Step 4: Run — expect PASS** + `-k "tui3 and matrix"`.
- [ ] **Step 5: Commit** (`feat(tui3): Adoption Matrix selected-cell corner lock frame`).

---

### Task 8: Failed-scout ladder

**Files:**
- Modify: the scout failure surface — `frontier_scout/tui3/app.py` `_failure_compass` (~1395) is the current v5 failure-recovery render. Confirm against `fs6-scout.jsx` `ScanFail`; if the prototype wants a fuller in-pane surface, add `_scan_fail(app, gl)` to `scout_view.py` and render it on failure. Prefer enhancing the existing `_failure_compass`.
- Test: `tests/test_tui3_provider.py` (append — it already tests `_failure_compass`)

**Context (README §3):** signal-lost motif `✕` (red) + a short `seg_off` run (`▱▱▱▱▱`/`-----`); a keyed ladder `r` retry · `P` switch engine · `·` `--demo`. Body line unchanged. All glyphs via `gl`/`_ASCIIFY`. No spend on render.

- [ ] **Step 1: Write the failing test** (extend the existing `test_failure_compass_offers_recovery_for_scout`):

```python
def test_failure_compass_v6_signal_lost_ladder():
    from frontier_scout.tui3.app import _failure_compass
    msg = _failure_compass("scout", "claude CLI timed out after 180s")
    assert "✕" in msg or "x" in msg            # signal-lost mark
    assert "▱" in msg or "-" in msg            # unlit pip run
    assert "switch" in msg and "retry" in msg and "--demo" in msg   # keyed ladder
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the motif + ladder in `_failure_compass` (keep the existing recovery wording; prepend `✕` + a `seg_off` run; format the three steps as `key · action`). Route glyphs through `glyphs(...)`.
- [ ] **Step 4: Run — expect PASS** + the existing failure-compass tests.
- [ ] **Step 5: Commit** (`feat(tui3): sharper failed-scout signal-lost ladder`).

---

### Task 9: Finalize — degradation sweep, full suite, lint

**Files:** none new (verification + any `theme.tcss` height rule for `.scout-progress` if the spinner row needs `height: auto`).

- [ ] **Step 1: Degradation/breakpoint smoke (Pilot).** Boot `MissionControlApp(demo=True)`; for sizes `(40,12) (70,24) (100,40) (140,48)` (tiny→wide... use valid breakpoint sizes) and for `(unicode,color) ∈ {(T,T),(F,T),(T,F),(F,F)}`: render Scout (with verdicts → matrix crosshair/lock; `_scanning=True` → spinner) and a cap tab; assert no exception and (ascii) no stray `⠋`/`▰`/`⌜`/`▁` leak (`"⠋" not in txt`, etc.). Script modelled on the v5 mono/ascii smoke.
- [ ] **Step 2: Full tui3 suite.**

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/ -k "tui3 or matrix or spinner or kit" -q
```

Expected: all pass.

- [ ] **Step 3: Lint.** `/opt/miniconda3/bin/python -m ruff check frontier_scout/ tests/` → clean. (Black is not a CI gate here; match surrounding style; lines ≤120.)
- [ ] **Step 4: Confirm constraints:** no Tweaks panel ported; no new deps (`git diff main -- pyproject.toml requirements.txt` empty); diffs confined to `kit.py`/`widgets.py`/`state.py`/`data.py`/`scout_view.py`/`panes.py`/`app.py`/tests (+ maybe `theme.tcss`); `AGENTS.md`/`CLAUDE.md` untouched.
- [ ] **Step 5: Commit** any smoke test added (`test(tui3): v6 degradation/breakpoint smoke`). Then finish via `superpowers:finishing-a-development-branch` → PR (do NOT merge protected `main` without the user's relax→merge→restore gate).

---

## Self-review

**Spec coverage:** §1 spinner+sweep → Tasks 1 (frames), 3 (widget), 4 (scout), 5 (cap-scan) ✓ · §2 crosshair+lock → Tasks 1 (corners), 6 (crosshair), 7 (lock frame) ✓ · §3 failed-scout → Task 8 ✓ · §5 spark → Task 1 ✓ · motion decision → Task 2 ✓ · degradation/tests/finalize → Task 9 ✓. No gaps.

**Placeholders:** deterministic tasks (1–3) carry full code; markup tasks (4–8) give the exact file+function, the exact glyphs/tones, the README section, and the test assertion — the implementer reads the named current function + the prototype for the surrounding markup (the only honest way to edit an existing function). No "TBD"/"handle edge cases".

**Type/name consistency:** `ScanSpinner(label, *, width)`, `_frame`/`_head`/`_tick_frame`/`_tick_sweep`/`_repaint`, `spinner_frames(unicode)`, `SPIN_UNI`/`SPIN_ASCII`, `glyphs()["corner_tl"|…]`, `AppState.motion`, `app._cap_scanning`, `_scan_progress` — used consistently across tasks.
