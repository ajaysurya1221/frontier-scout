"""One-off local evaluation for AI tools and model/tool surfaces."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .mcp_audit import PermissionManifest, classify_mcp_capabilities


class Evaluation(BaseModel):
    """A point-in-time, source-backed local evaluation."""

    tool_name: str
    source_url: str
    category: str
    fit: str = "medium"
    risk: str = "medium"
    source_trust: str = "medium"
    package: str | None = None
    evidence: list[str] = Field(default_factory=list)
    score: int = 5
    permission_manifest: PermissionManifest | None = None


def evaluate_url(
    url: str,
    stack: dict | None = None,
    *,
    source_text: str | None = None,
    reporter: "ProgressReporter | None" = None,
) -> Evaluation:
    """Evaluate a URL with deterministic heuristics.

    v0 intentionally avoids LLM calls here. Live scans still use the richer
    Scout funnel; this path is for fast local "should I try this?" decisions.

    v1.3.0 — accepts an optional ``reporter`` (see
    ``frontier_scout.progress``). ``None`` is a no-op.
    """

    from frontier_scout.progress import NullReporter

    progress = reporter or NullReporter()
    progress.stage("Classifying capabilities", total_stages=1)
    tool_name = _tool_name_from_url(url)
    text = " ".join(part for part in (tool_name, url, source_text or "") if part)
    category = _category(tool_name, url, text)
    source_trust = _source_trust(url)
    fit = _fit(category, text, stack or {})
    manifest = classify_mcp_capabilities(
        text,
        tool_name=tool_name,
        source_url=url,
        evidence_source="url-and-local-text",
    )
    risk = _risk(category, source_trust, manifest)
    score = _score(fit, risk, source_trust, manifest)
    evidence = [_evidence_label(url)]
    if source_text:
        evidence.append("local source text")
    if manifest.dangerous_flags:
        evidence.append("permission surface: " + ", ".join(manifest.dangerous_flags))
    progress.log(f"Evaluated {tool_name}: fit={fit} risk={risk}", tone="info")

    return Evaluation(
        tool_name=tool_name,
        source_url=url,
        category=category,
        fit=fit,
        risk=risk,
        source_trust=source_trust,
        package=_package_name(url, tool_name),
        evidence=evidence,
        score=score,
        permission_manifest=manifest,
    )


def _tool_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if host == "github.com" and len(parts) >= 2:
        return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if host == "huggingface.co" and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    if host == "pypi.org" and len(parts) >= 2 and parts[0] == "project":
        return parts[1]
    if host.endswith("npmjs.com") and parts:
        if parts[0] == "package" and len(parts) >= 2:
            return "/".join(parts[1:])
        return parts[-1]
    return parts[-1] if parts else host or url


def _category(tool_name: str, url: str, text: str) -> str:
    low = text.lower()
    if "huggingface.co" in url.lower():
        return "model_drop"
    if "mcp" in low or "modelcontextprotocol" in low:
        return "mcp_server"
    if "skill" in low:
        return "skill"
    if any(x in low for x in ("agent", "langgraph", "crewai", "browser-use", "openhands")):
        return "agent_framework"
    return "dev_tool"


def _source_trust(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host in {"github.com", "huggingface.co", "pypi.org", "npmjs.com"}:
        return "high"
    if host.endswith(("anthropic.com", "openai.com", "microsoft.com", "google.com")):
        return "high"
    if host:
        return "medium"
    return "low"


def _fit(category: str, text: str, stack: dict) -> str:
    stack_blob = " ".join(str(v).lower() for values in stack.values() for v in (values if isinstance(values, list) else [values]))
    low = text.lower()
    if category in {"mcp_server", "skill"} and any(x in stack_blob for x in ("agent", "mcp", "agents.md", "claude", "codex", "cursor")):
        return "high"
    if category == "model_drop" and any(x in stack_blob for x in ("ollama", "vllm", "huggingface")):
        return "high"
    if "python" in stack_blob and re.search(r"\b(python|pypi|pip)\b", low):
        return "high"
    if category in {"mcp_server", "agent_framework", "dev_tool"}:
        return "medium"
    return "low"


def _risk(category: str, source_trust: str, manifest: PermissionManifest) -> str:
    if "unknown" in manifest.dangerous_flags or "credential" in manifest.dangerous_flags or "shell" in manifest.dangerous_flags:
        return "high"
    if manifest.dangerous_flags or category in {"mcp_server", "agent_framework", "model_drop"}:
        return "medium"
    return "low" if source_trust == "high" else "medium"


def _score(fit: str, risk: str, source_trust: str, manifest: PermissionManifest) -> int:
    score = {"high": 4, "medium": 2, "low": 0}.get(fit, 1)
    score += {"high": 3, "medium": 2, "low": 0}.get(source_trust, 1)
    score -= {"high": 3, "medium": 1, "low": 0}.get(risk, 1)
    score -= 1 if "unknown" in manifest.dangerous_flags else 0
    return max(0, min(10, score + 3))


def _package_name(url: str, tool_name: str) -> str | None:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host in {"pypi.org", "npmjs.com", "huggingface.co"}:
        return tool_name
    return None


def _evidence_label(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return f"{host or 'source'} URL"
