# Mission Control v2 (tui3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the real Textual app (`frontier_scout/tui3/`) behave exactly like the prototype `Frontier Scout Mission Control v2.html` — fix the `r`-scan regression with a visible wired button, add full mouse↔keyboard parity, render the Scout Permission map, ship the repo switcher, and harden the documented anti-bugs.

**Architecture:** The current tui3 is already ~90% there — bindings, the worker bridge (`run_worker(thread=True)` → `WorkDone/WorkFailed` → `with_(cache=…)` → re-render-if-active), all gates (`ConfirmScreen`/`TypedConfirmScreen`), the capability caches, the empty-state copy, the funnel hero, and breakpoint reflow all exist and are tested. The gaps are: (1) **zero clickable targets** anywhere; (2) **no visible scan button** + no `r` compass hint on deps/guard; (3) Scout detail is **missing the Permission map** and carries a stray "Why it matters"/"Unknowns" not in the prototype; (4) **no repo switcher / `data.list_repos()`**; (5) first-paint size measurement can flash the "too small" floor. We add one reusable click primitive and route every click into the existing `action_*` methods — **one action, two triggers** — touching only `frontier_scout/tui3/`.

**Tech Stack:** Python 3.11+, Textual 8.2 (`App`, `ModalScreen`, `Static`, `events.Click`, `Pilot`), pytest. Run tests with `/opt/miniconda3/bin/python` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` (bare `python` is not on PATH in this env; 3 `test_implement.py` failures are pre-existing env-only and unrelated).

---

## Ground rules (carry into every task)

1. **Prototype is the source of truth** for layout, interactions, keybindings, copy, visual hierarchy. When prototype and Python disagree, change the Python.
2. **Scope: `frontier_scout/tui3/` only.** No `frontier_scout/<backend>.py`, no CLI changes. New tui3 files are allowed. Every action calls an existing `data.py`/backend function — invent **no** new backend API. (`data.list_repos()` is a *tui3* adapter over `scheduling.load_schedules()` — allowed.)
3. **One action, two triggers.** Every keypress and every click route to the *same* `action_*`/worker. Never duplicate action logic in a click handler.
4. **Nothing spends or hits the network on the render path.** Backend calls run only on a threaded worker, only after the relevant gate confirms.
5. **Every renderable goes through `app._paint(...)` (mono) and `glyphs(app.state.unicode)` (ascii).** `u`/`c` must re-render the whole tree.
6. **Never `remove_children()` + re-mount widgets with the same ids on a worker callback.** Refresh a list by repainting one id-tagged `Static` via `.update(markup)`. The single awaited pane swap in `_render_pane` (`app.py:174`) is the only safe teardown.
7. **Work tab-by-tab.** After each task, run its acceptance checks (the relevant §11 items, encoded as tests) before moving on.
8. **8 tabs, no Incident.** Tab order: Scout · Schedule · Receipts · Guard · Packs · Deps · Reports · Settings.

---

## Current-state reference (verified — do NOT rebuild these)

**`app.py` (`MissionControlApp`)**
- `BINDINGS` at `app.py:50-79`. Every spec key is bound **except `w`** (repo switcher) — Task 4 adds it.
- `action_refresh` `app.py:986`: scout→`run_scout`, guard/deps/settings→`_refresh_worker(tab)`. `_refresh_worker` `app.py:995` calls `data.guard`/`data.dependencies`/(`data.policy`+`data.repo_profile`+`data.doctor`). `on_work_done` `app.py:1041` sets `guard_cache` (1051), `deps_cache` (1055), `settings_cache` (1059) and re-renders only if that tab is active. **This worker path already works and is tested** (`tests/test_tui3_r_refresh.py`).
- `_goto` `app.py:317` auto-loads guard/deps/settings on first open when cache is `None` (322-327); `r` re-runs afterward (unconditional).
- `_render` `app.py:130` (breakpoint reflow via `breakpoint_for`), `_render_pane` `app.py:174` (`await main.remove_children()` then mount — safe), `_paint` `app.py:194`, `_set` `app.py:201`, `_refresh_chrome` `app.py:182`, `_refresh_nav` `app.py:186`, `compose` `app.py:97-104` (`#mc-header`, `#mc-body`→`#mc-rail`/`#mc-tabstrip`/`#mc-main`/`#mc-floor`, `#mc-compass`).
- `_compass_text` `app.py:226`: contextual prepends for reports (241), packs (244), schedule (249) only — **no guard/deps, no `r` hint**.
- `_term_size` `app.py:111-118` reads `self.size` (floor `max(1,…)`); `_size_override` set in `on_resize` `app.py:120`. **First paint before any Resize can read a degenerate size → "tiny" floor.**
- Gates: implement `app.py:757`, evaluate `796`, lab `830`, live schedule run `416`, discover `678`, reconfigure `880` (all `ConfirmScreen`); clear_history `855` (`TypedConfirmScreen`, token `clear`). Confirm callback fires the worker; cancel/esc never does.
- `run_palette_action` `app.py:923` (dispatch `kind:val`); `action_palette` `app.py:918`.
- **No `on_click`, no `Button`, no mouse handler anywhere.**

**`panes.py`** — `build_pane` `panes.py:23`, `_BUILDERS` `panes.py:336`; `_S(app, markup)`=`Static(app._paint(markup))` `panes.py:28`; `_head` `panes.py:33`. Panes: `_schedule` 43, `_receipts` 83, `_guard` 106 (empty 116, reads `guard_cache`), `_packs` 135, `_deps` 158 (empty 168, reads `deps_cache`, 3-state None/`()`/rows), `_reports` 189, `_settings` 226 (provider 235-246 + security 250-263 always render; empty 268; danger row 321-326). No pane is clickable; no pane uses `id=`.

**`scout_view.py`** — `build_scout` 56; `_hero` 83 (funnel band; only when `bp.show_hero`); `_scanbar` 106 (`SCOPES=["all","ai-devtools","mcp","deps"]` line 44; `s` affordance 112); `_empty` 124; `_list` 140; `_detail` 166 (order today: ribbon 174 → fit/risk/source 177 → dep upgrade 182 → **What it is** 188 → **Why it matters** 189 → why-it-fits 190 → Concerns/✓clean 195/201 → **Unknowns** 203 → Next safe step 207 → Ask 210 → source 211); `_ask` 221 (`data.ask_offline`, offline-only); `_ASKS` 45; `_section` 52.

**`state.py`** — `AppState` 125 (`frozen`): fields incl. `tab, repo, repo_name, languages, provider, verdicts, funnel, sel, sched_sel, scope, unicode, color, demo, unread, guard_cache, deps_cache, settings_cache`. `with_()` 146, `current` 149, `scoped_verdicts` 157, `move` 165. `Verdict` 34 (fields 36-54, `from_payload` 68) — **no capabilities field yet**. `Concern` 27. `Funnel` 101 (`from_payload` 111; no `coverage` field).

**`data.py`** — all wrappers present (`initial_state` 69, `run_scan` 97, `guard` 389, `dependencies` 469, `packs` 408, `packs_refresh` 426, `schedules` 194, `schedule_*` 228-341, `receipts` 371, `providers` 128, `policy` 492, `doctor` 501, `repo_profile` 514, `report_render` 706, `report_open` 742, `ask_offline` 604, `dossier` 536, `implement` 569, `evaluate` 622, `lab` 658, `clear_history` 689, `crontab_line` 212, `notifications_*`). `_verdicts_from_payload` 57 builds Verdicts from `payload["verdicts"]`. **`list_repos` does NOT exist.** **The payload's verdict dicts carry `permission_manifest` → `capabilities`** (`scout.py:144`; `mcp_audit.classify_mcp_capabilities`, keys `filesystem/network/shell/secrets[/unknown]`, statuses `likely/unlikely` etc.).

**`overlays.py`** — `_Modal` 56 (esc/q dismiss; content painted in `compose`/`body`, **visible on frame 1**, no opacity/transition in `theme.tcss`). `ConfirmScreen` 89 (`action_confirm` 138 pops then calls callback), `TypedConfirmScreen` 144 (`on_input_submitted` 187 fires only on token match), `CommandPalette` 463 (single `#cp-results` Static repainted via `.update()` 538), `NotificationsScreen` 358 (single `#notif-list` Static 392/406). **No `on_click` anywhere.**

**Tests** (Pilot pattern: `MissionControlApp(repo=…, demo=True)`, `async with app.run_test(size=(W,H)) as pilot`, `await pilot.press(k)` / `pilot.pause()` / `asyncio.sleep`, then assert `app.state`/`app.screen`; stub backends by swapping `frontier_scout.tui3.data` attrs): `test_tui3.py` (kit/state/boot/reflow/overlays), `test_tui3_scout_run.py` (`s`/`r` no-crash), `test_tui3_actions.py` (gates), `test_tui3_r_refresh.py` (`r` scans deps/guard/settings — **currently untracked; commit it in Task 1**).

---

## File structure (what each task creates/modifies)

| File | Responsibility | Tasks |
|---|---|---|
| `frontier_scout/tui3/widgets.py` *(new)* | `ClickStatic` (Static + `on_click` callback) and `LineClickStatic` (Static + per-line click map). The single click primitive everything routes through. | 1 |
| `frontier_scout/tui3/app.py` | compass `r` hints; click routing for tabs/header; `w` binding + repo-switcher action; `_term_size` first-paint fallback; palette "Switch repo" command. | 1,2,4,5 |
| `frontier_scout/tui3/panes.py` | clickable scan buttons (deps/guard/settings); clickable schedule rows + run/toggle/del/edit; clickable provider rows; settings copy. | 1,2 |
| `frontier_scout/tui3/scout_view.py` | clickable scope chips, verdict rows, scan affordance, action bar; detail reorder + Permission map. | 2,3 |
| `frontier_scout/tui3/state.py` | `Verdict.capabilities` field + `from_payload` projection. | 3 |
| `frontier_scout/tui3/data.py` | `list_repos()` adapter (over `scheduling.load_schedules()` + current repo). | 4 |
| `frontier_scout/tui3/overlays.py` | `RepoSwitcherScreen` (id-tagged Static list; j/k+⏎; mouse). | 4 |
| `tests/test_tui3_r_refresh.py` | extend with the click-path assertion. | 1 |
| `tests/test_tui3_mouse_parity.py` *(new)* | click parity for tabs/rows/chips/buttons/schedule/provider/gates. | 1,2 |
| `tests/test_tui3_detail_permission.py` *(new)* | detail order + Permission map render + tones. | 3 |
| `tests/test_tui3_repo_switcher.py` *(new)* | `w`/click/palette open, j/k+⏎ select, re-scout. | 4 |
| `tests/test_tui3_robustness.py` *(new)* | first-paint never floors; modal visible frame 1; no DuplicateIds after churn; u/c re-render. | 5 |

---

## Task 0: Branch + baseline

**Files:** none (git only).

- [ ] **Step 1: Branch from main**
```bash
cd /Users/ajaysurya/Desktop/ai-telemetry-public
git fetch origin --quiet && git checkout -b feat/tui3-mission-control-v2 origin/main
```

- [ ] **Step 2: Capture a green baseline (and commit the untracked regression test)**
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3.py tests/test_tui3_scout_run.py tests/test_tui3_actions.py tests/test_tui3_r_refresh.py
```
Expected: all pass. If `tests/test_tui3_r_refresh.py` is untracked (`git status`), it is the existing Bug #1 regression test — keep it; it is committed in Task 1.

- [ ] **Step 3: Open the prototype for reference** (manual, keep it open while building):
`frontier-scout-mission-control/Frontier Scout Mission Control v2.html`.

---

## Task 1: The `r` regression — visible, wired scan buttons (TOP PRIORITY) + the click primitive

**Why first:** the `r`→worker→cache→render path already works; the prototype additionally shows a **clickable** scan button that calls the *same* path, plus an `r scan`/`r re-run` compass hint. We introduce the one reusable click primitive here (everything else reuses it) and apply it to Deps/Guard/Settings.

**Files:**
- Create: `frontier_scout/tui3/widgets.py`
- Modify: `frontier_scout/tui3/panes.py` (`_guard` ~106, `_deps` ~158, `_settings` ~226)
- Modify: `frontier_scout/tui3/app.py` (`_compass_text` ~226)
- Test: `tests/test_tui3_r_refresh.py` (extend), `tests/test_tui3_mouse_parity.py` (new)

- [ ] **Step 1: Write the click primitive**

Create `frontier_scout/tui3/widgets.py`:
```python
"""Click primitives for tui3.

`ClickStatic` is the single mouse target the whole UI routes through: a painted
`Static` that, on click, calls one zero-arg callback. The callback dispatches to
an existing `action_*`/worker method — never duplicate action logic here
(handoff §5: "one action, two triggers").

`LineClickStatic` is for multi-line composite Statics (tab rail/strip, verdict
list): it maps the clicked row (`event.y`) to a callback via a line→callback map.
"""

from __future__ import annotations

from typing import Callable

from textual import events
from textual.widgets import Static

OnClick = Callable[[], None]


class ClickStatic(Static):
    """A painted Static that invokes `on_click_cb` when clicked."""

    def __init__(self, renderable: str, on_click_cb: OnClick, **kw) -> None:
        super().__init__(renderable, **kw)
        self._on_click_cb = on_click_cb

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self._on_click_cb()


class LineClickStatic(Static):
    """A multi-line Static that maps the clicked line index to a callback.

    `line_map` is a dict {line_index: callback}. `dbl_map` (optional) maps a line
    to a double-click callback (e.g. verdict row → dossier).
    """

    def __init__(
        self,
        renderable: str,
        line_map: dict[int, OnClick],
        dbl_map: dict[int, OnClick] | None = None,
        **kw,
    ) -> None:
        super().__init__(renderable, **kw)
        self._line_map = line_map
        self._dbl_map = dbl_map or {}

    def on_click(self, event: events.Click) -> None:
        cb = self._line_map.get(event.y)
        if cb is None:
            return
        event.stop()
        if event.chain == 2 and event.y in self._dbl_map:
            self._dbl_map[event.y]()
        else:
            cb()
```

- [ ] **Step 2: Write the failing click-path test** in `tests/test_tui3_mouse_parity.py` (new):
```python
"""Mouse↔keyboard parity: clicking a target runs the SAME action a key does."""
import asyncio

from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.widgets import ClickStatic


def _run(coro):
    return asyncio.run(coro)


def test_clicking_deps_scan_button_runs_scan():
    async def go():
        app = MissionControlApp(repo=".", demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.press("6")          # deps tab
            await pilot.pause()
            app.state = app.state.with_(deps_cache=None)
            await app._render_pane()
            await pilot.pause()
            btn = next(
                w for w in app.query(ClickStatic)
                if getattr(w, "id", "") == "cap-scan-deps"
            )
            btn._on_click_cb()              # exactly what a real click invokes
            for _ in range(40):
                await asyncio.sleep(0.05)
                if app.state.deps_cache is not None:
                    break
            assert app.state.deps_cache is not None, "click did not run the deps scan"
    _run(go())
```
- [ ] **Step 3: Run it — expect FAIL** (`no ClickStatic with id cap-scan-deps`):
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3_mouse_parity.py::test_clicking_deps_scan_button_runs_scan
```

- [ ] **Step 4: Add the scan buttons to the three panes.** In `panes.py`, import the primitive at top: `from frontier_scout.tui3.widgets import ClickStatic`. Add a small helper near `_S` (~`panes.py:28`):
```python
def _scan_btn(app, tab: str, label: str) -> ClickStatic:
    """Primary scan/run button that calls the SAME path the `r` key calls."""
    markup = f"[#0b1117 on #24d6a8 b] r [/] [#24d6a8]{label}[/]"
    return ClickStatic(app._paint(markup), lambda: app.action_refresh(),
                       id=f"cap-scan-{tab}", classes="cap-scan-btn")
```
Note: `app.action_refresh` is the existing async action; calling it schedules the same worker the key does (Textual actions are sync-callable; `action_refresh` is `async` but invoking it returns a coroutine — wrap so it runs). Use the existing dispatcher instead: add a tiny sync shim in `app.py` (Step 5) `def refresh_tab(self): self.run_worker(self.action_refresh())` — OR simpler, call the underlying sync path directly:
```python
    return ClickStatic(app._paint(markup),
                       lambda: app._refresh_worker(tab) if tab != "scout"
                       else app.run_scout(dry_run=app.state.demo),
                       id=f"cap-scan-{tab}", classes="cap-scan-btn")
```
This routes the click into the identical `_refresh_worker(tab)` the `r` key reaches via `action_refresh` (`app.py:992-993`) — one worker, two triggers.

Then mount the button in each pane:
- `_deps` (`panes.py:158`): in the `None` branch (after the empty-state line at ~168) add `box.compose_add_child(_scan_btn(app, "deps", "scan dependencies"))`. In the loaded branch (PaneHead area near `_head`) add a re-scan button `_scan_btn(app, "deps", "re-scan")` (label per prototype `fs2-tabs.jsx:179`).
- `_guard` (`panes.py:106`): in the `None` branch (after empty-state line ~116) add `_scan_btn(app, "guard", "run guard")`; loaded branch add `_scan_btn(app, "guard", "re-run")`.
- `_settings` (`panes.py:226`): in the `None`/policy-not-loaded branch (after line ~268) add `_scan_btn(app, "settings", "load diagnostics")`. **Change the empty-state copy at `panes.py:268`** to the prototype's exact line: `"\n[#6e8aa1]Press [#24d6a8 b]r[/] to load policy and doctor.[/]"` (prototype `fs2-tabs.jsx:298`).

Keep every existing "Press `r`…" empty-state string (Bug #2 — the copy must survive the pre-load frame).

- [ ] **Step 5: Add the `r` compass hints** for deps/guard. In `app.py` `_compass_text` (~`app.py:240`, alongside the reports/packs/schedule branches), add:
```python
        elif self.state.tab == "deps" and bp != "micro":
            hints = [("r", "scan"), *hints]
        elif self.state.tab == "guard" and bp != "micro":
            hints = [("r", "re-run"), *hints]
```
(Verbatim from prototype `fs2-app.jsx:147-148`.)

- [ ] **Step 6: Run the click test — expect PASS**, then the existing regression test:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3_mouse_parity.py tests/test_tui3_r_refresh.py
```
- [ ] **Step 7: Extend `tests/test_tui3_r_refresh.py`** — add a guard + settings click variant mirroring Step 2 (click `#cap-scan-guard` → `guard_cache` populated; click `#cap-scan-settings` → `settings_cache` populated). Run again; expect PASS.

- [ ] **Step 8: Commit**
```bash
git add frontier_scout/tui3/widgets.py frontier_scout/tui3/panes.py frontier_scout/tui3/app.py tests/test_tui3_mouse_parity.py tests/test_tui3_r_refresh.py
git commit -m "fix(tui3): wire visible scan buttons on deps/guard/settings + r compass hints

The r→worker→cache→render path worked; the prototype also exposes a clickable
scan button and an r scan/re-run compass hint. Add ClickStatic primitive and
route both the button and r through the same _refresh_worker. Keep the empty-state
copy. (handoff §6 Bug#1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Acceptance (§11.1):** fresh Deps tab → `r` → rows; same via the visible button. Repeat Guard, Settings.

---

## Task 2: Full mouse↔keyboard parity (§5)

**Files:** Modify `scout_view.py` (scope chips, verdict list, scan affordance, action bar), `panes.py` (schedule rows + run/toggle/del/edit, provider rows), `app.py` (tab rail/strip clicks, header bell + repo). Test: `tests/test_tui3_mouse_parity.py` (extend).

Pattern for every surface: **a click handler that calls the identical `action_*`/method the key calls.** Discrete targets → `ClickStatic`. Multi-line composites (tab rail/strip, verdict list) → `LineClickStatic` with a `{line: callback}` map.

- [ ] **Step 1 (tabs):** In `app.py`, the rail (`#mc-rail`) and tabstrip (`#mc-tabstrip`) are single Statics built by `_rail_text`/`_tabstrip_text`. Replace those two `Static` widgets in `compose` (`app.py:99-101`) with `LineClickStatic` instances, and when updating them in `_render` (`app.py:167`/`169`) also set `.${_line_map}` — simplest: give `LineClickStatic` a `set_line_map(d)` method and, in the rail/strip renderers, return `(markup, {line_index: lambda t=tab_id: self.call_later(self._goto, t)})`. Each visible tab line → `_goto(tab_id)` (the same method `action_goto_*` uses).

  Failing test first:
```python
def test_clicking_rail_tab_switches_tab():
    async def go():
        app = MissionControlApp(repo=".", demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            from frontier_scout.tui3.widgets import LineClickStatic
            rail = app.query_one("#mc-rail", LineClickStatic)
            # line for "guard" (4th tab, 0-based index 3) → _goto("guard")
            cb = rail._line_map[3]
            cb()
            await pilot.pause()
            assert app.state.tab == "guard"
    _run(go())
```

- [ ] **Step 2 (verdict list):** In `scout_view.py` `_list` (`scout_view.py:140`), build the rows into one `LineClickStatic` (id `scout-list`) instead of N child Statics. `line_map[row_i] = lambda i=i: app._select(i)`; `dbl_map[row_i] = lambda i=i: app.call_later(app.action_dossier)`. Add `app._select(i)` in `app.py`:
```python
def _select(self, i: int) -> None:
    self.state = self.state.with_(sel=i)
    self.call_later(self._render_pane)
```
(Single click selects — same end state as `j/k`; double-click opens the dossier — same as `D`.)

- [ ] **Step 3 (scope chips):** In `_scanbar` (`scout_view.py:106`) render each chip as a `ClickStatic` (or one `LineClickStatic` hit-tested by x is harder — prefer discrete `ClickStatic` per chip in a `Horizontal`). Each chip → `app._set_scope(scope)`:
```python
def _set_scope(self, scope: str) -> None:
    self.state = self.state.with_(scope=scope, sel=0)
    self.call_later(self._render_pane)
```
The `s` affordance becomes a `ClickStatic("s scout", lambda: app.run_scout(dry_run=app.state.demo), id="scout-scan")`.

- [ ] **Step 4 (Scout action bar):** Add an Actions row to `_detail` (prototype `fs2-scout.jsx:225`) as discrete `ClickStatic`s, each calling the existing action: `L`→`action_lab`, `e`→`action_evaluate`, `i`→`action_implement`, `D`→`action_dossier`, `o`→`action_open_target`. Wrap async actions with `lambda: app.call_later(app.action_lab)` etc. (gates still fire — these call the gated actions unchanged).

- [ ] **Step 5 (schedule rows):** In `panes.py` `_schedule` (`panes.py:43`), build rows into a `LineClickStatic` (id `sched-list`); `line_map[row] = lambda i=i: app._select_sched(i)`. Add per-row action chips (`⏎ run`, `t`, `Del`, `E`) as `ClickStatic`s calling `action_primary`/`action_toggle_schedule`/`action_remove_schedule`/`action_edit_schedule`. Add `app._select_sched(i)` mirroring `_select` but writing `sched_sel`.

- [ ] **Step 6 (provider rows + settings):** Provider rows and the danger row stay informational, but make the danger actions clickable: `R`→`action_reconfigure`, `X`→`action_clear_history`, wrapped to `call_later`. (Keep them labelled with their keys — the prototype keeps the keybinding affordance.)

- [ ] **Step 7 (header bell + repo):** In `app.py` `compose`, the header is one Static (`#mc-header`). Split the clickable zones: make the bell glyph and the repo name `ClickStatic`s (or convert `#mc-header` to a `LineClickStatic` line 0 with an x-hit-test is brittle — instead mount two small `ClickStatic`s in the header row): bell → `action_notifications`; repo → `action_switch_repo` (added in Task 4; for now wire to a no-op `lambda: None` and connect in Task 4).

- [ ] **Step 8: Tests** — extend `tests/test_tui3_mouse_parity.py` with one test per surface (tab click, verdict select click + double-click→ResultScreen, scope chip click changes `state.scope`, action-bar `e` click opens `ConfirmScreen`, schedule row click sets `sched_sel`). Run:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3_mouse_parity.py tests/test_tui3.py
```
Expected: PASS (and no DuplicateIds in output — every list is one id-tagged `LineClickStatic`).

- [ ] **Step 9: Commit**
```bash
git add frontier_scout/tui3/scout_view.py frontier_scout/tui3/panes.py frontier_scout/tui3/app.py tests/test_tui3_mouse_parity.py
git commit -m "feat(tui3): full mouse↔keyboard parity — every key has a click that hits the same action (handoff §5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Acceptance (§11.2):** keyboard untouched, click through every tab, select a verdict, change scope, run a scan, open the palette, toggle a schedule, open & cancel a gate. Nothing keyboard-only.

---

## Task 3: Scout detail → prototype (reorder + Permission map)

**Files:** Modify `state.py` (`Verdict`), `data.py` is unchanged (projection lives in `Verdict.from_payload`), `scout_view.py` (`_detail`). Test: `tests/test_tui3_detail_permission.py` (new).

- [ ] **Step 1: Add `capabilities` to `Verdict`.** In `state.py`, add a field on `Verdict` (after `unknowns`, ~`state.py:47`):
```python
    capabilities: tuple[tuple[str, str], ...] = ()  # (key, status) e.g. ("shell","likely")
```
In `Verdict.from_payload` (`state.py:68`), project it from the payload's permission manifest:
```python
        manifest = d.get("permission_manifest") or {}
        caps = manifest.get("capabilities") or {}
        capabilities = tuple((str(k), str(v)) for k, v in caps.items()) if isinstance(caps, dict) else ()
```
and pass `capabilities=capabilities` into the constructor. (Source: `scout.py:144` puts `permission_manifest` on each verdict; `mcp_audit` fills `capabilities`. Deps carry none → empty tuple → no map, exactly like the prototype.)

- [ ] **Step 2: Failing test** in `tests/test_tui3_detail_permission.py`:
```python
import asyncio
from frontier_scout.tui3.state import Verdict

def test_verdict_projects_capabilities_from_manifest():
    v = Verdict.from_payload({
        "tool_name": "x/y", "verdict": "trial", "fit": "high", "risk": "medium",
        "category": "MCP Server", "source_url": "https://github.com/x/y",
        "what": "w", "why_it_matters": "m", "fit_reasons": ["a"],
        "concerns": [], "next_safe_step": "n",
        "permission_manifest": {"capabilities": {"shell": "likely", "network": "possible"}},
    })
    assert dict(v.capabilities) == {"shell": "likely", "network": "possible"}

def test_dep_verdict_has_no_capabilities():
    v = Verdict.from_payload({"tool_name": "pkg", "verdict": "adopt", "fit": "high",
        "risk": "low", "category": "dep", "source_url": "", "what": "", "why_it_matters": "",
        "fit_reasons": [], "concerns": [], "next_safe_step": "", "from_version": "1", "to_version": "2"},
        kind="dep")
    assert v.capabilities == ()
```
Run → expect FAIL (no field), then PASS after Step 1.

- [ ] **Step 3: Reorder `_detail` + render the Permission map.** In `scout_view.py` `_detail` (`scout_view.py:166`):
  - **Remove** the standalone "Why it matters" section (`scout_view.py:189`) and the inline "Unknowns" section (`scout_view.py:203-206`) — neither is in the prototype's inline detail (`fs2-scout.jsx`; unknowns live only in the Dossier).
  - **Keep** the order: ribbon → fit/risk/source → (dep upgrade) → **What it is** (`v.what`) → why-it-fits (`"why it fits your repo"`, or dep `"why this upgrade works for you"`) → Concerns/`"✓ clean — no concerns flagged"`.
  - **Insert the Permission map after Concerns**, before Next safe step, only when `v.capabilities`:
```python
        if v.capabilities:
            rows = []
            for key, status in v.capabilities:
                danger = status in ("certain", "likely") and key in ("shell", "secrets", "network")
                med = status == "possible"
                tone = "#ff6b6b" if danger else ("#e3c26f" if med else "#6e8aa1")
                rows.append(f"[#6e8aa1]{key}[/] [{tone}]{status}[/]")
            box.compose_add_child(_section(app, "Permission map", "  ·  ".join(rows)))
```
  (Tone logic + header verbatim from prototype `fs2-scout.jsx:205-216`.)
  - Then Next safe step → **Actions row** (from Task 2) → Ask → source link (unchanged).

- [ ] **Step 4: Detail-order test** — mount a tool verdict with capabilities, assert the rendered detail text contains `"Permission map"` and `"shell"` and does NOT contain `"Why it matters"`; mount a dep verdict, assert no `"Permission map"`. Use `_pane_text(app)` (copy the helper from `test_tui3_r_refresh.py:51`). Run:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3_detail_permission.py
```

- [ ] **Step 5: Commit**
```bash
git add frontier_scout/tui3/state.py frontier_scout/tui3/scout_view.py tests/test_tui3_detail_permission.py
git commit -m "feat(tui3): Scout detail matches prototype — add Permission map, drop stray Why-it-matters/Unknowns (handoff §4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Acceptance:** a tool verdict shows ribbon→fit/risk→What it is→why it fits→Concerns→Permission map→Next safe step→Actions→Ask→source; a dep verdict shows the upgrade line and no Permission map.

---

## Task 4: Repo switcher (§9)

**Files:** Modify `data.py` (`list_repos`), `overlays.py` (`RepoSwitcherScreen`), `app.py` (`w` binding, `action_switch_repo`, palette command, header repo click → this action). Test: `tests/test_tui3_repo_switcher.py` (new).

- [ ] **Step 1: `data.list_repos()` adapter** (tui3-only, no new backend API). In `data.py`:
```python
def list_repos(current: str | None = None) -> list[dict[str, Any]]:
    """Known repos for the switcher: schedule repos + the current repo, deduped.

    Source of truth is scheduling.load_schedules() (each Schedule.repo); we fold in
    `current` so there is always at least one entry. (No backend list_repos exists;
    this is the only no-new-API path — handoff §9.)
    """
    seen: dict[str, dict[str, Any]] = {}
    if current:
        p = str(Path(current).resolve())
        seen[p] = {"name": _repo_name(p), "path": p}
    try:
        from frontier_scout import scheduling
        for s in scheduling.load_schedules():
            p = str(Path(s.repo).resolve())
            seen.setdefault(p, {"name": _repo_name(p), "path": p})
    except Exception:  # noqa: BLE001 — switcher must never crash
        pass
    return list(seen.values())
```

- [ ] **Step 2: `RepoSwitcherScreen`** in `overlays.py` — modeled on `CommandPalette` (single id-tagged `#repo-list` Static repainted via `.update()`; `j/k`/arrows in `on_key`; `Enter` selects; mouse via a `LineClickStatic`). Verbatim copy:
  - title: `Switch repo`
  - note: `Point Mission Control at another repo. Re-scouts on switch — verdicts are always relative to the repo you're in.`
  - footer preview: `◆ this surface previews the v1.6 multi-repo workspace — see the handoff for the backend it needs.` then dim `j/k move · ⏎ switch · esc cancel`
  - On select: `self.app.switch_repo(path)`; cursor starts on the current repo.

```python
class RepoSwitcherScreen(_Modal):
    def __init__(self, repos: list[dict], current: str) -> None:
        super().__init__()
        self._repos = repos
        self._sel = next((i for i, r in enumerate(repos) if r["path"] == current), 0)

    def body(self):
        from frontier_scout.tui3.widgets import LineClickStatic
        yield self._static("[#24d6a8 b]Switch repo[/]")
        yield self._static("[#6e8aa1]Point Mission Control at another repo. Re-scouts on "
                           "switch — verdicts are always relative to the repo you're in.[/]")
        line_map = {i + 1: (lambda p=r["path"]: self._choose(p)) for i, r in enumerate(self._repos)}
        self._list = LineClickStatic(self._list_markup(), line_map, id="repo-list")
        yield self._list
        yield self._static("[#7aa6ff]◆ this surface previews the v1.6 multi-repo "
                           "workspace — see the handoff for the backend it needs.[/]\n"
                           "[#6e8aa1]j/k move · ⏎ switch · esc cancel[/]")

    def _list_markup(self) -> str:
        lines = []
        for i, r in enumerate(self._repos):
            mark = "[#24d6a8 b]▸ [/]" if i == self._sel else "  "
            lines.append(f"{mark}[#d9f7ff]{r['name']}[/] [#6e8aa1]{r['path']}[/]")
        return "\n".join(lines) or "[#6e8aa1]no known repos[/]"

    def on_key(self, event) -> None:
        if event.key in ("j", "down"):
            self._sel = min(len(self._repos) - 1, self._sel + 1)
            self.query_one("#repo-list", expect_type=None).update(self.app._paint(self._list_markup()))
            event.stop()
        elif event.key in ("k", "up"):
            self._sel = max(0, self._sel - 1)
            self.query_one("#repo-list", expect_type=None).update(self.app._paint(self._list_markup()))
            event.stop()
        elif event.key == "enter" and self._repos:
            self._choose(self._repos[self._sel]["path"])
            event.stop()

    def _choose(self, path: str) -> None:
        self.app.pop_screen()
        self.app.switch_repo(path)
```

- [ ] **Step 3: `app.py` wiring.** Add binding `Binding("w", "switch_repo", "switch repo", show=False)` to `BINDINGS` (~`app.py:79`). Add:
```python
def action_switch_repo(self) -> None:
    from frontier_scout.tui3.overlays import RepoSwitcherScreen
    repos = data.list_repos(self.state.repo)
    self.push_screen(RepoSwitcherScreen(repos, self.state.repo))

def switch_repo(self, path: str) -> None:
    # Re-init state for the new repo, preserving UI prefs, then re-scout.
    fresh = data.initial_state(Path(path), demo=self.state.demo)
    self.state = fresh.with_(
        tab=self.state.tab, scope="all", sel=0,
        color=self.state.color, unicode=self.state.unicode,
    )
    self._refresh_nav()
    self.call_later(self._render)
    self.run_scout(dry_run=self.state.demo)
    self._toast(f"pointed at {self.state.repo_name} · re-scouting")
```
(If `_toast` does not exist, append a compass note instead — check `app.py` for an existing toast/notice helper; the prototype toasts `pointed at {name} · re-scouting`.) Add the palette command to `COMMANDS` in `overlays.py` (`("go", "Switch repo", "go:repo", "w")`) and a `go:repo` branch in `run_palette_action` (`app.py:923`) → `call_later(self.action_switch_repo)`. Wire the header repo `ClickStatic` (Task 2 Step 7) → `action_switch_repo`.

- [ ] **Step 4: Tests** in `tests/test_tui3_repo_switcher.py`: (a) `data.list_repos(".")` returns ≥1 entry incl. the current repo; (b) pressing `w` pushes `RepoSwitcherScreen`; (c) `j` then `enter` calls `switch_repo` (monkeypatch `app.switch_repo` to record) ; (d) `switch_repo(path)` triggers a scout (`app._scanning` toggles / verdicts change) — stub `data.initial_state` + `data.run_scan`. Run:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3_repo_switcher.py
```

- [ ] **Step 5: Commit**
```bash
git add frontier_scout/tui3/data.py frontier_scout/tui3/overlays.py frontier_scout/tui3/app.py tests/test_tui3_repo_switcher.py
git commit -m "feat(tui3): repo switcher — w/click/palette → modal list (j/k+⏎) → re-init + re-scout (handoff §9)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Acceptance:** `w` (and the header repo click, and palette "Switch repo") opens the list; `j/k`+`⏎` switches; verdicts/funnel/profile change and a scout runs.

---

## Task 5: Robustness & anti-bugs (§6 #4, measurement, #3, #6, §10)

**Files:** Modify `app.py` (`_term_size`). Test: `tests/test_tui3_robustness.py` (new). Bugs #4 (modal visible) and id-tagged repaint are *verification* items (already correct — don't regress).

- [ ] **Step 1: First-paint measurement fallback.** In `app.py` `_term_size` (`app.py:111-118`), never let an un-laid-out first frame collapse to the "tiny" floor: fall back to the driver/console size, and only floor when the *real* terminal is genuinely small.
```python
@property
def _term_size(self) -> tuple[int, int]:
    if self._size_override is not None:
        return self._size_override
    sz = self.size
    w, h = sz.width, sz.height
    if w <= 1 or h <= 1:                      # not laid out yet (first paint)
        try:
            cs = self.console.size              # real terminal size from the driver
            w, h = cs.width, cs.height
        except Exception:                       # noqa: BLE001
            w, h = 80, 24                       # safe viewport default, never the floor
    return max(1, w), max(1, h)
```

- [ ] **Step 2: Failing test** (first paint must not floor on a normal terminal):
```python
def test_first_paint_does_not_floor_on_normal_terminal():
    async def go():
        app = MissionControlApp(repo=".", demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app._bp_name != "tiny", "first paint collapsed to the too-small floor"
    _run(go())
```

- [ ] **Step 3: No-DuplicateIds churn test** — refresh deps 5×, open/close palette 5×, switch tabs rapidly; assert no exception and `app.query("#mc-main")` has children. (DuplicateIds surfaces as a raised exception in `run_test`.)
```python
def test_no_duplicate_ids_after_churn():
    async def go():
        app = MissionControlApp(repo=".", demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            for _ in range(5):
                await pilot.press("6"); await pilot.press("r"); await pilot.pause()
                await pilot.press("p"); await pilot.press("escape"); await pilot.pause()
                await pilot.press("1"); await pilot.press("4"); await pilot.pause()
            assert app.query_one("#mc-main")
    _run(go())
```

- [ ] **Step 4: u/c re-render test** — flip `u` and `c`, assert `app.state.unicode`/`app.state.color` toggled and panes still build (`#mc-main` has children). Confirm every new `ClickStatic`/`LineClickStatic` is painted via `app._paint(...)` and any glyphs via `glyphs(app.state.unicode)` (grep the diffs).

- [ ] **Step 5: Reflow-to-floor test** — `await pilot.resize_terminal(w, h)` across `(160,50)`,`(110,34)`,`(80,24)`,`(56,20)`,`(34,10)` and back; assert `app._bp_name` changes and never raises. Run all:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3_robustness.py
```

- [ ] **Step 6: Verify (don't fix) Bug #4** — confirm `theme.tcss` has no `opacity`/`transition`/`animation` on modal containers and `RepoSwitcherScreen` paints content in `compose`/`body` (visible frame 1). Add an assertion: pushing `RepoSwitcherScreen` then `pilot.pause()` → `_pane_text`/screen query shows "Switch repo".

- [ ] **Step 7: Commit**
```bash
git add frontier_scout/tui3/app.py tests/test_tui3_robustness.py
git commit -m "fix(tui3): robust first-paint sizing (never flash the too-small floor) + anti-bug regression tests (#3/#4/#6/§10)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Full §11 acceptance checklist

**Files:** none (verification + any fixes the checklist surfaces).

- [ ] **Step 1: Run the whole tui3 suite + ruff**
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q tests/test_tui3.py tests/test_tui3_scout_run.py tests/test_tui3_actions.py tests/test_tui3_r_refresh.py tests/test_tui3_mouse_parity.py tests/test_tui3_detail_permission.py tests/test_tui3_repo_switcher.py tests/test_tui3_robustness.py
/opt/miniconda3/bin/python -m ruff check frontier_scout/tui3
```
Expected: all pass; ruff clean.

- [ ] **Step 2: Manual smoke at the breakpoints** (real terminal): `stty size`, then `frontier-scout --demo` at ~160×50, 110×34, 80×24, 56×20, 34×10. Confirm: `r` scans on Deps/Guard/Settings (key + button); click every tab + a verdict + a scope chip + open/cancel a gate; `u`/`c` flip everywhere; hero appears/disappears; floor only at 34×10.

- [ ] **Step 3: Tick the §11 checklist explicitly** (record pass/fail for each): (1) `r` works on Deps/Guard/Settings via key & button; (2) full mouse parity; (3) gates fire & cancel is inert; (4) no DuplicateIds after churn; (5) `u`/`c` re-render; (6) reflow to floor & back; (7) offline `--demo` renders all 8 tabs and `a` answers offline with no spend; (8) exactly 8 tabs, no Incident.

- [ ] **Step 4: Finish the branch** — Announce: *"I'm using the finishing-a-development-branch skill to complete this work."* Verify tests pass, then present merge/PR options.

---

## Self-Review (completed during planning)

- **Spec coverage:** §3 bindings (Task 4 adds `w`; rest verified present) · §4 per-tab (Tasks 1–3) · §5 mouse parity (Tasks 1–2) · §6 Bug#1 (Task 1), Bug#2 (Task 1 keeps copy + cache-gated auto-load already correct), Bug#3 (Tasks 2/5 use id-tagged `LineClickStatic`), Bug#4 (Task 5 verify), Bug#5 (workers only — unchanged), Bug#6 (Tasks route through `_paint`/`glyphs`; Task 5 verifies) · §7 gates (unchanged; Task 2 calls them) · §8 worker bridge (unchanged) · §9 repo switcher (Task 4) · §10 reflow (Task 5) · §11 (Task 6) · §12 don't-change (palette/tokens, offline Ask, read-only policy untouched). Permission map data source confirmed real (`scout.py:144` `permission_manifest` → `capabilities`).
- **Placeholder scan:** novel mechanisms (`ClickStatic`/`LineClickStatic`, `Verdict.capabilities`, Permission map render, `data.list_repos`, `RepoSwitcherScreen`, `_term_size` fix, compass hints) have complete code; repetitive parity wiring lists each exact site + the one-line call.
- **Type consistency:** `Verdict.capabilities: tuple[tuple[str,str],...]`; click callbacks are zero-arg `OnClick`; `_select`/`_select_sched`/`_set_scope`/`switch_repo` are the named methods referenced throughout.
- **Open item to resolve in Task 4 Step 3:** confirm an existing toast/notice helper name in `app.py`; if absent, surface the "pointed at … · re-scouting" message via the compass line instead of inventing a toast widget.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-02-tui3-mission-control-v2.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration (REQUIRED SUB-SKILL: superpowers:subagent-driven-development).
2. **Inline Execution** — execute tasks in this session with checkpoints (REQUIRED SUB-SKILL: superpowers:executing-plans).

Which approach?
