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

from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from frontier_scout.tui3 import data
from frontier_scout.tui3.kit import bar, glyphs
from frontier_scout.tui3.widgets import ClickStatic


def build_pane(app: Any, tab: str) -> Vertical:
    builder = _BUILDERS.get(tab, _placeholder)
    return builder(app)


def _S(app: Any, markup: str, **kw: Any) -> Static:
    """A Static whose content is painted for the current color mode."""
    return Static(app._paint(markup), **kw)


def _head(app: Any, title: str, sub: str) -> Static:
    return _S(app, f"[#24d6a8 b]{title}[/]\n[#6e8aa1]{sub}[/]")


def _scan_btn(app: Any, tab: str, label: str) -> ClickStatic:
    """Primary scan/run button. Clicking it fires the SAME worker the `r` key
    fires (action_refresh → _refresh_worker) — one worker, two triggers (§5)."""
    markup = f"\n[#0b1117 on #24d6a8 b] r [/] [#24d6a8]{label}[/]"
    return ClickStatic(
        app._paint(markup),
        lambda: app._refresh_worker(tab),
        id=f"cap-scan-{tab}",
        classes="cap-scan-btn",
    )


def _scout(app: Any) -> Vertical:
    from frontier_scout.tui3.scout_view import build_scout

    return build_scout(app)


def _schedule(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    rows = data.schedules()
    box = Vertical()
    box.compose_add_child(
        _head(
            app,
            "Schedule",
            "Headless coverage — scheduled scouts run in the background and notify "
            "you only when verdicts change.",
        )
    )
    if not rows:
        box.compose_add_child(_S(app, "\n[#6e8aa1]No schedules yet.[/]"))
    # Clamp the selection defensively: if it ran off the end (a removal), select
    # the last row; with no rows there is nothing to mark.
    sel = min(max(0, getattr(app.state, "sched_sel", 0)), len(rows) - 1) if rows else -1
    for i, s in enumerate(rows):
        sw = (
            f"[#24d6a8]{gl['dot']} on[/]"
            if not s["disabled"]
            else f"[#6e8aa1]{gl['ring']} off[/]"
        )
        live = "[#e3c26f]live scan[/]" if s["live"] else "[#24d6a8]dry-run[/]"
        repo = s["repo"].split("/")[-1]
        marker = f"[#24d6a8]{gl['tri']}[/] " if i == sel else "  "
        box.compose_add_child(
            ClickStatic(
                app._paint(
                    f"\n{marker}{sw}  [#d9f7ff]{repo}[/]  {live}  [#6e8aa1]notify: {s['notification']}[/]"
                ),
                lambda i=i: app._select_sched(i),
            )
        )
        plural = "" if s["last_verdict_count"] == 1 else "s"
        box.compose_add_child(
            _S(
                app,
                f"  [#6e8aa1]{gl['dot']} {s['human']}[/] [#6e8aa1 i]{s['cron_expr']}[/]\n"
                f"  [#6e8aa1]last run {s['last_run']} {gl['pip']} "
                f"{s['last_verdict_count']} verdict{plural}[/]",
            )
        )
        # Per-row clickable action chips — each selects this row, then runs the
        # SAME action the schedule keybindings use (§5 mouse parity).
        acts = Horizontal(classes="sched-actions")
        for _lbl, _act in (
            (f"{gl['enter']} run", "action_primary"),
            ("t toggle", "action_toggle_schedule"),
            ("E edit", "action_edit_schedule"),
            ("del remove", "action_remove_schedule"),
        ):
            acts.compose_add_child(
                ClickStatic(
                    app._paint(f"  [#24d6a8 b]{_lbl}[/]"),
                    lambda i=i, a=_act: (
                        app._select_sched(i),
                        app.call_later(getattr(app, a)),
                    ),
                )
            )
        box.compose_add_child(acts)
    box.compose_add_child(
        _S(
            app,
            f"\n[#e3c26f]{gl['diamond']} one-time crontab install[/]\n"
            "[#a9bccd]Frontier Scout never edits your crontab for you. Add this single "
            "line once; the runner wakes every 15 min and fires only due schedules:[/]",
        )
    )
    box.compose_add_child(_S(app, f"  [#24d6a8]{data.crontab_line()}[/]"))
    box.compose_add_child(
        _S(
            app,
            "[#6e8aa1]Dry-run by default — scheduled scouts never drain API quota you "
            "forgot you configured. Flip a schedule to “live scan” to opt in.[/]",
        )
    )
    return box


def _receipts(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    rows = data.receipts()
    box = Vertical()
    box.compose_add_child(
        _head(
            app,
            "Receipts",
            "Every lab probe and trial leaves a recorded receipt — proof of what "
            "happened before you trusted it.",
        )
    )
    if not rows:
        box.compose_add_child(
            _S(app, "\n[#6e8aa1]No receipts yet — run a lab or trial.[/]")
        )
    tone = {"passed": "#24d6a8", "failed": "#ff6b6b", "report-only": "#7aa6ff"}
    for r in rows:
        col = tone.get(r["status"], "#6e8aa1")
        rt = f"  [#6e8aa1]{r['runtime']}[/]" if r["runtime"] else ""
        box.compose_add_child(
            _S(
                app,
                f"\n[{col}]{gl['dot']}[/] [#a9bccd]{r['tool_name']}[/]  [#6e8aa1]{r['kind']}[/]  "
                f"[{col}]{r['status']}[/]{rt}  [#6e8aa1]{r['when']}[/]",
            )
        )
        if r["note"]:
            box.compose_add_child(_S(app, f"  [#6e8aa1]{r['note']}[/]"))
    return box


def _guard(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    gd = app.state.guard_cache
    box = Vertical()
    box.compose_add_child(
        _head(
            app,
            "Guard",
            "Deterministic local policy checks — the Adoption Firewall. CI-friendly "
            "exit codes, never modifies your repo.",
        )
    )
    if gd is None:
        box.compose_add_child(
            _S(
                app,
                "\n[#6e8aa1]No guard run yet. Press [#24d6a8 b]r[/] to run the adoption firewall.[/]",
            )
        )
        box.compose_add_child(_scan_btn(app, "guard", "run guard"))
        return box
    box.compose_add_child(_scan_btn(app, "guard", "re-run"))
    if gd["fail"]:
        summary = (
            f"[#ff6b6b]{gl['cross']} exit 1[/] "
            f"[#6e8aa1]— {gd['high']} high, {gd['medium']} medium[/]"
        )
    else:
        summary = f"[#24d6a8]{gl['check']} exit 0[/] [#6e8aa1]— policy satisfied[/]"
    box.compose_add_child(_S(app, f"\n{summary}"))
    sev = {"high": "#ff6b6b", "medium": "#e3c26f", "low": "#6e8aa1"}
    for f in gd["findings"]:
        col = sev.get(f["severity"], "#6e8aa1")
        rule_col = "#24d6a8" if f["rule"] == "ok" else "#6e8aa1"
        box.compose_add_child(
            _S(
                app,
                f"\n[{col}]{f['severity']:<6}[/] [#d9f7ff]{f['tool']}[/] [{rule_col}]{f['rule']}[/]\n"
                f"  [#a9bccd]{f['detail']}[/]",
            )
        )
    return box


def _packs(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    rows = data.packs(app.state.languages)
    box = Vertical()
    box.compose_add_child(
        _head(
            app,
            "Scout Packs",
            "Living, curated source sets per domain — so you scout one focused feed, "
            "not five.",
        )
    )
    if not rows:
        box.compose_add_child(_S(app, "\n[#6e8aa1]No packs available.[/]"))
    maxv = max((p["sources"] for p in rows), default=1) or 1
    for p in rows:
        filled, empty = bar(p["sources"], maxv, 14, unicode=app.state.unicode)
        box.compose_add_child(
            _S(app, f"\n[#d9f7ff]{p['name']}[/]  [#6e8aa1]{p['slug']}[/]")
        )
        if p["desc"]:
            box.compose_add_child(_S(app, f"  [#6e8aa1]{p['desc']}[/]"))
        box.compose_add_child(
            _S(
                app,
                f"  [#6e8aa1]{p['seeds']} seeds {gl['vbar']} {p['sources']} sources[/]  "
                f"[#24d6a8]{filled}[/][#152232]{empty}[/]",
            )
        )
    return box


def _deps(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    rows = app.state.deps_cache
    box = Vertical()
    box.compose_add_child(
        _head(
            app,
            "Dependencies",
            "Meaningful upgrades for packages your repo actually imports — with why "
            "the upgrade works.",
        )
    )
    if rows is None:
        box.compose_add_child(
            _S(
                app,
                "\n[#6e8aa1]No dependency scan yet. Press [#24d6a8 b]r[/] to scan your manifests.[/]",
            )
        )
        box.compose_add_child(_scan_btn(app, "deps", "scan dependencies"))
        return box
    box.compose_add_child(_scan_btn(app, "deps", "re-scan"))
    if rows == ():
        box.compose_add_child(_S(app, "\n[#6e8aa1]No dependency findings.[/]"))
        return box
    vhex = {
        "adopt": "#24d6a8",
        "trial": "#e3c26f",
        "assess": "#7aa6ff",
        "hold": "#ff6b6b",
    }
    vlbl = {"adopt": "ADOPT", "trial": "TRIAL", "assess": "ASSESS", "hold": "HOLD"}
    for d in rows:
        v = d["verdict"]
        col = vhex.get(v, "#7aa6ff")
        lbl = vlbl.get(v, "ASSESS")
        box.compose_add_child(
            _S(
                app,
                f"\n[{col} b]{lbl:<6}[/] [#d9f7ff]{d['tool_name']}[/] "
                f"[#6e8aa1]{d['from_version']}{gl['arrow']}{d['to_version']}[/] "
                f"[#6e8aa1]{d['classification']}[/]",
            )
        )
        if d["why"]:
            box.compose_add_child(_S(app, f"  [#6e8aa1]{d['why']}[/]"))
    return box


def _reports(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    box = Vertical()
    box.compose_add_child(
        _head(
            app,
            "Reports",
            "Render the latest scan into a static, shareable radar. No server, no "
            "telemetry — just files.",
        )
    )
    verdicts = app.state.verdicts
    box.compose_add_child(
        _S(
            app,
            f"\n[#6e8aa1]Frontier Scout — weekly radar {gl['pip']}[/] [#d9f7ff]{app.state.repo_name}[/]",
        )
    )
    if verdicts:
        vhex = {
            "adopt": "#24d6a8",
            "trial": "#e3c26f",
            "assess": "#7aa6ff",
            "hold": "#ff6b6b",
        }
        vlbl = {"adopt": "ADOPT", "trial": "TRIAL", "assess": "ASSESS", "hold": "HOLD"}
        for v in verdicts[:4]:
            col = vhex.get(v.verdict, "#7aa6ff")
            lbl = vlbl.get(v.verdict, "ASSESS")
            box.compose_add_child(
                _S(
                    app,
                    f"  [{col} b]{lbl:<6}[/] [#a9bccd]{v.tool_name}[/]  [#6e8aa1]{v.category}[/]",
                )
            )
        extra = len(verdicts) - 4
        more = f"+ {extra} more {gl['pip']} " if extra > 0 else ""
        box.compose_add_child(
            _S(app, f"  [#6e8aa1]{more}{app.state.funnel.scanned} sources covered[/]")
        )
    else:
        box.compose_add_child(
            _S(app, "  [#6e8aa1]No scan yet — render after scouting.[/]")
        )
    outs = [
        ("briefing.html", "executive radar — shareable, offline"),
        ("briefing.md", "markdown digest for PRs / chat"),
        ("verdicts.json", "machine-readable verdict payload"),
        ("cost-breakdown.md", "per-pass token + dollar accounting"),
        ("judge-trace.md", "why each verdict landed where it did"),
    ]
    box.compose_add_child(
        _S(
            app,
            "\n" + "\n".join(f"[#a9bccd]{fn}[/]  [#6e8aa1]{d}[/]" for fn, d in outs),
        )
    )
    return box


def _settings(app: Any) -> Vertical:
    gl = glyphs(app.state.unicode)
    box = Vertical()
    box.compose_add_child(
        _head(
            app,
            "Settings",
            "Providers, security posture, the repo profile that personalizes your "
            "scout, and self-diagnostics.",
        )
    )
    if app.state.settings_cache is not None:
        box.compose_add_child(_scan_btn(app, "settings", "reload diagnostics"))

    # Provider — cheap env/which checks, safe inline on the render path.
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Provider[/]"))
    box.compose_add_child(
        _S(app, "[#6e8aa1]click a row or press [#24d6a8 b]P[/] to switch[/]")
    )
    active = str(getattr(app.state, "provider", "") or "").lower()
    for p in data.providers():
        present = p["present"]
        dot = f"[#24d6a8]{gl['dot']}[/]" if present else f"[#6e8aa1]{gl['ring']}[/]"
        bcol = "#24d6a8" if present else "#6e8aa1"
        mark = (
            " [#24d6a8]· active[/]"
            if active and active in (p["id"].lower(), p["name"].lower())
            else ""
        )
        box.compose_add_child(
            ClickStatic(
                app._paint(
                    f"{dot} [#d9f7ff]{p['name']}[/]  [{bcol}]{p['badge']}[/]  [#6e8aa1]{p['cost']}[/]{mark}"
                ),
                app.action_switch_provider,
            )
        )
        if p["detail"]:
            box.compose_add_child(_S(app, f"    [#6e8aa1]{p['detail']}[/]"))

    # Active tier models (defensive — never break the render path).
    try:
        from frontier_scout.providers import DEEP, FAST, resolve_provider

        _p = resolve_provider(active) if active and active != "local" else None
        if _p is not None:
            _fast = _p.model(FAST) or "(CLI default)"
            _deep = _p.model(DEEP) or "(CLI default)"
            box.compose_add_child(
                _S(
                    app,
                    f"    [#6e8aa1]tiers — scout (fast): [#a9bccd]{_fast}[/]  ·  "
                    f"judge (deep): [#a9bccd]{_deep}[/][/]",
                )
            )
    except Exception:  # noqa: BLE001 — Settings must never crash on provider probe
        pass

    # Security posture — locked architectural invariants (each verified against
    # the implementation) + the real read-only policy below.
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Security posture[/]"))
    invariants = [
        (
            "Repo source is never sent to an LLM",
            "Only filenames, dependency manifests/versions, import names, and "
            "derived structure ever leave your machine — never your source.",
        ),
        (
            "Fetched release text is treated as untrusted data",
            "Public content is data, never instructions — injection is contained.",
        ),
        (
            "Lab subprocesses run with a scrubbed environment",
            "Stripped env, wall-clock timeout, size caps, secret scan.",
        ),
    ]
    for label, detail in invariants:
        box.compose_add_child(
            _S(
                app,
                f"[#24d6a8]{gl['check']}[/] [#a9bccd]{label}[/]  [#6e8aa1]invariant[/]\n"
                f"    [#6e8aa1]{detail}[/]",
            )
        )

    cache = app.state.settings_cache
    if cache is None:
        box.compose_add_child(
            _S(app, "\n[#6e8aa1]Press [#24d6a8 b]r[/] to load policy and doctor.[/]")
        )
        box.compose_add_child(_scan_btn(app, "settings", "load diagnostics"))
        return box

    # Policy (read-only — the REAL Policy model fields; edit via the CLI).
    pol = cache.get("policy", {}) or {}

    def onoff(flag: bool) -> str:
        return "[#24d6a8]on[/]" if flag else "[#6e8aa1]off[/]"

    box.compose_add_child(
        _S(
            app,
            "\n[#24d6a8 b]Policy[/]  [#6e8aa1](read-only · edit via frontier-scout setup)[/]",
        )
    )
    box.compose_add_child(
        _S(
            app,
            f"  [#6e8aa1]strict[/] {onoff(pol.get('strict', False))}   "
            f"[#6e8aa1]require trial for dangerous capabilities[/] "
            f"{onoff(pol.get('require_trial_for_dangerous_capabilities', True))}",
        )
    )
    box.compose_add_child(
        _S(
            app,
            f"  [#6e8aa1]fail unknown capabilities[/] "
            f"{onoff(pol.get('fail_unknown_capabilities', True))}   "
            f"[#6e8aa1]allow adopt without lab (low risk)[/] "
            f"{onoff(pol.get('allow_adopt_without_lab_for_low_risk', False))}",
        )
    )
    npacks = len(pol.get("packs", {}) or {})
    if npacks:
        box.compose_add_child(
            _S(app, f"  [#6e8aa1]packs configured[/] [#a9bccd]{npacks}[/]")
        )

    # Repo profile (read-only — what personalizes the scout).
    prof = cache.get("profile", {}) or {}
    box.compose_add_child(
        _S(
            app,
            "\n[#24d6a8 b]Repo profile[/]  [#6e8aa1]— what personalizes your scout[/]",
        )
    )
    for label, key in (
        ("languages", "languages"),
        ("frameworks", "frameworks"),
        ("managers", "managers"),
        ("agent configs", "agent_configs"),
    ):
        vals = ", ".join(prof.get(key, []) or []) or "—"
        box.compose_add_child(_S(app, f"  [#6e8aa1]{label}[/] [#a9bccd]{vals}[/]"))
    risks = prof.get("risk_flags", []) or []
    if risks:
        box.compose_add_child(
            _S(app, f"  [#e3c26f]risk flags[/] [#a9bccd]{', '.join(risks)}[/]")
        )

    # Doctor.
    box.compose_add_child(_S(app, "\n[#24d6a8 b]Doctor[/]"))
    marks = {
        "ok": f"[#24d6a8]{gl['check']}[/]",
        "warn": f"[#e3c26f]{gl['diamond']}[/]",
        "fail": f"[#ff6b6b]{gl['cross']}[/]",
    }
    for c in cache.get("doctor", []):
        mk = marks.get(c.get("status", "ok"), gl["pip"])
        box.compose_add_child(
            _S(
                app,
                f"{mk} [#a9bccd]{c.get('name','')}[/]  [#6e8aa1]{c.get('detail','')}[/]",
            )
        )
        fix = c.get("fix", "")
        if fix:
            box.compose_add_child(_S(app, f"    [#6e8aa1]fix: {fix}[/]"))

    # Danger row — real keybindings (discoverable affordances, not fake buttons).
    box.compose_add_child(
        _S(
            app,
            f"\n[#6e8aa1]{gl['pip']} [#24d6a8 b]R[/] reconfigure   "
            f"{gl['pip']} [#24d6a8 b]X[/] clear history   "
            f"{gl['pip']} [#24d6a8 b]q[/] quit[/]",
        )
    )
    return box


def _placeholder(app: Any) -> Vertical:
    box = Vertical()
    box.compose_add_child(_S(app, f"[#6e8aa1]{app.state.tab}[/]"))
    return box


_BUILDERS = {
    "scout": _scout,
    "schedule": _schedule,
    "receipts": _receipts,
    "guard": _guard,
    "packs": _packs,
    "deps": _deps,
    "reports": _reports,
    "settings": _settings,
}
