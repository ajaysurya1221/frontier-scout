"""Deterministic local policy for Adoption Firewall decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

from .evaluate import Evaluation
from .mcp_audit import PermissionManifest

Severity = Literal["info", "medium", "high"]
Verdict = Literal["adopt", "trial", "assess", "hold"]


class Policy(BaseModel):
    require_trial_for_dangerous_capabilities: bool = True
    fail_unknown_capabilities: bool = True
    allow_adopt_without_lab_for_low_risk: bool = False
    strict: bool = False
    packs: dict[str, dict[str, list[str]]] = Field(default_factory=dict)


class PolicyFinding(BaseModel):
    severity: Severity
    rule_id: str
    message: str
    tool_name: str = ""


class PolicyDecision(BaseModel):
    verdict: Verdict
    summary: str
    findings: list[PolicyFinding] = Field(default_factory=list)


DEFAULT_POLICY = Policy()


def load_policy(repo: Path | None = None) -> Policy:
    """Load optional TOML policy from repo or home, falling back to defaults."""

    candidates: list[Path] = []
    if repo is not None:
        candidates.append(Path(repo) / ".frontier-scout" / "policy.toml")
    candidates.append(Path("~/.frontier-scout/policy.toml").expanduser())
    for path in candidates:
        if not path.exists() or tomllib is None:
            continue
        try:
            data = tomllib.loads(path.read_text())
            policy_data = dict(data.get("policy") or data)
            if "packs" in data:
                policy_data["packs"] = data["packs"]
            return Policy(**policy_data)
        except (OSError, ValueError):
            # Malformed/unreadable policy file (bad TOML, wrong field type,
            # read error): honour the docstring and fall back to defaults
            # rather than crashing guard/dossier/scout. TOMLDecodeError and
            # pydantic ValidationError both subclass ValueError.
            continue
    return DEFAULT_POLICY


def default_policy_toml() -> str:
    return """[policy]
require_trial_for_dangerous_capabilities = true
fail_unknown_capabilities = true
allow_adopt_without_lab_for_low_risk = false
strict = false

[packs.mcp]
include = []
exclude = []
pin = ["modelcontextprotocol/servers"]
suppress = []
retire = []
"""


def evaluate_policy(
    evaluation: Evaluation,
    manifest: PermissionManifest | None = None,
    lab_result: dict[str, Any] | None = None,
    *,
    policy: Policy | None = None,
) -> PolicyDecision:
    policy = policy or DEFAULT_POLICY
    manifest = manifest or evaluation.permission_manifest
    findings: list[PolicyFinding] = []
    tool_name = evaluation.tool_name

    if manifest is None:
        findings.append(
            PolicyFinding(
                severity="high",
                rule_id="capability.missing",
                message="No permission manifest is stored for this tool.",
                tool_name=tool_name,
            )
        )
    else:
        if policy.fail_unknown_capabilities and "unknown" in manifest.dangerous_flags:
            findings.append(
                PolicyFinding(
                    severity="high",
                    rule_id="capability.unknown",
                    message="Capability surface is unknown; require better evidence before trial.",
                    tool_name=tool_name,
                )
            )
        # v1.2.1 — Stream H: the dangerous-flags loop was previously
        # unconditional; ``Policy.require_trial_for_dangerous_capabilities``
        # was a config field with no consumer. Now operators who set the
        # flag to ``false`` (e.g. for an internal toolchain where every
        # tool *is* network/write-capable by design) actually see the
        # capability.* findings disappear and verdicts shift accordingly.
        if policy.require_trial_for_dangerous_capabilities:
            for flag in manifest.dangerous_flags:
                if flag == "unknown":
                    continue
                severity: Severity = "high" if flag in {"write", "shell", "credential"} else "medium"
                findings.append(
                    PolicyFinding(
                        severity=severity,
                        rule_id=f"capability.{flag}",
                        message=f"Tool exposes {flag} capability; sandbox evidence is required before adoption.",
                        tool_name=tool_name,
                    )
                )

    lab_passed = bool(lab_result) and (
        lab_result.get("status") == "passed"
        or (
            lab_result.get("status") == "completed"
            # exit_code absent on a finished trial means clean finish;
            # default to 0 so precedence can't silently drop a passed lab.
            and lab_result.get("exit_code", 0) == 0
        )
    )
    lab_failed = bool(lab_result) and lab_result.get("exit_code") not in {None, 0}
    if lab_failed:
        findings.append(
            PolicyFinding(
                severity="high",
                rule_id="lab.failed",
                message="Latest lab run failed; hold adoption until investigated.",
                tool_name=tool_name,
            )
        )

    if any(f.rule_id in {"capability.unknown", "capability.missing", "lab.failed"} for f in findings):
        return PolicyDecision(
            verdict="hold",
            summary="HOLD - blocking local evidence is missing or failed.",
            findings=findings,
        )

    high_findings = [f for f in findings if f.severity == "high"]
    if high_findings and not lab_passed:
        return PolicyDecision(
            verdict="trial",
            summary="TRIAL - high-risk capability requires sandbox evidence.",
            findings=findings,
        )

    if findings and not lab_passed:
        return PolicyDecision(
            verdict="trial",
            summary="TRIAL - permission surface requires a stored sandbox receipt.",
            findings=findings,
        )

    if (
        evaluation.fit == "high"
        and evaluation.risk == "low"
        and evaluation.source_trust == "high"
        and (lab_passed or policy.allow_adopt_without_lab_for_low_risk)
        and not findings
    ):
        return PolicyDecision(
            verdict="adopt",
            summary="ADOPT - high fit, low risk, trusted source, and clean evidence.",
            findings=[],
        )

    if lab_passed:
        return PolicyDecision(
            verdict="trial",
            summary="TRIAL - lab evidence exists; review before adoption.",
            findings=findings,
        )

    return PolicyDecision(
        verdict="assess",
        summary="ASSESS - relevant, but needs stronger local evidence.",
        findings=findings,
    )
