"""Mission Control (tui3) — pane builders.

``build_pane(app, tab)`` returns the widget for a tab. This module starts with
lightweight, real-data panes (no mock content) and is expanded tab-by-tab into
the full master/detail Scout view and capability panes in later increments.

Every renderable goes through ``_S(app, markup)`` so it inherits the app's
color fallback (``app._paint``), and every glyph comes from ``glyphs(unicode)``
so the unicode/ASCII fallback holds on every tab.
"""

from __future__ import annotations

from typing import Any

from textual.containers import Vertical
from textual.widgets import Static

from frontier_scout.tui3 import data
from frontier_scout.tui3.kit import glyphs, verdict_label


def build_pane(app: Any, tab: str) -> Vertical:
    builder = _BUILDERS.get(tab, _placeholder)
    return builder(app)


def _S(app: Any, markup: str, **kw: Any) -> Static:
    """A Static whose content is painted for the current color mode."""
    return Static(app._paint(markup), **kw)


def _head(app: Any, title: str, sub: str) -> Static:
    return _S(app, f"[#24d6a8 b]{title.upper()}[/]   [#6e8aa1]{sub}[/]", classes="panel-title")


def _scout(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    box = Vertical()
    box.compose_add_child(_head(app, "Scout", f"{len(app.state.verdicts)} verdicts · {app.state.repo_name}"))
    if not app.state.verdicts:
        box.compose_add_child(_S(
            app,
            f"\n[#6e8aa1]No scan yet. Press [#24d6a8 b]s[/] to run a scout"
            f"{' (demo)' if app.state.demo else ''}.[/]"))
        return box
    for i, v in enumerate(app.state.verdicts):
        on = i == app.state.sel
        tag = f"[#24d6a8]{verdict_label(v.verdict)}[/]"
        marker = gl["tri"] if on else " "
        line = f"{marker} {tag}  [#d9f7ff]{v.tool_name}[/]  [#6e8aa1]{v.category}[/]"
        box.compose_add_child(_S(app, line, classes="row-sel" if on else ""))
    return box


def _schedule(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    rows = data.schedules()
    box = Vertical()
    box.compose_add_child(_head(app, "Schedule", f"{len(rows)} schedule(s) · headless coverage"))
    if not rows:
        box.compose_add_child(_S(app, "\n[#6e8aa1]No schedules yet.[/]"))
    for s in rows:
        state = "[#24d6a8]on[/]" if not s["disabled"] else "[#6e8aa1]off[/]"
        box.compose_add_child(_S(
            app, f"{gl['dot']} [#d9f7ff]{s['repo'].split('/')[-1]}[/]  [#6e8aa1]{s['human']}[/]  {state}"))
    box.compose_add_child(_S(app, f"\n[#6e8aa1]crontab:[/] [#a9bccd]{data.crontab_line()}[/]"))
    return box


def _receipts(app: Any) -> Vertical:
    rows = data.receipts()
    box = Vertical()
    box.compose_add_child(_head(app, "Receipts", f"{len(rows)} recorded · try-before-trust"))
    if not rows:
        box.compose_add_child(_S(app, "\n[#6e8aa1]No receipts yet — run a lab or trial.[/]"))
    for r in rows:
        box.compose_add_child(_S(
            app,
            f"[#a9bccd]{r['tool_name']}[/]  [#6e8aa1]{r['kind']}[/]  "
            f"[#24d6a8]{r['status']}[/]  [#6e8aa1]{r['when']}[/]"))
    return box


def _guard(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    gd = data.guard(app.state.repo, strict=False)
    box = Vertical()
    box.compose_add_child(_head(app, "Guard", "Adoption Firewall · deterministic policy"))
    if gd["fail"]:
        mark = f"[#ff6b6b]{gl['cross']} exit 1[/]"
    else:
        mark = f"[#24d6a8]{gl['check']} exit 0[/]"
    box.compose_add_child(_S(app, f"\n{mark}  [#6e8aa1]{gd['high']} high · {gd['medium']} medium[/]"))
    for f in gd["findings"]:
        box.compose_add_child(_S(
            app,
            f"[#e3c26f]{f['severity']}[/] [#d9f7ff]{f['tool']}[/] [#6e8aa1]{f['rule']}[/] — {f['detail']}"))
    return box


def _packs(app: Any) -> Vertical:
    rows = data.packs(app.state.languages)
    box = Vertical()
    box.compose_add_child(_head(app, "Scout Packs", f"{len(rows)} curated source sets"))
    for p in rows:
        box.compose_add_child(_S(
            app,
            f"[#d9f7ff]{p['name']}[/]  [#6e8aa1]{p['slug']}[/]  "
            f"[#6e8aa1]{p['seeds']} seeds · {p['sources']} sources[/]"))
    return box


def _deps(app: Any) -> Vertical:
    rows = data.dependencies(app.state.repo)
    box = Vertical()
    box.compose_add_child(_head(app, "Dependencies", "Upgrades for packages you import"))
    if not rows:
        box.compose_add_child(_S(app, "\n[#6e8aa1]No dependency findings — run a deps scan.[/]"))
    for d in rows:
        box.compose_add_child(_S(
            app,
            f"[#d9f7ff]{d['tool_name']}[/] [#6e8aa1]{d['from_version']}→{d['to_version']}[/] "
            f"[#6e8aa1]{d['classification']}[/]"))
    return box


def _reports(app: Any) -> Vertical:
    box = Vertical()
    box.compose_add_child(_head(app, "Reports", "Render the latest scan into a shareable radar"))
    outs = [
        ("briefing.html", "executive radar — shareable, offline"),
        ("briefing.md", "markdown digest for PRs / chat"),
        ("verdicts.json", "machine-readable verdict payload"),
    ]
    for f, d in outs:
        box.compose_add_child(_S(app, f"[#a9bccd]{f}[/]  [#6e8aa1]{d}[/]"))
    return box


def _settings(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    box = Vertical()
    box.compose_add_child(_head(app, "Settings", "Providers · policy · profile · doctor"))
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Providers[/]"))
    for p in data.providers():
        dot = f"[#24d6a8]{gl['dot']}[/]" if p["present"] else f"[#6e8aa1]{gl['ring']}[/]"
        box.compose_add_child(_S(app, f"{dot} [#d9f7ff]{p['name']}[/]  [#6e8aa1]{p['badge']} · {p['cost']}[/]"))
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Doctor[/]"))
    marks = {
        "ok": f"[#24d6a8]{gl['check']}[/]",
        "warn": f"[#e3c26f]{gl['diamond']}[/]",
        "fail": f"[#ff6b6b]{gl['cross']}[/]",
    }
    for c in data.doctor():
        mk = marks.get(c["status"], "·")
        box.compose_add_child(_S(app, f"{mk} [#a9bccd]{c['name']}[/]  [#6e8aa1]{c['detail']}[/]"))
    return box


def _placeholder(app: Any) -> Vertical:
    box = Vertical()
    box.compose_add_child(_S(app, f"[#6e8aa1]{app.state.tab}[/]"))
    return box


_BUILDERS = {
    "scout": _scout, "schedule": _schedule, "receipts": _receipts, "guard": _guard,
    "packs": _packs, "deps": _deps, "reports": _reports, "settings": _settings,
}
