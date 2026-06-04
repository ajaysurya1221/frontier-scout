# Mission Control v6 — cell-precision rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Make the v6 Mission Control instruments (Adoption Matrix, gauges, scan state) cell-precise and converge them character-for-character on `design_handoff_mission_control_v6/ascii_golden_frames.txt`, fixing the multi-cell ASCII-glyph drift (`(o)`=3, `->`=2). v6 features already shipped in 1.8.0; this hardens their rendering.

**Architecture:** Every glyph-art surface becomes a width-parameterized **pure function** `fn(width:int)->str` that asserts `len(strip(out))==width`. The Textual engine packs fixed/`fr` cells per the px→cell budget; pure functions guarantee widths. Convergence is automated via golden-frame text tests + width asserts + `pytest-textual-snapshot` at pinned sizes.

**Tech stack:** Python 3.11, Textual, Rich (`rich.cells.cell_len` for multi-cell width), pytest 8.4.2 + pytest-textual-snapshot.

**Golden targets** (from `ascii_golden_frames.txt`): matrix block = **59 cells** (gutter 4 · `|` · 3×[17-cell col · `|`]); gauge meter width **20** (`[`+20+`]`=22); sweep width as drawn. Snapshot sizes: wide **140×38**, mid **100×28**, narrow **72×20** (→ breakpoint_for wide/mid/narrow).

**Key invariants:** every glyph via `glyphs()`/`_ASCIIFY`; degrade color/mono/unicode/ascii/light with IDENTICAL widths; motion only in spinner/sweep (pause on `not state.motion`); mouse+key parity via Click primitives; do NOT port the Tweaks panel; narrow diffs; AGENTS.md/CLAUDE.md untouched.

Tests: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest …` (snapshot tests add `-p pytest_textual_snapshot -p syrupy`).

---

### Task 1: kit.py cell-precision primitives
**Files:** Modify `frontier_scout/tui3/kit.py`; Test `tests/test_tui3_cells.py` (new).
- `cell_width(s)` → display width via `rich.cells.cell_len` (so `(o)`=3, `->`=2 measured correctly, not `len()`).
- `meter(value, width, *, unicode=True) -> str` → `cap_l + seg_on*filled + seg_off*(width-filled) + cap_r`; `len==width+2`; ascii `[####----------------]`.
- `sweep(width, head, *, motion=True, unicode=True) -> str` → `seg_off` track, bright `seg_on` at `head%width`, dim tail at head-1/head-2 (motion on); motion off = static mid-lit; plain `len==width`. (Markup added by caller.)
- Confirm existing: `SPIN_UNI/SPIN_ASCII`, `spinner_frames`, corners `⌜⌝⌞⌟`/`+`, `spark`.
- Tests: `len(meter(0.5,20))==22`; `meter(0.5,20,unicode=False)=="[##########----------]"`; `len(sweep(20,7))==20`; `cell_width("(o)")==3`; `glyphs(False)["spark"]==".:-=+*#%"`; `asciify("▁▂▃▄▅▆▇█")` all-ASCII.

### Task 2: Adoption Matrix pure function (the 59-cell box grid)
**Files:** Modify `frontier_scout/tui3/scout_view.py`; Test `tests/test_tui3_golden_matrix.py` (new).
- New pure fn `adoption_matrix_lines(cells, sel, sel_fit, sel_risk, total, *, unicode, ascii_plain=False) -> list[str]` emitting the golden grid: title row (`ADOPTION MATRIX … FIT x RISK . N` = 59), risk-label header row, `+---+` dividers (`─`/`┼` unicode, `+`/`-` ascii), 3 fit-rows (label in 4-cell gutter + `|`/`│` + 3×17-cell cells), crosshair (selected fit-row + risk-col labels toned+bold via `fit_tone`/`risk_tone`), corner lock on the selected cell (mint, red on low-fit/high-risk), readout line. Cell content pads to 17 cells using `cell_width` (so `(o)` selected dot accounts for 3).
- The plain (markup-stripped) ascii output MUST match `ascii_golden_frames.txt` "ADOPTION MATRIX" block char-for-char.
- Tests: parse the golden block from the handoff file; assert `adoption_matrix_lines(..., ascii_plain=True)` equals it line-for-line; `all(len(r)==59 for r in plain_lines)`.

### Task 3: Scan state — spinner + sweep + staged checklist
**Files:** Modify `frontier_scout/tui3/scout_view.py` (+ `widgets.py` `ScanSpinner`); Test `tests/test_tui3_golden_scan.py` (new).
- ScanProgress: line 1 = spinner frame + ` scanning ` + `sweep(width, head)`; then the 5-stage checklist `read tree / parse symbols / judge fit / score risk / rank` with markers done=`check`(✓/v), active=`tri`(▸/>), todo=`ring`(○/o); foot = `reading <repo> · offline pass · nothing leaves your machine`. Match golden "SCAN STATE" block (pinned stage = "judge fit" active, head col 7).
- `ScanSpinner` drives spinner (0.09s) + sweep head (0.07s) via `set_interval`; pause both when `not state.motion` (static frame 0 + mid-lit sweep). Stage index from real progress if exposed, else a fixed/elapsed-bucket value (documented).
- Tests: golden scan-frame char-for-char at pinned stage; `len(sweep(...))` invariant.

### Task 4: Wire matrix + scan into the layout (fixed-width regions) + panes
**Files:** Modify `frontier_scout/tui3/scout_view.py`, `panes.py`, `theme.tcss`.
- Render `adoption_matrix_lines` as painted line-Statics in a FIXED 59-cell instrument column (engine packs; no hand-padding across the screen). Preserve click-to-select via `LineClickStatic` (mouse+key parity).
- Wire ScanProgress into scout scanning + `panes.py` cap-scan; keep failed-scout ladder (1.8.0) aligned to §3.
- Confirm wide shows matrix; mid/narrow show Tier Ledger (unchanged).

### Task 5: Convergence harness (snapshots + golden + width)
**Files:** `tests/test_tui3_snapshots.py` (new), `pyproject.toml` ([dev] += `pytest-textual-snapshot`).
- `@pytest.mark.parametrize("size",[(140,38),(100,28),(72,20)])` → `snap_compare(MissionControlApp(demo=True), terminal_size=size)`. Seed with `--snapshot-update`.
- Aggregate the width/golden asserts from Tasks 1–3. Add pytest-textual-snapshot to [dev]; keep `pytest>=8.0.0` (snapshot pin forces <9 — compatible).

### Task 6: Finalize
**Files:** none new.
- Verify all surfaces degrade across color/mono/unicode/ascii/light with identical widths (golden in ascii; widths in all).
- Full suite on pytest 8.4.2 (3 `test_implement.py` env-only failures expected); ruff clean on touched files; golden diff clean; snapshots pass.
- Confirm: no Tweaks panel, only `pytest-textual-snapshot` added, AGENTS.md/CLAUDE.md untouched, narrow diffs.

---
After all tasks: final whole-branch review → finishing-a-development-branch → PR → CI → relax→merge→restore to main → user tags release.
