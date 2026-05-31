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
from frontier_scout.tui3.kit import glyphs


def build_pane(app: Any, tab: str) -> Vertical:
    builder = _BUILDERS.get(tab, _placeholder)
    return builder(app)


def _S(app: Any, markup: str, **kw: Any) -> Static:
    """A Static whose content is painted for the current color mode."""
    return Static(app._paint(markup), **kw)


def _head(app: Any, title: str, sub: str) -> Static:
    return _S(app, f"[#24d6a8 b]{title.upper()}[/]   [#6e8aa1]{sub}[/]", classes="panel-title")


def _scout(app: Any) -> Vertical:
    from frontier_scout.tui3.scout_view import build_scout

    return build_scout(app)


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
    gd = app.state.guard_cache
    box = Vertical()
    box.compose_add_child(_head(app, "Guard", "Adoption Firewall · deterministic policy"))
    if gd is None:
        box.compose_add_child(_S(
            app, "\n[#6e8aa1]No guard run yet. Press [#24d6a8 b]r[/] to run the adoption firewall.[/]"))
        return box
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
    rows = app.state.deps_cache
    box = Vertical()
    box.compose_add_child(_head(app, "Dependencies", "Upgrades for packages you import"))
    if rows is None:
        box.compose_add_child(_S(
            app, "\n[#6e8aa1]No dependency scan yet. Press [#24d6a8 b]r[/] to scan your manifests.[/]"))
        return box
    if rows == ():
        box.compose_add_child(_S(app, "\n[#6e8aa1]No dependency findings.[/]"))
        return box
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

    # Providers — cheap env/which checks, safe inline.
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Providers[/]"))
    for p in data.providers():
        dot = f"[#24d6a8]{gl['dot']}[/]" if p["present"] else f"[#6e8aa1]{gl['ring']}[/]"
        box.compose_add_child(_S(app, f"{dot} [#d9f7ff]{p['name']}[/]  [#6e8aa1]{p['badge']} · {p['cost']}[/]"))

    cache = app.state.settings_cache
    if cache is None:
        box.compose_add_child(_S(
            app, "\n[#6e8aa1]Press [#24d6a8 b]r[/] to load policy, repo profile, and doctor.[/]"))
        return box

    # Policy (read-only display; edit via the CLI).
    pol = cache.get("policy", {})
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Policy[/]  [#6e8aa1](read-only)[/]"))
    if pol.get("exists"):
        strict = "[#24d6a8]on[/]" if pol.get("strict") else "[#6e8aa1]off[/]"
        box.compose_add_child(_S(
            app, f"  [#6e8aa1]strict[/] {strict}  [#6e8aa1]max risk[/] [#a9bccd]{pol.get('max_risk','medium')}[/]"))
        allowed = ", ".join(pol.get("allowed_verdicts", []) or []) or "—"
        blocked = ", ".join(pol.get("blocked_capabilities", []) or []) or "—"
        box.compose_add_child(_S(app, f"  [#6e8aa1]allow[/] [#a9bccd]{allowed}[/]"))
        box.compose_add_child(_S(app, f"  [#6e8aa1]block[/] [#a9bccd]{blocked}[/]"))
    else:
        box.compose_add_child(_S(app, "  [#6e8aa1]no policy file — defaults in effect[/]"))

    # Repo profile (read-only).
    prof = cache.get("profile", {})
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Repo profile[/]"))
    for label, key in (("languages", "languages"), ("frameworks", "frameworks"),
                       ("managers", "managers"), ("agent configs", "agent_configs")):
        vals = ", ".join(prof.get(key, []) or []) or "—"
        box.compose_add_child(_S(app, f"  [#6e8aa1]{label}[/] [#a9bccd]{vals}[/]"))
    risks = prof.get("risk_flags", []) or []
    if risks:
        box.compose_add_child(_S(app, f"  [#e3c26f]risk flags[/] [#a9bccd]{', '.join(risks)}[/]"))

    # Doctor.
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Doctor[/]"))
    marks = {
        "ok": f"[#24d6a8]{gl['check']}[/]",
        "warn": f"[#e3c26f]{gl['diamond']}[/]",
        "fail": f"[#ff6b6b]{gl['cross']}[/]",
    }
    for c in cache.get("doctor", []):
        mk = marks.get(c.get("status", "ok"), "·")
        box.compose_add_child(_S(app, f"{mk} [#a9bccd]{c.get('name','')}[/]  [#6e8aa1]{c.get('detail','')}[/]"))

    box.compose_add_child(_S(
        app, "\n[#6e8aa1]edit policy / rebuild profile / reconfigure: use the CLI (frontier-scout setup).[/]"))
    return box


def _placeholder(app: Any) -> Vertical:
    box = Vertical()
    box.compose_add_child(_S(app, f"[#6e8aa1]{app.state.tab}[/]"))
    return box


_BUILDERS = {
    "scout": _scout, "schedule": _schedule, "receipts": _receipts, "guard": _guard,
    "packs": _packs, "deps": _deps, "reports": _reports, "settings": _settings,
}
