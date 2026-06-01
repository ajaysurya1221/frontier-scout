"""Tests for Mission Control — the dense tabbed TUI (v1.5.0, ``frontier_scout/tui3``).

Mission Control's hard requirement is "renders flawlessly at any size, never
crashes, every capability reachable." These tests are the proof: the render kit
is pure and correct, the immutable state machine behaves, the app boots at seven
terminal geometries (40 cols → 200+, extreme ratios, the tiny floor), every tab
is reachable by number key, every global keybinding works, the overlays open and
close, and — the regression guard for the ``event.size`` fix — a live resize
reflows to the correct breakpoint at every step including floor recovery.

All async via ``app.run_test(size=…)`` + ``asyncio.run`` — no new deps, matching
the existing suite (see ``test_tui2.py``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.text import Text

from frontier_scout.tui3.app import TAB_IDS, MissionControlApp
from frontier_scout.tui3.kit import bar, breakpoint_for, glyphs, mono, pct, verdict_label
from frontier_scout.tui3.state import AppState, Funnel, Verdict

# Sizes spanning the responsive spec: tiny floor, micro, narrow, mid, wide,
# extreme wide-short, and tall-narrow.
SIZES = [(40, 24), (80, 28), (120, 40), (200, 50), (48, 60), (200, 16), (34, 10)]


def _run(coro):
    return asyncio.run(coro)


def _sample_verdicts() -> tuple[Verdict, ...]:
    return (
        Verdict.from_payload(
            {
                "tool_name": "ruff",
                "category": "linting",
                "verdict": "adopt",
                "fit": "high",
                "risk": "low",
                "what": "fast Python linter",
                "why_it_matters": "replaces several slow tools",
                "fit_reasons": ["you already run flake8", "Rust-fast on CI"],
                "concerns": [{"label": "young project", "severity": "low", "evidence": "v0.x"}],
                "next_safe_step": "frontier-scout lab ruff",
                "source_url": "https://github.com/astral-sh/ruff",
            }
        ),
        Verdict.from_payload(
            {
                "tool_name": "pydantic",
                "category": "validation",
                "verdict": "trial",
                "fit": "medium",
                "risk": "medium",
                "what": "data validation via type hints",
                "source_url": "https://pypi.org/project/pydantic/",
            }
        ),
    )


# ── 1. Render kit — pure, no Textual ─────────────────────────────────────────


def test_breakpoint_for_names():
    cases = {
        (30, 10): "tiny",
        (34, 10): "tiny",
        (40, 24): "micro",
        (36, 11): "micro",
        (70, 24): "narrow",
        (100, 30): "mid",
        (120, 40): "wide",
        (200, 16): "wide",
    }
    for (cols, rows), expected in cases.items():
        assert breakpoint_for(cols, rows).name == expected, (cols, rows)


def test_breakpoint_flags():
    # wide gets the full rail + inline master/detail in Scout.
    assert breakpoint_for(120, 40).rail is True
    assert breakpoint_for(120, 40).master_detail is True
    # mid keeps the rail but compact, and folds master/detail away.
    assert breakpoint_for(100, 30).rail is True
    assert breakpoint_for(100, 30).rail_compact is True
    assert breakpoint_for(100, 30).master_detail is False
    # narrow + micro drop the rail for the top tab strip.
    assert breakpoint_for(70, 24).rail is False
    assert breakpoint_for(48, 22).rail is False
    assert breakpoint_for(48, 22).master_detail is False


def test_mono_strips_color_keeps_bold_and_parses():
    out = mono("[#d9f7ff b]frontier scout[/] [#25405c]>[/] [#a9bccd]repo[/]")
    assert "#" not in out  # all color removed
    assert "b" in out  # bold style preserved
    # Result must be balanced markup Rich can parse without raising.
    Text.from_markup(out)
    # Plain text passes through untouched.
    assert mono("plain text") == "plain text"
    # A background-only tag collapses but stays parseable.
    Text.from_markup(mono("[on #10202a]bg[/]"))


def test_pct_and_bar():
    assert pct(7, 10) == 70
    assert pct(0, 0) == 0
    assert pct(350, 377) == 93  # round(92.838) → 93
    for value, maximum, width in ((3, 10, 20), (0, 0, 12), (10, 10, 8)):
        filled, empty = bar(value, maximum, width)
        assert len(filled) + len(empty) == width


def test_glyphs_unicode_and_ascii():
    uni, ascii_ = glyphs(True), glyphs(False)
    # Same keys in both maps; ASCII map has no non-ASCII bytes.
    assert set(uni) == set(ascii_)
    for v in ascii_.values():
        assert v.isascii()


def test_verdict_label():
    assert verdict_label("adopt") == "ADOPT"
    assert verdict_label("hold") == "HOLD"
    assert verdict_label("unknown") == "ASSESS"  # default


# ── 2. Immutable state machine ───────────────────────────────────────────────


def test_appstate_move_clamps():
    st = AppState(verdicts=_sample_verdicts())
    assert st.sel == 0
    assert st.move(-1).sel == 0  # clamped at the low end
    assert st.move(1).sel == 1
    assert st.move(5).sel == 1  # clamped at the high end (2 verdicts)


def test_appstate_current_and_scoped():
    st = AppState(verdicts=_sample_verdicts())
    assert st.current.tool_name == "ruff"
    assert st.with_(sel=1).current.tool_name == "pydantic"
    # Empty state has no current verdict and never raises.
    assert AppState().current is None
    # scoped_verdicts: "all" returns everything; "deps" filters to dep kind.
    assert len(st.scoped_verdicts) == 2
    assert st.with_(scope="deps").scoped_verdicts == ()


def test_funnel_from_payload():
    f = Funnel.from_payload({"scanned": 120, "candidates": 30, "verdicts": [1, 2, 3], "cost_usd": 0.42})
    assert f.scanned == 120
    assert f.candidates == 30
    assert f.verdicts == 3
    assert f.cost == 0.42


def _mixed_verdicts() -> tuple[Verdict, ...]:
    # Alternating tool / dep so the scoped subset is a strict subset of the
    # full list at different positions (dep at indices 1 and 3).
    return (
        Verdict.from_payload({"tool_name": "tool-a"}, kind="tool"),
        Verdict.from_payload({"tool_name": "dep-a"}, kind="dep"),
        Verdict.from_payload({"tool_name": "tool-b"}, kind="tool"),
        Verdict.from_payload({"tool_name": "dep-b"}, kind="dep"),
    )


def test_current_uses_scoped_index():
    # Regression guard for the scoped-selection bug: when scope != "all", the
    # highlighted row (rendered over scoped_verdicts at i == sel) and the detail
    # panel (current) MUST resolve to the same verdict. This FAILS against the
    # old `current` that indexed the full verdicts list.
    st = AppState(verdicts=_mixed_verdicts(), scope="deps", sel=0)
    assert st.scoped_verdicts[0].tool_name == "dep-a"
    assert st.current is st.scoped_verdicts[0]  # first dep, not first verdict
    moved = st.move(1)
    assert moved.current is moved.scoped_verdicts[1]  # second dep
    assert moved.current.tool_name == "dep-b"


def test_current_scoped_clamps_and_stays_in_scope():
    # An out-of-range sel resolves to the last scoped verdict, never raises,
    # and never leaks a verdict from outside the scope.
    st = AppState(verdicts=_mixed_verdicts(), scope="deps", sel=99)
    scoped = st.scoped_verdicts
    assert st.current is scoped[-1]
    assert st.current.kind == "dep"


def test_verdict_string_list_fields_not_char_split():
    # A bare string payload field must become a single-item tuple, not a tuple
    # of individual characters.
    v = Verdict.from_payload({"fit_reasons": "high performance"})
    assert v.fit_reasons == ("high performance",)
    v2 = Verdict.from_payload({"unknowns": "license unclear"})
    assert v2.unknowns == ("license unclear",)
    # Lists still coerce element-wise to strings.
    v3 = Verdict.from_payload({"fit_reasons": ["a", "b"]})
    assert v3.fit_reasons == ("a", "b")


def test_funnel_verdicts_non_sequence_guard():
    # A non-sequence verdicts value must not raise TypeError on len().
    assert Funnel.from_payload({"verdicts": 5}).verdicts == 0
    assert Funnel.from_payload({"verdicts": None}).verdicts == 0
    # Sequences still count correctly.
    assert Funnel.from_payload({"verdicts": ["a", "b"]}).verdicts == 2


# ── 3. Boots at every size, never crashes ────────────────────────────────────


def test_boots_at_all_sizes():
    async def go():
        for size in SIZES:
            app = MissionControlApp(repo=Path("."), demo=True)
            async with app.run_test(size=size):
                assert app.state.tab == "scout"
                # Core chrome always present (compose-once shell).
                assert app.query_one("#mc-header")
                assert app.query_one("#mc-compass")

    _run(go())


# ── 4. Tab navigation: every tab reachable by number key ─────────────────────


def test_tab_navigation_all_tabs():
    async def go():
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            for i, tab in enumerate(TAB_IDS, start=1):
                await pilot.press(str(i))
                await pilot.pause()
                assert app.state.tab == tab, (i, tab, app.state.tab)

    _run(go())


# ── 5. Global keybindings: toggles + overlays ────────────────────────────────


def test_toggles_unicode_and_color():
    async def go():
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            uni0, col0 = app.state.unicode, app.state.color
            await pilot.press("u")
            await pilot.pause()
            assert app.state.unicode == (not uni0)
            await pilot.press("c")
            await pilot.pause()
            assert app.state.color == (not col0)

    _run(go())


def test_overlays_open_and_close():
    async def go():
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("question_mark")
            await pilot.pause()
            assert len(app.screen_stack) > 1  # help pushed
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1
            await pilot.press("n")
            await pilot.pause()
            assert len(app.screen_stack) > 1  # notifications pushed
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1

    _run(go())


# ── 6. Live resize reflows to the right breakpoint (event.size regression) ────


def test_live_resize_reflows_every_breakpoint():
    async def go():
        steps = [(95, 30), (70, 24), (48, 22), (34, 10), (200, 16), (36, 11), (120, 40)]
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            assert app._bp_name == "wide"
            for (w, h) in steps:
                await pilot.resize_terminal(w, h)
                await pilot.pause()
                assert app._bp_name == breakpoint_for(w, h).name, (w, h, app._bp_name)

    _run(go())


# ── 7. Scout interactions: scope + ask cycling ───────────────────────────────


def test_scout_scope_and_ask_cycle():
    async def go():
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            app.state = app.state.with_(verdicts=_sample_verdicts(), tab="scout", sel=0)
            await pilot.press("1")
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            assert app.state.scope == "ai-devtools"
            await pilot.press("left")
            await pilot.pause()
            assert app.state.scope == "all"
            ask0 = app._ask_i
            await pilot.press("a")
            await pilot.pause()
            assert app._ask_i == ask0 + 1

    _run(go())


# ── 8. Every pane builds in every glyph/color mode ───────────────────────────


def test_every_pane_builds_all_modes():
    async def go():
        for unicode in (True, False):
            for color in (True, False):
                app = MissionControlApp(repo=Path("."), demo=True)
                async with app.run_test(size=(120, 40)) as pilot:
                    app.state = app.state.with_(
                        unicode=unicode, color=color, verdicts=_sample_verdicts()
                    )
                    for i, _tab in enumerate(TAB_IDS, start=1):
                        await pilot.press(str(i))
                        await pilot.pause()
                        # The pane mounted children — no silent empty render.
                        assert app.query_one("#mc-main").children

    _run(go())
