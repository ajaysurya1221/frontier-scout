"""Doctor: check a repo's Frontier Scout (policy compiler) setup. Read-only, offline.

Reports whether the policy, lock, compiled Claude controls, hooks, and verify
workflow are present and consistent — the things ``agent compile`` produces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DoctorCheck", "run_doctor", "render_text", "render_json"]


@dataclass
class DoctorCheck:
    name: str
    status: str  # "pass" | "warn" | "fail"
    detail: str


def run_doctor(repo: str = ".") -> list[DoctorCheck]:
    """Return readiness checks for the Frontier Scout setup in ``repo``."""

    root = Path(repo)
    checks: list[DoctorCheck] = []

    def add(name: str, ok: bool, detail: str, *, warn_only: bool = False) -> None:
        checks.append(DoctorCheck(name, "pass" if ok else ("warn" if warn_only else "fail"), detail))

    policy = root / "frontier-scout.policy.json"
    lock = root / "policy.lock.json"
    settings = root / ".claude" / "settings.json"
    guard = root / ".claude" / "hooks" / "_fs_guard.py"
    workflow = root / ".github" / "workflows" / "frontier-scout-verify.yml"
    receipts = root / ".frontier-scout" / "receipts"

    add("policy", policy.exists(),
        f"{policy.name} {'present' if policy.exists() else 'missing — run `agent policy init`'}")
    add("lock", lock.exists(),
        f"{lock.name} {'present' if lock.exists() else 'missing — run `agent compile`'}")
    add("settings", settings.exists(),
        f".claude/settings.json {'present' if settings.exists() else 'missing — run `agent compile`'}")
    add("hooks", guard.exists(),
        f"hooks {'compiled' if guard.exists() else 'missing — run `agent compile`'}")
    add("workflow", workflow.exists(),
        f"verify workflow {'present' if workflow.exists() else 'missing — run `agent compile`'}",
        warn_only=True)

    if policy.exists() and lock.exists():
        try:
            from .agent_firewall.lock import policy_hash

            expected = json.loads(lock.read_text()).get("policy_sha256")
            current = policy_hash(json.loads(policy.read_text()))
            ok = bool(expected) and expected == current
            add("policy-lock-match", ok,
                "policy matches lock" if ok else "policy drifted — re-run `agent compile`")
        except Exception:
            add("policy-lock-match", False, "could not compare policy to lock")

    n = len(list(receipts.glob("*.json"))) if receipts.exists() else 0
    add("receipts", True, f"{n} local receipt(s)")
    return checks


def render_text(checks: list[DoctorCheck]) -> str:
    icon = {"pass": "ok ", "warn": "warn", "fail": "FAIL"}  # nosec B105 — status labels, not a secret
    return "".join(f"[{icon[c.status]}] {c.name}: {c.detail}\n" for c in checks)


def render_json(checks: list[DoctorCheck]) -> str:
    return json.dumps(
        [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks], indent=2
    )
