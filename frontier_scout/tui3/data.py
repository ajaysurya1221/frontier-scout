"""Mission Control (tui3) — data adapter.

The single bridge between the real Frontier Scout backends and the immutable
view-model in ``state.py``. Every function is defensive (getattr / dict
fallbacks) so backend shape drift degrades to an empty/"−" cell rather than a
crash — the TUI must never break on data. No Textual imports here.

Field names verified against the live backends:
  Schedule(id, repo, cron_expr, notification, last_run, last_result_dir,
           last_verdict_count, disabled, live)
  PolicyFinding(severity, rule_id, message, tool_name)
  Policy(require_trial_for_dangerous_capabilities, fail_unknown_capabilities,
         allow_adopt_without_lab_for_low_risk, strict, packs)
  packs.pack_summary_rows() -> [{slug, display_name, seed_count, source_count}]
  doctor Check(name, status['ok'|'warn'|'fail'], detail, fix)
  store.list_trial_summaries(limit) -> list[dict]
  profile(repo, languages, frameworks, package_managers, agent_configs, risk_flags, …)

Decisions honoured: D3 Ask is OFFLINE-ONLY (never calls a provider);
D4 coverage = real aggregate funnel + packs; D5 policy read-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from frontier_scout.tui3.state import AppState, Funnel, Verdict


def _g(obj: Any, name: str, default: Any = "") -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _repo_name(repo: str | Path) -> str:
    s = str(repo or ".")
    if s in (".", ""):
        return Path.cwd().name
    return Path(s).name or s


def _humanize_cron(expr: str) -> str:
    return {
        "@hourly": "Every hour",
        "@daily": "Every day · 00:00",
        "@weekly": "Weekly · Sun 00:00",
        "@monthly": "Monthly · 1st",
        "0 7 * * 1-5": "Weekdays · 07:00",
    }.get(expr, expr)


# ── Verdict projection ───────────────────────────────────────────────────────
def _verdicts_from_payload(payload: dict[str, Any]) -> tuple[Verdict, ...]:
    rows = payload.get("verdicts") or []
    out: list[Verdict] = []
    for d in rows:
        if not isinstance(d, dict):
            continue
        kind = "dep" if (d.get("from_version") or d.get("classification")) else "tool"
        out.append(Verdict.from_payload(d, kind=kind))
    return tuple(out)


# ── Initial state ────────────────────────────────────────────────────────────
def initial_state(repo: Path | None = None, *, demo: bool = False) -> AppState:
    repo_path = str((repo or Path.cwd()).resolve())
    languages: tuple[str, ...] = ()
    verdicts: tuple[Verdict, ...] = ()
    funnel = Funnel()
    try:
        from frontier_scout import store

        store.init_home()
        payload = store.latest_scan(repo_path)
        if payload:
            verdicts = _verdicts_from_payload(payload)
            funnel = Funnel.from_payload(payload)
            languages = tuple(str(x) for x in ((payload.get("stack") or {}).get("languages") or []))
    except Exception:  # noqa: BLE001 — opening state must never crash
        pass
    return AppState(
        repo=repo_path,
        repo_name=_repo_name(repo_path),
        languages=languages,
        provider=_detect_provider(demo=demo),
        verdicts=verdicts,
        funnel=funnel,
        demo=demo,
        unread=_unread_count(),
    )


def run_scan(repo: str, *, dry_run: bool, scope: str, reporter: Any = None) -> dict[str, Any]:
    """Run a real scout scan (caller is on a worker). Returns projected pieces."""
    from frontier_scout.scout import run_scan as _run

    pack = None if scope in ("all", "deps") else scope
    payload = _run(
        repo=Path(repo), dry_run=dry_run, persist=not dry_run, pack=pack, reporter=reporter
    )
    return {
        "verdicts": _verdicts_from_payload(payload),
        "funnel": Funnel.from_payload(payload),
        "languages": tuple(str(x) for x in ((payload.get("stack") or {}).get("languages") or [])),
    }


# ── Providers ────────────────────────────────────────────────────────────────
def _detect_provider(*, demo: bool) -> str:
    if demo:
        return "local"
    import os
    import shutil

    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if shutil.which("claude"):
        return "claude-cli"
    return "local"


def providers() -> list[dict[str, Any]]:
    import os
    import shutil

    a = bool(os.environ.get("ANTHROPIC_API_KEY"))
    o = bool(os.environ.get("OPENAI_API_KEY"))
    cc = bool(shutil.which("claude"))
    cx = bool(shutil.which("codex"))
    return [
        {"id": "anthropic", "name": "Anthropic API", "present": a,
         "badge": "key present" if a else "no key", "cost": "~$0.34 / scan",
         "detail": "ANTHROPIC_API_KEY " + ("found" if a else "not set")},
        {"id": "claude-cli", "name": "Claude Code CLI", "present": cc,
         "badge": "detected" if cc else "not found", "cost": "$0 marginal",
         "detail": "`claude` " + ("on PATH" if cc else "not on PATH")},
        {"id": "openai", "name": "OpenAI API", "present": o,
         "badge": "configured" if o else "not configured", "cost": "~$0.05 / scan",
         "detail": "OPENAI_API_KEY " + ("found" if o else "not set")},
        {"id": "codex-cli", "name": "Codex CLI", "present": cx,
         "badge": "detected" if cx else "not found", "cost": "$0 marginal",
         "detail": "`codex` " + ("on PATH" if cx else "not on PATH")},
        {"id": "local", "name": "Local · offline", "present": True, "badge": "always on",
         "cost": "free", "detail": "Bundled fixtures, no network"},
    ]


def _unread_count() -> int:
    try:
        from frontier_scout import notifications

        return int(notifications.unread_count())
    except Exception:  # noqa: BLE001
        return 0


def notifications_list() -> list[dict[str, Any]]:
    try:
        from frontier_scout import notifications

        rows = notifications.list_notifications(False) or []
        return [
            {"text": str(_g(n, "text") or _g(n, "message")), "repo": str(_g(n, "repo")),
             "when": str(_g(n, "when") or _g(n, "created_at")), "read": bool(_g(n, "read", False))}
            for n in rows
        ]
    except Exception:  # noqa: BLE001
        return []


# ── Schedules ────────────────────────────────────────────────────────────────
def schedules() -> list[dict[str, Any]]:
    try:
        from frontier_scout import scheduling

        rows = scheduling.load_schedules() or []
        return [
            {"id": str(_g(s, "id")), "repo": str(_g(s, "repo")),
             "cron_expr": str(_g(s, "cron_expr")), "human": _humanize_cron(str(_g(s, "cron_expr"))),
             "notification": str(_g(s, "notification", "system")),
             "live": bool(_g(s, "live", False)), "disabled": bool(_g(s, "disabled", False)),
             "last_run": str(_g(s, "last_run", "never") or "never"),
             "last_verdict_count": int(_g(s, "last_verdict_count", 0) or 0)}
            for s in rows
        ]
    except Exception:  # noqa: BLE001
        return []


def crontab_line() -> str:
    try:
        from frontier_scout import scheduling

        return str(scheduling.crontab_line())
    except Exception:  # noqa: BLE001
        return '*/15 * * * * "~/.frontier-scout/cron-runner.sh"'


# ── Receipts (real) ──────────────────────────────────────────────────────────
def receipts(limit: int = 50) -> list[dict[str, Any]]:
    try:
        from frontier_scout import store

        rows = store.list_trial_summaries(limit) or []
        return [
            {"tool_name": str(_g(r, "tool_name")),
             "kind": str(_g(r, "kind", _g(r, "requested_action", "trial"))),
             "status": str(_g(r, "status", "—")), "runtime": str(_g(r, "runtime", "")),
             "when": str(_g(r, "when", _g(r, "finished_at", _g(r, "created_at", "")))),
             "note": str(_g(r, "note", _g(r, "summary", "")))}
            for r in rows
        ]
    except Exception:  # noqa: BLE001
        return []


# ── Guard ────────────────────────────────────────────────────────────────────
def guard(repo: str, *, strict: bool) -> dict[str, Any]:
    try:
        from frontier_scout.guard import run_guard

        findings = run_guard(Path(repo), strict=strict) or []
        rows = [
            {"severity": str(_g(f, "severity", "low")), "rule": str(_g(f, "rule_id", "")),
             "tool": str(_g(f, "tool_name", "")), "detail": str(_g(f, "message", ""))}
            for f in findings
        ]
        high = sum(1 for r in rows if r["severity"] == "high")
        med = sum(1 for r in rows if r["severity"] == "medium")
        return {"findings": rows, "high": high, "medium": med,
                "fail": high > 0 or (strict and med > 0)}
    except Exception:  # noqa: BLE001
        return {"findings": [], "high": 0, "medium": 0, "fail": False}


# ── Packs (use the render-ready summary rows) ────────────────────────────────
def packs(languages: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    try:
        from frontier_scout import packs as packs_mod

        rows = packs_mod.pack_summary_rows() or []
        out = []
        for r in rows:
            out.append({
                "slug": str(_g(r, "slug")), "name": str(_g(r, "display_name", _g(r, "slug"))),
                "seeds": int(_g(r, "seed_count", 0) or 0),
                "sources": int(_g(r, "source_count", 0) or 0),
                "desc": str(_g(r, "description", "")),
            })
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Dependencies ─────────────────────────────────────────────────────────────
def dependencies(repo: str) -> list[dict[str, Any]]:
    try:
        from frontier_scout.dependencies import run_dependency_scan

        result = run_dependency_scan(Path(repo), persist=False)
        findings = result.get("findings", []) if isinstance(result, dict) else (
            _g(result, "findings", []) or [])
        out = []
        for d in findings:
            why = _g(d, "why_fit", None)
            why_text = (why[0] if isinstance(why, list) and why else str(_g(d, "why", "")))
            out.append({
                "tool_name": str(_g(d, "package_name", _g(d, "tool_name", ""))),
                "from_version": str(_g(d, "from_version", "")),
                "to_version": str(_g(d, "to_version", "")),
                "classification": str(_g(d, "classification", "")),
                "why": str(why_text), "verdict": str(_g(d, "verdict", "assess"))})
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Settings: policy / profile / doctor ──────────────────────────────────────
def policy(repo: str) -> dict[str, Any]:
    try:
        from frontier_scout.policy import load_policy

        return load_policy(Path(repo)).model_dump()
    except Exception:  # noqa: BLE001
        return {}


def doctor() -> list[dict[str, Any]]:
    try:
        from frontier_scout.doctor import run_doctor

        return [
            {"name": str(_g(c, "name")), "status": str(_g(c, "status", "ok")),
             "detail": str(_g(c, "detail", "")), "fix": str(_g(c, "fix", ""))}
            for c in (run_doctor() or [])
        ]
    except Exception:  # noqa: BLE001
        return []


def repo_profile(repo: str) -> dict[str, Any]:
    try:
        from frontier_scout.profile import build_scout_profile

        p = build_scout_profile(Path(repo))
        return {
            "languages": list(_g(p, "languages", []) or []),
            "frameworks": list(_g(p, "frameworks", []) or []),
            "managers": list(_g(p, "package_managers", []) or []),
            "agent_configs": list(_g(p, "agent_configs", []) or []),
            "risk_flags": list(_g(p, "risk_flags", []) or []),
        }
    except Exception:  # noqa: BLE001
        return {}


# ── Offline Ask (deterministic; never calls a provider — decision D3) ────────
def ask_offline(v: Verdict, question: str, repo_name: str) -> str:
    parts = [f"{v.tool_name} is an {v.verdict.upper()} for {repo_name} — fit {v.fit}, risk {v.risk}."]
    if v.fit_reasons:
        parts.append(v.fit_reasons[0])
    if v.concerns:
        c = v.concerns[0]
        parts.append(f"Watch ({c.severity}): {c.evidence}")
    if v.next_safe_step:
        parts.append(f"Next: {v.next_safe_step}")
    parts.append("(offline answer — connect a provider for a live, tailored reply.)")
    return " ".join(p for p in parts if p)
