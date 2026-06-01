"""Mission Control (tui3) — the Scout tab (centerpiece).

Renders the Scout dashboard as a breakpoint-aware tree of painted Statics:

  hero/funnel band · scan bar (scope chips) · master verdict list ·
  reasoning detail · offline Ask

Reflow by the active Breakpoint:
  wide  → hero + scanbar + (list | detail) side by side  (master_detail)
  mid   → hero + scanbar + list + detail stacked under the selection
  narrow→ scanbar + compact list + stacked detail (no hero band)
  micro → scanbar + compact list + stacked detail

Every renderable goes through ``app._paint`` (color/mono fallback) and every
glyph through ``glyphs(unicode)`` (unicode/ASCII fallback). The view is pure —
the app re-renders this whole subtree on selection/scope/scan changes, matching
the immutable view-model.
"""

from __future__ import annotations

from typing import Any

from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from frontier_scout.tui3 import data
from frontier_scout.tui3.kit import (
    bar,
    breakpoint_for,
    fit_tone,
    glyphs,
    pct,
    risk_tone,
    sev_tone,
    verdict_label,
    verdict_tone,
)
from frontier_scout.tui3.widgets import ClickStatic

_TONE = {
    "mint": "#24d6a8", "gold": "#e3c26f", "blue": "#7aa6ff", "red": "#ff6b6b",
    "muted": "#6e8aa1", "bright": "#d9f7ff", "text": "#a9bccd",
}
SCOPES = ["all", "ai-devtools", "mcp", "deps"]
_ASKS = ["Is it safe to adopt now?", "What is the main risk?", "What is the next safe step?"]


def _hex(tone: str) -> str:
    return _TONE.get(tone, _TONE["muted"])


def _S(app: Any, markup: str, **kw: Any) -> Static:
    return Static(app._paint(markup), **kw)


def build_scout(app: Any) -> Vertical:
    bp = breakpoint_for(*app._term_size)
    gl = glyphs(app.state.unicode)
    verdicts = app.state.scoped_verdicts

    root = Vertical(classes="scout-root")
    if bp.show_hero:
        root.compose_add_child(_hero(app, gl))
    root.compose_add_child(_scanbar(app, gl))

    if not verdicts:
        root.compose_add_child(_empty(app, gl))
        return root

    full = bp.name in ("wide", "mid")
    if bp.master_detail:
        split = Horizontal(classes="scout-split")
        split.compose_add_child(_list(app, gl, verdicts, side=True, full=full))
        split.compose_add_child(_detail(app, gl, side=True))
        root.compose_add_child(split)
    else:
        root.compose_add_child(_list(app, gl, verdicts, side=False, full=full))
        root.compose_add_child(_detail(app, gl, side=False))
    return root


# ── hero / funnel band ───────────────────────────────────────────────────────
def _hero(app: Any, gl: dict[str, str]) -> Static:
    f = app.state.funnel
    langs = ", ".join(app.state.languages[:3]) or "—"
    filled, empty = bar(f.verdicts, max(f.candidates, f.verdicts, 1), 16, unicode=app.state.unicode)
    ratio = pct(f.verdicts, max(f.candidates, 1))
    title = (
        f"[#24d6a8 b]{gl['radar_core']} RADAR[/]  "
        f"[#a9bccd]{f.scanned}[/] [#6e8aa1]sources[/] [#25405c]{gl['arrow']}[/] "
        f"[#a9bccd]{f.candidates}[/] [#6e8aa1]candidates[/] [#25405c]{gl['arrow']}[/] "
        f"[#24d6a8 b]{f.verdicts}[/] [#6e8aa1]verdicts[/]"
    )
    cover = (
        f"[#24d6a8]{filled}[/][#152232]{empty}[/] [#6e8aa1]{ratio}% coverage {gl['pip']} "
        f"{f.window} {gl['pip']} ${f.cost:.2f} {gl['pip']} {f.last_run}[/]"
    )
    personal = (
        f"[#6e8aa1]tuned to[/] [#d9f7ff]{app.state.repo_name}[/] "
        f"[#6e8aa1]{gl['pip']} {langs} {gl['pip']} {app.state.provider}[/]"
    )
    return _S(app, f"{title}\n{cover}\n{personal}", classes="scout-hero panel")


# ── scan bar (scope chips) ───────────────────────────────────────────────────
def _scanbar(app: Any, gl: dict[str, str]) -> Horizontal:
    # Each scope chip and the scout affordance are their own ClickStatic so a
    # click routes to the same action the keys use (←/→ scope, s scout) — §5.
    row = Horizontal(classes="scout-scanbar")
    row.compose_add_child(_S(app, "[#6e8aa1]scope[/] "))
    for s in SCOPES:
        on = s == app.state.scope
        row.compose_add_child(ClickStatic(
            app._paint(f"[#24d6a8 b]{s}[/] " if on else f"[#6e8aa1]{s}[/] "),
            lambda sc=s: app._set_scope(sc),
            id=f"scope-{s}", classes="chip on" if on else "chip"))
    dry = " (dry-run)" if app.state.demo else ""
    row.compose_add_child(ClickStatic(
        app._paint(f"  [#24d6a8 b]s[/][#6e8aa1] scout{dry}[/]"),
        lambda: app.run_scout(dry_run=app.state.demo), id="scout-scan"))
    bp = breakpoint_for(*app._term_size)
    if bp.name != "micro":
        f = app.state.funnel
        row.compose_add_child(_S(
            app,
            f" [#6e8aa1]{gl['pip']} last {f.last_run} {gl['pip']} "
            f"${f.cost:.2f} {gl['pip']} {f.duration:.0f}s[/]"))
    return row


# ── empty / first-run state ──────────────────────────────────────────────────
def _empty(app: Any, gl: dict[str, str]) -> Static:
    demo = " (demo data)" if app.state.demo else ""
    scoped = "" if app.state.scope == "all" else f" in scope [#24d6a8]{app.state.scope}[/]"
    return _S(
        app,
        f"\n[#d9f7ff b]No verdicts yet{scoped}.[/]\n\n"
        f"[#6e8aa1]Press [#24d6a8 b]s[/] to scout this repo{demo}. Frontier Scout finds new AI\n"
        f"tools and dependency upgrades that fit [#a9bccd]{app.state.repo_name}[/], then ranks each\n"
        f"[#24d6a8]ADOPT[/] / [#e3c26f]TRIAL[/] / [#7aa6ff]ASSESS[/] / [#ff6b6b]HOLD[/] "
        f"with reasons you can act on.[/]\n\n"
        f"[#6e8aa1]{gl['pip']} [#24d6a8 b]?[/] glossary   {gl['pip']} [#24d6a8 b]{gl['arrow']}[/] change scope[/]",
        classes="scout-empty",
    )


# ── master list ──────────────────────────────────────────────────────────────
def _list(app: Any, gl: dict[str, str], verdicts: tuple, *, side: bool, full: bool) -> Vertical:
    box = Vertical(classes="scout-list" + (" side" if side else ""))
    box.compose_add_child(
        _S(app, f"[#6e8aa1]{len(verdicts)} verdict(s) {gl['pip']} ranked for {app.state.repo_name}[/]")
    )
    for i, v in enumerate(verdicts):
        on = i == app.state.sel
        marker = f"[#24d6a8]{gl['tri']}[/]" if on else " "
        tag = f"[{_hex(verdict_tone(v.verdict))} b]{verdict_label(v.verdict):<6}[/]"
        name = v.tool_name if len(v.tool_name) <= 22 else v.tool_name[:21] + "…"
        if full:
            fit_hex = _hex(fit_tone(v.fit))
            risk_hex = _hex(risk_tone(v.risk))
            age = f"  [#6e8aa1]{v.age}[/]" if v.age else ""
            line = (
                f"{marker} {tag}  [#d9f7ff]{name:<22}[/]  [#6e8aa1]{v.category}[/]  "
                f"[#6e8aa1]fit[/] [{fit_hex} b]{v.fit}[/] "
                f"[#6e8aa1]· risk[/] [{risk_hex} b]{v.risk}[/]{age}"
            )
        else:
            line = f"{marker} {tag} [#d9f7ff]{name}[/] [#6e8aa1]{v.fit}/{v.risk}[/]"
        box.compose_add_child(ClickStatic(
            app._paint(line),
            lambda i=i: app._select(i),
            lambda i=i: (app._select(i), app.call_later(app.action_dossier)),
            classes="row-sel" if on else ""))
    return box


# ── reasoning detail ─────────────────────────────────────────────────────────
def _detail(app: Any, gl: dict[str, str], *, side: bool) -> Vertical:
    v = app.state.current
    box = Vertical(classes="scout-detail panel" + (" side" if side else ""))
    if v is None:
        box.compose_add_child(_S(app, "[#6e8aa1]Select a verdict to see why.[/]"))
        return box

    tone = _hex(verdict_tone(v.verdict))
    box.compose_add_child(
        _S(app, f"[{tone} b]{verdict_label(v.verdict)}[/]  [#d9f7ff b]{v.tool_name}[/]  [#6e8aa1]{v.category}[/]")
    )
    src = v.source + (f" {gl['pip']} {v.age}" if v.age else "")
    box.compose_add_child(
        _S(app, f"[#6e8aa1]fit [{_hex(fit_tone(v.fit))}]{v.fit}[/]  "
                f"risk [{_hex(risk_tone(v.risk))}]{v.risk}[/]  {gl['pip']} {src}[/]")
    )
    if v.kind == "dep" and (v.from_version or v.to_version):
        box.compose_add_child(
            _S(app, f"[#6e8aa1]upgrade[/] [#a9bccd]{v.from_version}{gl['arrow']}{v.to_version}[/] "
                    f"[#6e8aa1]{v.classification}[/]")
        )

    # Order follows the prototype's VerdictDetail exactly: What it is → why it
    # fits → Concerns/✓ clean → Permission map → Next safe step → Actions → Ask →
    # source. (No "Why it matters" or inline "Unknowns" — the prototype keeps
    # unknowns in the Dossier only.)
    _section(app, box, "What it is", v.what)
    if v.fit_reasons:
        fit_head = "why this upgrade works for you" if v.kind == "dep" else "why it fits your repo"
        box.compose_add_child(_S(app, f"\n[#24d6a8 b]{fit_head}[/]"))
        for r in v.fit_reasons:
            box.compose_add_child(_S(app, f"  [#24d6a8]{gl['pip']}[/] [#a9bccd]{r}[/]"))
    if v.concerns:
        box.compose_add_child(_S(app, "\n[#24d6a8 b]Concerns[/]"))
        for c in v.concerns:
            ev = f" [#6e8aa1]{gl['pip']} {c.evidence}[/]" if c.evidence else ""
            ct = _hex(sev_tone(c.severity))
            box.compose_add_child(_S(app, f"  [{ct}]{c.severity:<6}[/] [#a9bccd]{c.label}[/]{ev}"))
    else:
        box.compose_add_child(_S(app, f"\n[#24d6a8]{gl['check']} clean[/] [#6e8aa1]— no concerns flagged[/]"))

    # Permission map — only when the verdict carries a capability manifest (deps
    # don't), matching the prototype. Tone: red for certain/likely on the
    # sensitive surfaces (shell/secrets/network), gold for possible, else muted.
    if v.capabilities:
        box.compose_add_child(_S(app, "\n[#24d6a8 b]Permission map[/]"))
        cells = []
        for key, status in v.capabilities:
            danger = status in ("certain", "likely") and key in ("shell", "secrets", "network")
            tone = "#ff6b6b" if danger else ("#e3c26f" if status == "possible" else "#6e8aa1")
            cells.append(f"[#6e8aa1]{key}[/] [{tone}]{status}[/]")
        box.compose_add_child(_S(app, "  " + "  ".join(cells)))

    if v.next_safe_step:
        box.compose_add_child(_S(app, f"\n[#24d6a8 b]Next safe step[/]\n  [#d9f7ff]{v.next_safe_step}[/]"))

    # Action bar — clickable, routing to the same gated actions as the keys (§5).
    # Dossier + Open apply to every verdict (incl. deps); lab/evaluate/implement
    # are tool-only. Don't gate the whole bar on kind — that would drop dep
    # mouse parity for Dossier/Open.
    specs = [("D", "dossier", "action_dossier"), ("o", "open", "action_open_target")]
    if v.kind != "dep":
        specs = [
            ("L", "lab", "action_lab"),
            ("e", "evaluate", "action_evaluate"),
            ("i", "implement", "action_implement"),
        ] + specs
    actions = Horizontal(classes="scout-actions")
    for key, label, act in specs:
        actions.compose_add_child(ClickStatic(
            app._paint(f"[#0b1117 on #24d6a8 b] {key} [/][#6e8aa1] {label}[/]  "),
            lambda a=act: app.call_later(getattr(app, a)),
            classes="scout-action"))
    box.compose_add_child(actions)

    box.compose_add_child(_ask(app, gl, v))
    if v.source_url:
        box.compose_add_child(_S(app, f"\n[#6e8aa1]source:[/] [#7aa6ff]{v.source_url}[/]"))
    return box


def _section(app: Any, box: Vertical, title: str, body: str) -> None:
    if body:
        box.compose_add_child(_S(app, f"\n[#24d6a8 b]{title}[/]\n  [#a9bccd]{body}[/]"))


def _ask(app: Any, gl: dict[str, str], v: Any) -> Static:
    """Offline Ask: deterministic answer for the standing question (never spends)."""
    q = _ASKS[getattr(app, "_ask_i", 0) % len(_ASKS)]
    try:
        answer = data.ask_offline(v, q, app.state.repo_name)
    except Exception:  # noqa: BLE001
        answer = "Unavailable offline."
    return _S(
        app,
        f"\n[#24d6a8 b]Ask[/] [#6e8aa1](offline {gl['pip']} [#24d6a8 b]a[/][#6e8aa1] next question)[/]\n"
        f"  [#6e8aa1]Q:[/] [#a9bccd]{q}[/]\n"
        f"  [#6e8aa1]A:[/] [#d9f7ff]{answer}[/]",
        classes="scout-ask",
    )
