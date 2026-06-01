"""Dependency intelligence for repo-aware adoption scouting."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field

from .profile import DependencySpec, build_scout_profile
from .store import get_dep_cache, save_dep_cache, save_dependency_finding

if TYPE_CHECKING:
    from frontier_scout.progress import ProgressReporter

Classification = Literal["security", "hardening", "breaking", "feature", "noise"]


class AdvisoryLookupError(RuntimeError):
    """Raised when the OSV advisory lookup cannot be completed.

    Distinct from "no advisories found": a caller that treats this as an empty
    result would silently report a vulnerable dependency as benign during an
    OSV outage.
    """


OSV_ENDPOINT = "https://api.osv.dev/v1/query"
PYPI_ENDPOINT = "https://pypi.org/pypi/{name}/json"
NPM_ENDPOINT = "https://registry.npmjs.org/{name}"

_SECURITY_RE = re.compile(r"\b(CVE-\d{4}-\d+|GHSA-[a-z0-9-]+|vulnerability|rce|xss|prototype pollution)\b", re.I)
_HARDENING_RE = re.compile(r"\b(harden(?:ed|ing|s)?|sanitize|unsafe|untrusted|manifest|path traversal|urllib3)\b", re.I)
_BREAKING_RE = re.compile(r"\b(breaking|removed|drop(?:ped)? support|incompatible|deprecated)\b", re.I)


class ReleaseClassification(BaseModel):
    package_name: str
    from_version: str
    to_version: str
    classification: Classification
    confidence: float = Field(ge=0, le=1)
    evidence_quotes: list[str] = Field(default_factory=list)


class DependencyFinding(BaseModel):
    repo_id: str
    repo: str
    ecosystem: Literal["pypi", "npm"]
    package_name: str
    from_version: str
    to_version: str
    classification: Classification
    classifier_confidence: float
    advisory_ids: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    verdict: Literal["trial", "assess", "hold"] = "assess"
    repo_fit: str = "medium"
    next_safe_step: str
    #: True when the OSV advisory lookup could not be completed (network/parse
    #: error). The finding then cannot be trusted as "clean": absence of
    #: advisory_ids means "unknown", not "safe". Defaults False so persisted
    #: legacy rows and the metadata/offline path read as a completed check.
    advisory_lookup_failed: bool = False


def classify_release_notes(
    *,
    package_name: str,
    from_version: str,
    to_version: str,
    text: str,
) -> ReleaseClassification:
    """Classify release notes deterministically before any optional LLM pass."""

    quotes = _evidence_quotes(text)
    if _SECURITY_RE.search(text):
        return ReleaseClassification(
            package_name=package_name,
            from_version=from_version,
            to_version=to_version,
            classification="security",
            confidence=0.9,
            evidence_quotes=quotes,
        )
    if _HARDENING_RE.search(text):
        return ReleaseClassification(
            package_name=package_name,
            from_version=from_version,
            to_version=to_version,
            classification="hardening",
            confidence=0.75,
            evidence_quotes=quotes,
        )
    if _BREAKING_RE.search(text):
        return ReleaseClassification(
            package_name=package_name,
            from_version=from_version,
            to_version=to_version,
            classification="breaking",
            confidence=0.7,
            evidence_quotes=quotes,
        )
    if text.strip():
        return ReleaseClassification(
            package_name=package_name,
            from_version=from_version,
            to_version=to_version,
            classification="feature",
            confidence=0.45,
            evidence_quotes=quotes[:2],
        )
    return ReleaseClassification(
        package_name=package_name,
        from_version=from_version,
        to_version=to_version,
        classification="noise",
        confidence=0.0,
        evidence_quotes=[],
    )


def run_dependency_scan(
    repo: Path,
    *,
    metadata: dict[str, Any] | None = None,
    max_items: int = 30,
    persist: bool = True,
    reporter: ProgressReporter | None = None,
) -> dict[str, Any]:
    """Scan pinned repo dependencies for meaningful upgrade findings.

    v1.3.0 — accepts an optional ``reporter`` (see
    ``frontier_scout.progress``). ``None`` is a no-op.
    """

    from frontier_scout.progress import NullReporter

    progress = reporter or NullReporter()
    progress.stage("Reading manifests", total_stages=2)
    profile = build_scout_profile(repo)
    deps = profile.dependencies[:max_items]
    progress.stage("Classifying upgrades", total_stages=2)
    findings: list[DependencyFinding] = []
    total_deps = max(1, len(deps))
    for index, dep in enumerate(deps, start=1):
        finding = _finding_for_dependency(profile.repo_id, profile.repo, dep, metadata=metadata)
        if finding is None:
            continue
        findings.append(finding)
        if persist:
            save_dependency_finding(finding)
        progress.advance(index / total_deps, f"{index}/{total_deps} {dep.name}")
    progress.log(
        f"Dependency scan complete: {len(findings)} finding(s)",
        tone="ok",
    )
    return {
        "repo": profile.repo,
        "repo_id": profile.repo_id,
        "dependencies_scanned": len(deps),
        "findings": [finding.model_dump() for finding in findings],
    }


def _finding_for_dependency(
    repo_id: str,
    repo: str,
    dep: DependencySpec,
    *,
    metadata: dict[str, Any] | None,
) -> DependencyFinding | None:
    current = dep.resolved_version or _exact_version(dep.specifier)
    if not current:
        return None
    try:
        package_meta = _package_metadata(dep, metadata)
    except RuntimeError:
        package_meta = {}
    latest = str(package_meta.get("latest_version") or "")
    if not latest:
        return DependencyFinding(
            repo_id=repo_id,
            repo=repo,
            ecosystem=dep.ecosystem,
            package_name=dep.name,
            from_version=current,
            to_version=current,
            classification="noise",
            classifier_confidence=0.0,
            advisory_ids=[],
            evidence_quotes=[],
            verdict="assess",
            repo_fit="medium",
            next_safe_step=f"Retry dependency metadata lookup for {dep.name}; registry metadata was unavailable.",
        )
    if not _is_newer(latest, current):
        return None
    notes = _release_notes(package_meta, latest)
    classification = classify_release_notes(
        package_name=dep.name,
        from_version=current,
        to_version=latest,
        text=notes,
    )
    advisory_lookup_failed = False
    try:
        advisory_ids = _advisory_ids(dep, current, metadata)
    except AdvisoryLookupError:
        # OSV is unreachable. We cannot claim this upgrade is clean, so flag the
        # gap and never let the dep be dropped (the "noise + no advisory" path
        # below) or read as benign. The advisory check simply did not run.
        advisory_lookup_failed = True
        advisory_ids = []
    if advisory_ids and classification.classification in {"feature", "noise"}:
        classification = classification.model_copy(
            update={"classification": "security", "confidence": max(classification.confidence, 0.85)}
        )
    if classification.classification == "noise" and not advisory_ids and not advisory_lookup_failed:
        return None
    verdict: Literal["trial", "assess", "hold"] = (
        "trial" if classification.classification in {"security", "hardening", "breaking"} else "assess"
    )
    if advisory_lookup_failed:
        # Surface, but do not over-state: not "security" (we have no evidence of
        # a vuln), yet not silently clean either. Hold for a human re-run.
        verdict = "hold" if verdict == "assess" else verdict
        next_step = (
            f"OSV advisory lookup failed for {dep.name} {current}→{latest}; "
            f"re-run `frontier-scout deps` once OSV is reachable before trusting this as clean."
        )
    else:
        next_step = (
            f"frontier-scout deps trial {dep.name} --from {current} --to {latest} --repo {repo}"
        )
    return DependencyFinding(
        repo_id=repo_id,
        repo=repo,
        ecosystem=dep.ecosystem,
        package_name=dep.name,
        from_version=current,
        to_version=latest,
        classification=classification.classification,
        classifier_confidence=classification.confidence,
        advisory_ids=advisory_ids,
        advisory_lookup_failed=advisory_lookup_failed,
        evidence_quotes=classification.evidence_quotes,
        verdict=verdict,
        repo_fit="high" if dep.name in {"langchain-core", "@modelcontextprotocol/sdk"} else "medium",
        next_safe_step=next_step,
    )


def _package_metadata(dep: DependencySpec, metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata:
        return dict((metadata.get(dep.ecosystem) or {}).get(dep.name) or {})
    source = "pypi" if dep.ecosystem == "pypi" else "npm"
    cached = get_dep_cache(source, dep.name)
    if cached is not None:
        return cached
    if dep.ecosystem == "pypi":
        payload = _get_json(PYPI_ENDPOINT.format(name=urllib.parse.quote(dep.name)))
        latest = ((payload.get("info") or {}).get("version")) or ""
        releases = payload.get("releases") or {}
        meta = {
            "latest_version": latest,
            "release_notes": {latest: str((payload.get("info") or {}).get("description") or "")[:8000]},
            "release_count": len(releases),
        }
        save_dep_cache("pypi", dep.name, meta, ttl_seconds=12 * 60 * 60)
        return meta
    payload = _get_json(NPM_ENDPOINT.format(name=urllib.parse.quote(dep.name, safe="@")))
    latest = str(((payload.get("dist-tags") or {}).get("latest")) or "")
    latest_meta = (payload.get("versions") or {}).get(latest) or {}
    meta = {
        "latest_version": latest,
        "release_notes": {latest: str(latest_meta.get("description") or payload.get("description") or "")[:8000]},
        "repository": latest_meta.get("repository") or payload.get("repository"),
    }
    save_dep_cache("npm", dep.name, meta, ttl_seconds=12 * 60 * 60)
    return meta


def _advisory_ids(dep: DependencySpec, version: str, metadata: dict[str, Any] | None) -> list[str]:
    """Return OSV advisory IDs for ``dep@version``.

    Raises :class:`AdvisoryLookupError` when the OSV query cannot be completed
    (network/parse error). Callers MUST distinguish that from an empty list: an
    empty list means "OSV answered: no advisories", whereas the exception means
    "we never found out" — treating the latter as clean would silently hide a
    real CVE during an OSV outage.
    """

    key = f"{_osv_ecosystem(dep.ecosystem)}:{dep.name}:{version}"
    if metadata:
        vulns = ((metadata.get("osv") or {}).get(key) or {}).get("vulns") or []
        return [str(v.get("id")) for v in vulns if v.get("id")]
    cached = get_dep_cache("osv", key)
    if cached is None:
        try:
            time.sleep(0.05)
            cached = _post_json(
                OSV_ENDPOINT,
                {
                    "version": version,
                    "package": {"name": dep.name, "ecosystem": _osv_ecosystem(dep.ecosystem)},
                },
            )
        except RuntimeError as exc:
            # Do NOT swallow into [] — that is indistinguishable from "no
            # advisories" and would present a vulnerable dep as benign.
            raise AdvisoryLookupError(str(exc)) from exc
        save_dep_cache("osv", key, cached, ttl_seconds=24 * 60 * 60)
    return [str(v.get("id")) for v in (cached.get("vulns") or []) if v.get("id")]


def _release_notes(package_meta: dict[str, Any], version: str) -> str:
    notes = package_meta.get("release_notes") or {}
    if isinstance(notes, dict):
        return str(notes.get(version) or "")
    return str(notes or "")


def _evidence_quotes(text: str) -> list[str]:
    lines = [line.strip(" -#") for line in text.splitlines() if line.strip()]
    hits = [
        line
        for line in lines
        if _SECURITY_RE.search(line) or _HARDENING_RE.search(line) or _BREAKING_RE.search(line)
    ]
    if hits:
        return hits[:4]
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip()[:180] for s in sentences if s.strip()][:2]


def _exact_version(specifier: str) -> str | None:
    match = re.match(r"\s*==\s*([A-Za-z0-9_.!+-]+)\s*$", specifier)
    return match.group(1) if match else None


def _is_newer(candidate: str, current: str) -> bool:
    try:
        return Version(candidate) > Version(current)
    except InvalidVersion:
        return candidate != current


def _osv_ecosystem(ecosystem: str) -> str:
    return "PyPI" if ecosystem == "pypi" else "npm"


def _get_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:  # noqa: S310 - fixed public metadata endpoints.
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"metadata fetch failed: {url}") from exc


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310 - fixed public OSV endpoint.
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OSV fetch failed: {url}") from exc
