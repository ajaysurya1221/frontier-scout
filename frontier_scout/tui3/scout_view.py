"""Mission Control (tui3) — the Scout tab (centerpiece).

Renders the Scout dashboard as a breakpoint-aware tree of painted Statics:

  hero/funnel band · scan bar (scope chips) · Adoption Matrix (wide) or
  Tier Ledger (mid/narrow/micro) · master verdict list · reasoning detail ·
  offline Ask

Reflow by the active Breakpoint:
  wide  → hero + matrix + scanbar + (list | detail) side by side
  mid   → hero + tier-ledger + scanbar + list + detail stacked
  narrow→ tier-ledger + scanbar + compact list + stacked detail (no hero band)
  micro → scanbar + compact list + stacked detail

Every renderable goes through ``app._paint`` (color/mono fallback) and every
glyph through ``glyphs(unicode)`` (unicode/ASCII fallback). The view is pure —
the app re-renders this whole subtree on selection/scope/scan changes, matching
the immutable view-model.

Pure bucketing helpers (no Textual import):
  ``bucket_matrix(verdicts)`` → {(fit, risk): [(index, Verdict), …]}
  ``tier_ledger(verdicts)``   → [{"tier", "count", "fill", "names", "overflow"}, …]
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
    gauge,
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
# Capability surfaces the Adoption Firewall treats as dangerous (mirrors
# mcp_audit.DANGEROUS_KEYS). Real statuses: likely / possible / unlikely / unknown.
_DANGEROUS_CAPS = {"write", "network", "browser", "shell", "credential", "unknown"}

# ── Adoption Matrix / Tier Ledger — axis definitions ─────────────────────────
# FITS: rows top-to-bottom (high fit at top = good, low fit at bottom).
# RISKS: cols left-to-right (low risk at left = safe, high risk at right).
FITS: tuple[str, ...] = ("high", "medium", "low")
RISKS: tuple[str, ...] = ("low", "medium", "high")

# Tier Ledger constants
_TIER_ORDER = ("adopt", "trial", "assess", "hold")
_TIER_TONE = {"adopt": "mint", "trial": "gold", "assess": "blue", "hold": "red"}
_LEDGER_CAP = 8   # gauge max
_DOT_MAX = 14     # max dots shown per cell before +N overflow


# ── Pure bucketing helpers (no Textual — unit-testable in isolation) ──────────

def bucket_matrix(
    verdicts: tuple,
) -> dict[tuple[str, str], list[tuple[int, Any]]]:
    """Return a mapping of (fit, risk) → [(original_index, Verdict), …].

    All nine cells are always present in the result (empty cells have ``[]``).
    The order within each cell preserves the original verdict list order.
    """
    cells: dict[tuple[str, str], list[tuple[int, Any]]] = {
        (f, r): [] for f in FITS for r in RISKS
    }
    for idx, v in enumerate(verdicts):
        fit = getattr(v, "fit", "medium")
        risk = getattr(v, "risk", "medium")
        # Clamp unknown fit/risk values to "medium" so nothing falls off the grid.
        if fit not in FITS:
            fit = "medium"
        if risk not in RISKS:
            risk = "medium"
        cells[(fit, risk)].append((idx, v))
    return cells


def tier_ledger(
    verdicts: tuple,
) -> list[dict]:
    """Return one dict per tier with display data for the Tier Ledger.

    Each row::

        {
          "tier":     str,               # "adopt" | "trial" | "assess" | "hold"
          "tone":     str,               # palette key for the gauge
          "count":    int,               # total verdicts for this tier
          "fill":     int,               # min(count, _LEDGER_CAP) — gauge value
          "names":    [(idx, name), …],  # first 5 (idx, tool_name) pairs
          "overflow": int,               # count - 5 when count > 5, else 0
        }
    """
    rows = []
    for tier in _TIER_ORDER:
        items = [(i, v) for i, v in enumerate(verdicts) if getattr(v, "verdict", "") == tier]
        count = len(items)
        fill = min(count, _LEDGER_CAP)
        first5 = [(i, v.tool_name) for i, v in items[:5]]
        overflow = max(0, count - 5)
        rows.append({
            "tier": tier,
            "tone": _TIER_TONE[tier],
            "count": count,
            "fill": fill,
            "names": first5,
            "overflow": overflow,
        })
    return rows


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

    # Adoption Matrix (wide) / Tier Ledger (mid) placed after hero, before scanbar.
    # Placement follows the prototype's ScoutPane: matrix in the calm-head band on
    # wide (masterDetail=True); ledger inside the coverage area on mid/narrow.
    # micro skips both (too little vertical room for the extra instrument).
    if verdicts:
        if bp.master_detail:
            root.compose_add_child(_adoption_matrix(app, gl, verdicts))
        elif bp.name in ("mid", "narrow"):
            root.compose_add_child(_tier_ledger_widget(app, gl, verdicts))

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


# ── Adoption Matrix (wide breakpoint) ────────────────────────────────────────
#
# Layout:
#   header line   — "adoption matrix · fit × risk · <N>"
#   axis row      — risk → low / med / high column headers
#   3 rows of 3   — one ClickStatic per cell; dots + count badge + overflow
#   readout line  — "▸ <name> · <verdict> · fit <f> · risk <r>" or hint
#
# Each cell is a ClickStatic so clicking anywhere in the cell selects its first
# verdict (if populated). Individual dots within a cell that has >1 verdict are
# rendered inline as text; the cell-click selects the first dot (mouse parity
# for the common case). The readout line updates on the next render cycle when
# state.sel changes.
#
# Invariants:
#   • Every glyph through glyphs() + app._paint  (color/mono + unicode/ascii)
#   • click → app._select(i) — same path as j/k  (no duplicated logic)
#   • compose_add_child only; never remove_children + remount

_RISK_LABELS = {"low": "low", "medium": "med", "high": "high"}
_FIT_LABELS = {"high": "hi ", "medium": "med", "low": "lo "}


def _cell_markup(
    app: Any,
    gl: dict[str, str],
    items: list[tuple[int, Any]],
    sel: int,
    fit: str,
    risk: str,
) -> str:
    """Build the Rich-markup string for one matrix cell.

    Cells have a fixed 3-line budget:
      line 0 — count badge (when >3) OR empty
      line 1 — dot run (up to _DOT_MAX) + +N overflow
      line 2 — "safe" / "hold" label when empty corner, else blank
    This gives each cell a predictable height without Textual grid CSS.
    """
    border = _hex("muted")
    safe_corner = fit == "high" and risk == "low"
    hold_corner = fit == "low" and risk == "high"

    if not items:
        # Empty cell — show corner label if applicable, otherwise faint placeholder.
        if safe_corner:
            return app._paint(f"[{_hex('mint')} dim]safe[/]")
        if hold_corner:
            return app._paint(f"[{_hex('red')} dim]hold[/]")
        return app._paint(f"[{border}]·[/]")

    count = len(items)
    displayed = items[:_DOT_MAX]
    overflow = count - _DOT_MAX if count > _DOT_MAX else 0

    # Build dot string — selected dot uses radar_core glyph.
    parts: list[str] = []
    if count > 3:
        cnt_hex = _hex("text")
        parts.append(f"[{cnt_hex}]{count}[/] ")

    for i, v in displayed:
        tone_hex = _hex(verdict_tone(v.verdict))
        glyph = gl["radar_core"] if i == sel else gl["dot"]
        # Each dot is individually tagged so it carries correct color in both
        # color and mono modes (the color is stripped by app._paint in mono,
        # leaving the glyph which still conveys presence).
        parts.append(f"[{tone_hex}]{glyph}[/]")

    if overflow:
        parts.append(f"[{_hex('muted')}]+{overflow}[/]")

    return app._paint("".join(parts))


def _adoption_matrix(app: Any, gl: dict[str, str], verdicts: tuple) -> Vertical:
    """Render the 3×3 Adoption Matrix as a Vertical containing box-drawn rows."""
    sel = app.state.sel
    n = len(verdicts)
    cells = bucket_matrix(verdicts)

    box = Vertical(classes="scout-matrix panel")

    # ── header ────────────────────────────────────────────────────────────────
    box.compose_add_child(_S(
        app,
        f"[{_hex('muted')}]adoption matrix[/] "
        f"[{_hex('text')}]{gl['pip']} fit {gl['ud'][0]} {gl['pip']} risk {gl['arrow']} "
        f"{gl['pip']}[/] [{_hex('mint')} b]{n}[/]",
    ))

    # ── risk axis header ───────────────────────────────────────────────────────
    risk_header = (
        f"[{_hex('muted')}]{'fit ':>5}[/]  "
        + "  ".join(
            f"[{_hex('muted')}]{_RISK_LABELS[r]:<6}[/]"
            for r in RISKS
        )
    )
    box.compose_add_child(_S(app, risk_header))

    # ── 3 rows of cells ───────────────────────────────────────────────────────
    for fit in FITS:
        row_w = Horizontal(classes="scout-matrix-row")
        # fit axis label
        row_w.compose_add_child(_S(
            app,
            f"[{_hex('muted')}]{_FIT_LABELS[fit]}[/]  ",
        ))
        for risk in RISKS:
            items = cells[(fit, risk)]
            markup = _cell_markup(app, gl, items, sel, fit, risk)

            if items:
                first_idx = items[0][0]
                cell_w = ClickStatic(
                    markup,
                    lambda i=first_idx: app._select(i),
                    classes="scout-matrix-cell",
                )
            else:
                cell_w = Static(markup, classes="scout-matrix-cell empty")

            row_w.compose_add_child(cell_w)
        box.compose_add_child(row_w)

    # ── readout line ──────────────────────────────────────────────────────────
    v = app.state.current
    if v is not None:
        tone_hex = _hex(verdict_tone(v.verdict))
        name = v.tool_name.split("/")[-1]
        readout = (
            f"[{tone_hex}]{gl['tri']}[/] "
            f"[{_hex('bright')}]{name}[/] "
            f"[{_hex('muted')}]{gl['pip']}[/] "
            f"[{tone_hex}]{verdict_label(v.verdict).lower()}[/] "
            f"[{_hex('muted')}]{gl['pip']} fit[/] [{_hex(fit_tone(v.fit))} b]{v.fit}[/] "
            f"[{_hex('muted')}]{gl['pip']} risk[/] [{_hex(risk_tone(v.risk))} b]{v.risk}[/]"
        )
    else:
        readout = f"[{_hex('muted')}]select a verdict to read it[/]"

    box.compose_add_child(_S(app, readout, classes="scout-matrix-read"))
    return box


# ── Tier Ledger (mid / narrow breakpoints) ────────────────────────────────────
#
# Four rows: adopt / trial / assess / hold.
# Each row: tag · capped segment gauge · count (with + when over cap) · names.
# Names are ClickStatics routing to app._select(i).

def _tier_ledger_widget(app: Any, gl: dict[str, str], verdicts: tuple) -> Vertical:
    """Render the Tier Ledger as a Vertical with one row per tier."""
    box = Vertical(classes="scout-ledger panel")
    box.compose_add_child(_S(
        app,
        f"[{_hex('muted')}]tier ledger[/]",
    ))

    rows = tier_ledger(verdicts)
    for row in rows:
        tier = row["tier"]
        tone = row["tone"]
        count = row["count"]
        fill = row["fill"]
        names = row["names"]
        overflow = row["overflow"]
        tone_hex = _hex(tone)

        # Gauge string: lit and unlit pips via bar() so it routes through glyphs().
        lit, unlit = bar(fill, _LEDGER_CAP, _LEDGER_CAP, unicode=app.state.unicode)
        gauge_str = (
            f"[{tone_hex}]{lit}[/]"
            + (f"[{_hex('muted')}]{unlit}[/]" if unlit else "")
        )

        # Count badge: show + suffix when over cap.
        count_mark = "+" if count > _LEDGER_CAP else " "
        count_str = f"[{_hex('text')}]{count}{count_mark}[/]"

        # Tag label.
        tag_str = f"[{tone_hex} b]{verdict_label(tier):<6}[/]"

        # Header part of the row (tag + gauge + count).
        row_w = Horizontal(classes="scout-ledger-row")
        row_w.compose_add_child(_S(app, f"{tag_str} {gauge_str} {count_str}  "))

        if not names:
            row_w.compose_add_child(_S(app, f"[{_hex('muted')}]{gl['pip']} none[/]"))
        else:
            # Render each name as a ClickStatic for mouse-select parity.
            for j, (idx, name) in enumerate(names):
                if j > 0:
                    row_w.compose_add_child(_S(app, f"[{_hex('muted')}] {gl['pip']} [/]"))
                on = idx == app.state.sel
                name_hex = _hex("mint") if on else _hex("text")
                row_w.compose_add_child(ClickStatic(
                    app._paint(f"[{name_hex}]{name}[/]"),
                    lambda i=idx: app._select(i),
                    classes="ledger-name sel" if on else "ledger-name",
                ))
            if overflow:
                row_w.compose_add_child(_S(
                    app, f"[{_hex('muted')}] {gl['pip']} +{overflow} more[/]",
                ))
        box.compose_add_child(row_w)

    return box


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
    fit_g = gauge(label="fit", level=v.fit, read=v.fit, unicode=app.state.unicode)
    risk_g = gauge(label="risk", level=v.risk, read=v.risk, danger=True, unicode=app.state.unicode)
    box.compose_add_child(
        _S(app, f"{fit_g}   {risk_g}   [#6e8aa1]{gl['pip']} {src}[/]")
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
    # don't), matching the prototype.  Each capability is rendered as a gauge so
    # the risk level is both a colour signal and a visible pip count.
    # Level mapping: likely→high, possible→medium, unlikely/unknown→none (muted,
    # 0 pips).  Spec: "unlikely=0=muted" — empty-but-present gauge.
    # Tone: dangerous+likely→red (danger=True, level=high); dangerous+possible→
    # gold (danger=True, level=medium); non-dangerous→normal tone curve.
    if v.capabilities:
        box.compose_add_child(_S(app, "\n[#24d6a8 b]Permission map[/]"))
        _STATUS_LEVEL = {"likely": "high", "possible": "medium", "unlikely": "none"}
        cells = []
        for key, status in v.capabilities:
            dangerous = key in _DANGEROUS_CAPS
            cap_level = _STATUS_LEVEL.get(status, "none")
            g_str = gauge(
                label=key,
                level=cap_level,
                read=status,
                danger=dangerous,
                unicode=app.state.unicode,
            )
            cells.append(g_str)
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
