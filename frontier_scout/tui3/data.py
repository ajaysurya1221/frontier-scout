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
            languages = tuple(
                str(x) for x in ((payload.get("stack") or {}).get("languages") or [])
            )
    except Exception:  # noqa: BLE001 — opening state must never crash
        pass
    prov_name, prov_reason = _detect_provider(demo=demo)
    return AppState(
        repo=repo_path,
        repo_name=_repo_name(repo_path),
        languages=languages,
        provider=prov_name,
        provider_reason=prov_reason,
        verdicts=verdicts,
        funnel=funnel,
        demo=demo,
        unread=_unread_count(),
    )


def run_scan(
    repo: str, *, dry_run: bool, scope: str, reporter: Any = None
) -> dict[str, Any]:
    """Run a real scout scan (caller is on a worker). Returns projected pieces."""
    from frontier_scout.scout import run_scan as _run

    pack = None if scope in ("all", "deps") else scope
    payload = _run(
        repo=Path(repo),
        dry_run=dry_run,
        persist=not dry_run,
        pack=pack,
        reporter=reporter,
    )
    return {
        "verdicts": _verdicts_from_payload(payload),
        "funnel": Funnel.from_payload(payload),
        "languages": tuple(
            str(x) for x in ((payload.get("stack") or {}).get("languages") or [])
        ),
    }


def list_repos(current: str | None = None) -> list[dict[str, Any]]:
    """Known repos for the switcher: schedule repos + the current repo, deduped.

    Source of truth is ``scheduling.load_schedules()`` (each Schedule.repo); we
    fold in ``current`` so there is always at least one entry. No backend
    ``list_repos`` exists — this is the only no-new-API path (handoff §9). Each
    entry: ``{"name", "path"}``.
    """
    seen: dict[str, dict[str, Any]] = {}

    def _add(raw: Any) -> None:
        if not raw:
            return
        try:
            p = str(Path(str(raw)).expanduser().resolve())
        except Exception:  # noqa: BLE001
            p = str(raw)
        seen.setdefault(p, {"name": _repo_name(p), "path": p})

    _add(current)
    try:
        from frontier_scout import scheduling

        for s in scheduling.load_schedules() or []:
            raw = getattr(s, "repo", None)
            if raw is None and isinstance(s, dict):
                raw = s.get("repo")
            _add(raw)
    except Exception:  # noqa: BLE001 — the switcher must never crash
        pass
    return list(seen.values())


# ── Providers ────────────────────────────────────────────────────────────────
def _detect_provider(*, demo: bool) -> tuple[str, str]:
    """Return (provider_name, reason) via the single selection ladder so the
    header can never disagree with what a scan uses. Never crashes."""
    if demo:
        return ("local", "demo")
    try:
        from frontier_scout.providers import select

        s = select.select(interactive=False)
        return ("local", "none") if s.reason == "none" else (s.name, s.reason)
    except Exception:  # noqa: BLE001 — opening state must never crash
        return ("local", "none")


def providers() -> list[dict[str, Any]]:
    import os
    import shutil

    a = bool(os.environ.get("ANTHROPIC_API_KEY"))
    o = bool(os.environ.get("OPENAI_API_KEY"))
    cc = bool(shutil.which("claude"))
    cx = bool(shutil.which("codex"))
    return [
        {
            "id": "anthropic",
            "name": "Anthropic API",
            "present": a,
            "badge": "key present" if a else "no key",
            "cost": "~$0.34 / scan",
            "detail": "ANTHROPIC_API_KEY " + ("found" if a else "not set"),
        },
        {
            "id": "claude-cli",
            "name": "Claude Code CLI",
            "present": cc,
            "badge": "detected" if cc else "not found",
            "cost": "$0 marginal",
            "detail": "`claude` " + ("on PATH" if cc else "not on PATH"),
        },
        {
            "id": "openai",
            "name": "OpenAI API",
            "present": o,
            "badge": "configured" if o else "not configured",
            "cost": "~$0.05 / scan",
            "detail": "OPENAI_API_KEY " + ("found" if o else "not set"),
        },
        {
            "id": "openai-compatible",
            "name": "Custom endpoint",
            "present": bool(
                os.environ.get("FRONTIER_SCOUT_OPENAI_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
            ),
            "badge": (
                "configured"
                if (
                    os.environ.get("FRONTIER_SCOUT_OPENAI_BASE_URL")
                    or os.environ.get("OPENAI_BASE_URL")
                )
                else "not set"
            ),
            "cost": "your gateway",
            "detail": "OPENAI_BASE_URL "
            + (
                "set"
                if (
                    os.environ.get("FRONTIER_SCOUT_OPENAI_BASE_URL")
                    or os.environ.get("OPENAI_BASE_URL")
                )
                else "not set"
            ),
        },
        {
            "id": "codex-cli",
            "name": "Codex CLI",
            "present": cx,
            "badge": "detected" if cx else "not found",
            "cost": "$0 marginal",
            "detail": "`codex` " + ("on PATH" if cx else "not on PATH"),
        },
        {
            "id": "local",
            "name": "Local · offline",
            "present": True,
            "badge": "always on",
            "cost": "free",
            "detail": "Bundled fixtures, no network",
        },
    ]


def provider_choices(current: str | None = None) -> list[dict[str, Any]]:
    """Switchable providers with human labels + availability (for the switcher)."""
    try:
        from frontier_scout.providers import available_providers

        avail = set(available_providers())
    except Exception:  # noqa: BLE001 — the switcher must never crash
        avail = set()
    labels = {
        "anthropic": ("Anthropic API", "set ANTHROPIC_API_KEY"),
        "openai": ("OpenAI API", "set OPENAI_API_KEY"),
        "openai-compatible": ("Custom endpoint (your gateway)", "set OPENAI_BASE_URL"),
        "claude-cli": ("Claude (CLI subscription)", "log in to the claude CLI"),
        "codex-cli": ("Codex (CLI subscription)", "log in to the codex CLI"),
    }
    cur = (current or "").lower()
    out: list[dict[str, Any]] = []
    for pid, (label, fix) in labels.items():
        ok = pid in avail
        out.append(
            {
                "id": pid,
                "label": label,
                "available": ok,
                "hint": "" if ok else fix,
                "active": cur == pid,
            }
        )
    return out


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
            {
                "text": str(_g(n, "text") or _g(n, "message")),
                "repo": str(_g(n, "repo")),
                "when": str(_g(n, "when") or _g(n, "created_at")),
                "read": bool(_g(n, "read", False)),
            }
            for n in rows
        ]
    except Exception:  # noqa: BLE001
        return []


def notifications_clear() -> int:
    """Clear ALL notifications. Returns the count cleared. FREE local DB write.

    A benign, explicit-keypress local write (no spend, no network): it only
    deletes rows from ``~/.frontier-scout``'s notifications store. Defensive —
    mirrors the ``notifications_list`` try/except style; degrades to 0 on any
    backend hiccup rather than raising.
    """
    try:
        from frontier_scout import notifications

        return int(notifications.clear_all())
    except Exception:  # noqa: BLE001
        return 0


# ── Schedules ────────────────────────────────────────────────────────────────
def schedules() -> list[dict[str, Any]]:
    try:
        from frontier_scout import scheduling

        rows = scheduling.load_schedules() or []
        return [
            {
                "id": str(_g(s, "id")),
                "repo": str(_g(s, "repo")),
                "cron_expr": str(_g(s, "cron_expr")),
                "human": _humanize_cron(str(_g(s, "cron_expr"))),
                "notification": str(_g(s, "notification", "system")),
                "live": bool(_g(s, "live", False)),
                "disabled": bool(_g(s, "disabled", False)),
                "last_run": str(_g(s, "last_run", "never") or "never"),
                "last_verdict_count": int(_g(s, "last_verdict_count", 0) or 0),
            }
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


# ── Schedule mutations (FREE local JSON writes — no spend, no network) ────────
# Toggle + remove only rewrite ``~/.frontier-scout/schedules.json``. They never
# run a scan, never touch a provider, never reach the network. ``schedule_run``
# is the ONLY spend path here, and it honours the ``dry_run`` the *caller*
# passes — the cost gate lives in the app, never inside these wrappers. All
# three are defensive (mirror the ``schedules()`` try/except style): a backend
# hiccup degrades to ``{"ok": False, "reason": …}`` rather than crashing.
def schedule_toggle(schedule_id: str) -> dict[str, Any]:
    """Flip a schedule's ``disabled`` flag in place. FREE local JSON write.

    Loads the schedules, finds the one with ``schedule_id``, flips its
    ``disabled`` field (mutating the non-frozen dataclass) and saves. Returns
    the NEW ``disabled`` value so the caller can report it. Never raises.
    """
    try:
        from frontier_scout import scheduling

        rows = scheduling.load_schedules() or []
        for s in rows:
            if str(_g(s, "id")) == str(schedule_id):
                s.disabled = not bool(_g(s, "disabled", False))
                scheduling.save_schedules(rows)
                return {
                    "ok": True,
                    "disabled": bool(s.disabled),
                    "repo": _repo_name(_g(s, "repo", "")),
                }
        return {"ok": False, "reason": "schedule not found"}
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {"ok": False, "reason": str(exc)}


def schedule_remove(schedule_id: str) -> dict[str, Any]:
    """Remove a schedule by id. FREE local JSON write (destructive but cheap).

    Resolves the basename BEFORE the delete so the result can name what went.
    Delegates to ``scheduling.remove_schedule`` (returns True when one was
    removed). Never raises.
    """
    try:
        from frontier_scout import scheduling

        repo = ""
        for s in scheduling.load_schedules() or []:
            if str(_g(s, "id")) == str(schedule_id):
                repo = _repo_name(_g(s, "repo", ""))
                break
        ok = bool(scheduling.remove_schedule(str(schedule_id)))
        return {"ok": ok, "repo": repo}
    except Exception:  # noqa: BLE001 — actions must never crash the UI
        return {"ok": False, "repo": ""}


def schedule_run(schedule_id: str, *, dry_run: bool) -> dict[str, Any]:
    """Run the scout for a single schedule. The ONLY spend path here.

    Loads the schedule, runs it through the SAME ``run_scan`` the app's scout
    uses (``scope="all"``), and HONOURS the ``dry_run`` the caller passes —
    never forces it. ``dry_run=True`` is the seeded, no-spend, no-network path;
    ``dry_run=False`` spends (the app gates that before ever calling here).
    Best-effort records the run against the schedule (``record_run``) so the
    Schedule tab's "last run" reflects it; a record_run failure NEVER aborts the
    run (it is wrapped). Returns a render-honest dict. Never raises.
    """
    try:
        from frontier_scout import scheduling

        sched = None
        for s in scheduling.load_schedules() or []:
            if str(_g(s, "id")) == str(schedule_id):
                sched = s
                break
        if sched is None:
            return {"ok": False, "reason": "schedule not found"}

        repo = str(_g(sched, "repo", "")) or "."
        result = run_scan(repo, dry_run=dry_run, scope="all")
        funnel = result.get("funnel")
        verdicts = int(_g(funnel, "verdicts", 0) or 0)
        cost = float(_g(funnel, "cost", 0.0) or 0.0)

        # Best-effort: stamp last_run on the schedule. A real persisted scan
        # lands under the store's runs dir; we point record_run there. Any
        # failure here is swallowed — it must never abort a completed run.
        try:
            result_dir = scheduling.runs_dir() / str(_g(sched, "id", "run"))
            scheduling.record_run(sched, result_dir=result_dir, verdict_count=verdicts)
        except Exception:  # noqa: BLE001 — record_run is best-effort only
            pass

        return {
            "ok": True,
            "repo": _repo_name(repo),
            "verdicts": verdicts,
            "cost": cost,
            "dry_run": dry_run,
        }
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {"ok": False, "reason": str(exc)}


def schedule_create(
    repo: str, cron_expr: str = "@daily", notification: str = "file", live: bool = False
) -> dict[str, Any]:
    """Create a new schedule. FREE local JSON write (no spend, no network).

    Validates the cron expression first (``is_valid_cron_expr``) so a malformed
    expr is rejected BEFORE ``add_schedule`` writes anything; then delegates to
    ``scheduling.add_schedule`` (which appends + persists ``schedules.json``).
    The editor screen already normalises the cron, but we re-validate here so
    the wrapper is safe to call directly. Returns a render-ready dict; defensive
    — any failure degrades to ``{"ok": False, "reason": …}`` rather than raising.
    """
    try:
        from frontier_scout import scheduling

        if not scheduling.is_valid_cron_expr(cron_expr):
            return {"ok": False, "reason": "invalid cron"}
        scheduling.add_schedule(
            repo, cron_expr=cron_expr, notification=notification, live=bool(live)
        )
        return {
            "ok": True,
            "repo": _repo_name(repo),
            "cron": cron_expr,
            "live": bool(live),
        }
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {"ok": False, "reason": str(exc)}


def schedule_update(
    schedule_id: str, repo: str, cron_expr: str, notification: str, live: bool
) -> dict[str, Any]:
    """Edit an existing schedule in place. FREE local JSON write.

    Loads the schedules, finds the one with ``schedule_id``, mutates its
    repo/cron_expr/notification/live fields (the dataclass is non-frozen) and
    saves the whole list back. Returns ``{"ok": False, "reason": "not found"}``
    when no schedule matches; otherwise ``{"ok": True, "repo": <basename>}``.
    Defensive — any failure degrades to ``{"ok": False, "reason": …}``; never
    raises.
    """
    try:
        from frontier_scout import scheduling

        rows = scheduling.load_schedules() or []
        for s in rows:
            if str(_g(s, "id")) == str(schedule_id):
                s.repo = str(repo)
                s.cron_expr = str(cron_expr)
                s.notification = str(notification)
                s.live = bool(live)
                scheduling.save_schedules(rows)
                return {"ok": True, "repo": _repo_name(repo)}
        return {"ok": False, "reason": "not found"}
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {"ok": False, "reason": str(exc)}


# ── Receipts (real) ──────────────────────────────────────────────────────────
def receipts(limit: int = 50) -> list[dict[str, Any]]:
    try:
        from frontier_scout import store

        rows = store.list_trial_summaries(limit) or []
        return [
            {
                "tool_name": str(_g(r, "tool_name")),
                "kind": str(_g(r, "kind", _g(r, "requested_action", "trial"))),
                "status": str(_g(r, "status", "—")),
                "runtime": str(_g(r, "runtime", "")),
                "when": str(
                    _g(r, "when", _g(r, "finished_at", _g(r, "created_at", "")))
                ),
                "note": str(_g(r, "note", _g(r, "summary", ""))),
            }
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
            {
                "severity": str(_g(f, "severity", "low")),
                "rule": str(_g(f, "rule_id", "")),
                "tool": str(_g(f, "tool_name", "")),
                "detail": str(_g(f, "message", "")),
            }
            for f in findings
        ]
        high = sum(1 for r in rows if r["severity"] == "high")
        med = sum(1 for r in rows if r["severity"] == "medium")
        return {
            "findings": rows,
            "high": high,
            "medium": med,
            "fail": high > 0 or (strict and med > 0),
        }
    except Exception:  # noqa: BLE001
        return {"findings": [], "high": 0, "medium": 0, "fail": False}


# ── Packs (use the render-ready summary rows) ────────────────────────────────
def packs(languages: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    try:
        from frontier_scout import packs as packs_mod

        rows = packs_mod.pack_summary_rows() or []
        out = []
        for r in rows:
            out.append(
                {
                    "slug": str(_g(r, "slug")),
                    "name": str(_g(r, "display_name", _g(r, "slug"))),
                    "seeds": int(_g(r, "seed_count", 0) or 0),
                    "sources": int(_g(r, "source_count", 0) or 0),
                    "desc": str(_g(r, "description", "")),
                }
            )
        return out
    except Exception:  # noqa: BLE001
        return []


def packs_refresh(*, discover: bool = False) -> dict[str, Any]:
    """Refresh pack candidates — mirrors ``cli.py``'s ``packs refresh`` handler.

    ``discover=False`` is FREE + LOCAL + GUARANTEED OFFLINE: it only materialises
    seed candidates and writes them to the store. ``discover=True`` may HTTP GET
    the MCP registry (network) but spends NO money and runs NO LLM — the only
    network gate is ``candidate_rows_for_pack(..., discover=True)`` reaching out
    when a pack carries ``discovery.mcp_registry_url``.

    Ensures the built-in packs exist (so ``list_packs`` isn't empty on first
    run), then for each pack builds a ``ScoutPack`` model and saves every
    candidate row. Per-pack failures are caught and skipped (the refresh as a
    whole keeps going). Returns a render-ready summary; on a top-level failure
    returns ``{"ok": False, "reason": str(exc)}``. Defensive — never raises.
    """
    try:
        from frontier_scout import packs as packs_mod
        from frontier_scout import store
        from frontier_scout.packs import ScoutPack

        store.save_builtin_packs_if_empty()
        per_pack: list[dict[str, Any]] = []
        total = 0
        for pack in store.list_packs() or []:
            try:
                pack_model = ScoutPack(**(pack.get("definition") or {}))
                count = 0
                for candidate in packs_mod.candidate_rows_for_pack(
                    pack_model, discover=discover
                ):
                    store.save_pack_candidate(candidate)
                    count += 1
                name = str(_g(pack, "display_name", _g(pack, "slug", "pack")))
                per_pack.append({"name": name, "count": count})
                total += count
            except Exception:  # noqa: BLE001 — one bad pack must not abort the rest
                continue
        return {"ok": True, "discover": discover, "total": total, "packs": per_pack}
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {"ok": False, "reason": str(exc)}


# ── Dependencies ─────────────────────────────────────────────────────────────
def dependencies(repo: str) -> list[dict[str, Any]]:
    try:
        from frontier_scout.dependencies import run_dependency_scan

        result = run_dependency_scan(Path(repo), persist=False)
        findings = (
            result.get("findings", [])
            if isinstance(result, dict)
            else (_g(result, "findings", []) or [])
        )
        out = []
        for d in findings:
            why = _g(d, "why_fit", None)
            why_text = (
                why[0] if isinstance(why, list) and why else str(_g(d, "why", ""))
            )
            out.append(
                {
                    "tool_name": str(_g(d, "package_name", _g(d, "tool_name", ""))),
                    "from_version": str(_g(d, "from_version", "")),
                    "to_version": str(_g(d, "to_version", "")),
                    "classification": str(_g(d, "classification", "")),
                    "why": str(why_text),
                    "verdict": str(_g(d, "verdict", "assess")),
                }
            )
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
            {
                "name": str(_g(c, "name")),
                "status": str(_g(c, "status", "ok")),
                "detail": str(_g(c, "detail", "")),
                "fix": str(_g(c, "fix", "")),
            }
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


# ── Guard-railed Scout actions (run on a worker, never on the render path) ───
def _target_for(v: Verdict) -> str:
    """The dossier/implement target: prefer the source URL, else the tool name."""
    return str(_g(v, "source_url", "")) or str(_g(v, "tool_name", "")) or "tool"


def dossier(verdict: Verdict, repo: str) -> dict[str, Any]:
    """Build an adoption dossier (FREE — no spend, no network, no LLM).

    Runs ``dossier.build_dossier`` on the caller's worker thread (it calls
    ``build_scout_profile`` and is too slow for the render path). Returns a
    projected, render-ready dict of str/list values. Defensive — never raises;
    returns ``{}`` on any failure.
    """
    try:
        from frontier_scout.dossier import build_dossier

        target = _target_for(verdict)
        payload = build_dossier(target, repo=Path(repo)) or {}
        prof = payload.get("repo_profile") or {}
        return {
            "tool_name": str(_g(payload, "tool_name", _g(verdict, "tool_name", ""))),
            "verdict": str(_g(payload, "verdict", _g(verdict, "verdict", ""))),
            "fit": str(_g(payload, "fit", _g(verdict, "fit", ""))),
            "risk": str(_g(payload, "risk", _g(verdict, "risk", ""))),
            "source_trust": str(_g(payload, "source_trust", "")),
            "policy": str(_g(payload, "policy_summary", "")),
            "why": str(_g(payload, "why_trending", "")),
            "fit_reasons": [str(x) for x in (_g(payload, "fit_reasons", ()) or ())],
            "gaps": [str(x) for x in (_g(payload, "unknowns", ()) or ())],
            "alternatives": [str(x) for x in (_g(payload, "alternatives", ()) or ())],
            "next_step": str(_g(payload, "next_safe_step", "")),
            "profile_languages": [str(x) for x in (_g(prof, "languages", ()) or ())],
            "receipt_path": str(_g(payload, "receipt_path", "")),
        }
    except Exception:  # noqa: BLE001 — actions must never crash the UI
        return {}


def implement(verdict: Verdict, repo: str, *, dry_run: bool) -> dict[str, Any]:
    """Implement & test the selected tool in an isolated worktree.

    ``dry_run=True`` is a true no-spend / no-mutation path: the backend returns
    a synthetic "prepared" result BEFORE creating a provider or writing into the
    real working tree (the change is staged in an isolated copy and discarded).
    Runs on the caller's worker thread. Returns a projected dict; defensive —
    never raises; returns an ``error`` dict on failure.
    """
    try:
        from frontier_scout.implement import run_implement

        result = run_implement(
            repo=Path(repo),
            tool_name=str(_g(verdict, "tool_name", "tool")),
            dry_run=dry_run,
        )
        d = result.to_dict() if hasattr(result, "to_dict") else {}
        return {
            "status": str(_g(d, "status", _g(result, "status", "error"))),
            "summary": str(_g(d, "summary", "")),
            "what_you_get": str(_g(d, "what_you_get", "")),
            "files": [str(x) for x in (_g(d, "files_changed", ()) or ())],
            "diff": str(_g(d, "diff", "")),
            "test_output": str(_g(d, "test_output", "")),
            "test_command": str(_g(d, "test_command", "")),
            "cost_usd": float(_g(d, "cost_usd", 0.0) or 0.0),
            "error": str(_g(d, "error", "")),
        }
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {
            "status": "error",
            "summary": "",
            "files": [],
            "diff": "",
            "test_output": "",
            "error": str(exc),
        }


# ── Offline Ask (deterministic; never calls a provider — decision D3) ────────
def ask_offline(v: Verdict, question: str, repo_name: str) -> str:
    parts = [
        f"{v.tool_name} is an {v.verdict.upper()} for {repo_name} — fit {v.fit}, risk {v.risk}."
    ]
    if v.fit_reasons:
        parts.append(v.fit_reasons[0])
    if v.concerns:
        c = v.concerns[0]
        parts.append(f"Watch ({c.severity}): {c.evidence}")
    if v.next_safe_step:
        parts.append(f"Next: {v.next_safe_step}")
    parts.append("(offline answer — connect a provider for a live, tailored reply.)")
    return " ".join(p for p in parts if p)


# ── Guard-railed actions behind explicit gates (worker-only) ─────────────────
# These touch the real backends. The UI only calls them from a threaded worker
# AFTER the user has cleared the relevant gate. Each is defensive (mirrors the
# ``dossier``/``implement`` try/except style) so a backend hiccup degrades to a
# render-ready dict rather than crashing the worker.
def evaluate(verdict: Verdict, repo: str) -> dict[str, Any]:
    """Run a full (judged) evaluation of a verdict's source URL.

    SPENDS real money (``evaluate_url`` resolves a provider judge). Worker-only,
    post cost-gate. ``repo`` is accepted for API symmetry; ``evaluate_url`` has
    no repo parameter, so it is not forwarded. Returns a projection of the
    resulting ``Evaluation`` to plain str/list values; never raises.
    """
    try:
        from frontier_scout import evaluate as _eval

        v = _eval.evaluate_url(str(_g(verdict, "source_url", "")))
        fit = str(_g(v, "fit", ""))
        risk = str(_g(v, "risk", ""))
        trust = str(_g(v, "source_trust", ""))
        tool = str(_g(v, "tool_name", _g(verdict, "tool_name", "")))
        summary = f"{tool}: fit {fit or '−'}, risk {risk or '−'}, source trust {trust or '−'}."
        return {
            "ok": True,
            "tool_name": tool,
            "source_url": str(_g(v, "source_url", _g(verdict, "source_url", ""))),
            "category": str(_g(v, "category", "")),
            "fit": fit,
            "risk": risk,
            "source_trust": trust,
            "score": _g(v, "score", None),
            "summary": summary,
            "evidence": [str(x) for x in (_g(v, "evidence", ()) or ())],
        }
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {
            "ok": False,
            "tool_name": str(_g(verdict, "tool_name", "")),
            "summary": "evaluation failed",
            "error": str(exc),
        }


def lab(verdict: Verdict, repo: str) -> dict[str, Any]:
    """Run a sandbox trial of a verdict's tool (PyPI install + probe).

    Free of API spend but downloads + installs the package into a temp sandbox.
    ``persist`` is NOT a parameter of ``run_trial`` in this build; the trial
    always writes a receipt. We pass ``dry_run=False`` to actually run the lab.
    Worker-only, post-gate. Returns a projection of the result dict; never
    raises.
    """
    try:
        from frontier_scout import trials

        r = trials.run_trial(
            str(_g(verdict, "tool_name", "tool")),
            url=str(_g(verdict, "source_url", "")) or None,
            repo=Path(repo),
        )
        d = r if isinstance(r, dict) else {}
        return {
            "ok": True,
            "tool_name": str(_g(verdict, "tool_name", "")),
            "status": str(_g(d, "status", "")),
            "runtime": str(_g(d, "runtime", _g(d, "duration_s", ""))),
            "detail": str(_g(d, "summary", "")),
            "exit_code": _g(d, "exit_code", None),
        }
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {
            "ok": False,
            "tool_name": str(_g(verdict, "tool_name", "")),
            "status": "error",
            "detail": "trial failed",
            "error": str(exc),
        }


def clear_history(repo: str) -> int:
    """Delete persisted scans for ``repo``. DESTRUCTIVE. Returns deleted count.

    Worker-only, post typed-confirm gate. Defensive — returns 0 on failure.
    """
    try:
        from frontier_scout import store

        return int(store.clear_scans_for_repo(repo))
    except Exception:  # noqa: BLE001 — actions must never crash the UI
        return 0


# ── Reports (FREE — pure render of already-stored scan data) ──────────────────
# Both wrappers are no-spend / no-network: ``report_render`` re-renders the
# latest *stored* scan into static files; ``report_open`` hands an already
# written file to the OS browser. Neither calls an LLM or hits the network.
def report_render(repo: str) -> dict[str, Any]:
    """Render the latest stored scan for ``repo`` into a stable reports dir.

    Reads ``store.latest_scan(repo)`` (no scan is run — this only renders data
    already on disk) and writes the briefing bundle via ``report.write_report``.
    Returns ``{"ok": False, "reason": …}`` when there is nothing to render or on
    any failure; otherwise ``{"ok": True, "dir", "html", "files"}``. Defensive —
    never raises.
    """
    try:
        from frontier_scout import report, store

        payload = store.latest_scan(Path(repo))
        if not payload:
            return {"ok": False, "reason": "No stored scan yet — run a scout first."}
        verdicts = list(_g(payload, "verdicts", []) or [])
        date = str(_g(payload, "date", "latest") or "latest")
        # The stored payload carries the flat funnel fields (scanned/candidates/
        # cost_usd/…) at top level, mirroring how cli.py + setup_app.py feed it
        # straight back to the renderer as ``funnel``.
        out_dir = Path.home() / ".frontier-scout" / "reports" / _repo_name(repo)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = report.write_report(
            out_dir, verdicts, date=date, funnel=payload, include_trials=True
        )
        html_path = written.get("html")
        return {
            "ok": True,
            "dir": str(out_dir),
            "html": str(html_path) if html_path else "",
            "files": sorted(Path(p).name for p in written.values()),
        }
    except Exception as exc:  # noqa: BLE001 — actions must never crash the UI
        return {"ok": False, "reason": str(exc)}


def report_open(html_path: str) -> bool:
    """Open a rendered HTML report in the OS browser. Never raises.

    Uses the stdlib ``webbrowser`` (same pattern as the legacy setup_app). The
    file is opened via a ``file://`` URI so it resolves offline. Returns True on
    a successful hand-off, False on any failure.
    """
    try:
        import webbrowser

        target = Path(html_path)
        if not target.exists():
            return False
        return bool(webbrowser.open(target.resolve().as_uri()))
    except Exception:  # noqa: BLE001 — actions must never crash the UI
        return False
