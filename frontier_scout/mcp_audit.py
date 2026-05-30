"""Static capability audit helpers for MCP-like tool surfaces."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

CapabilityStatus = Literal["likely", "possible", "unlikely", "unknown"]
Confidence = Literal["high", "medium", "low"]

CAPABILITY_KEYS = ("read", "write", "network", "browser", "shell", "credential", "unknown")
DANGEROUS_KEYS = {"write", "network", "browser", "shell", "credential", "unknown"}

_PATTERNS: dict[str, re.Pattern[str]] = {
    "read": re.compile(r"\b(read|list|get|fetch|search|query|inspect|schema|resource)\b", re.I),
    "write": re.compile(
        r"\b(writ(e|es|ing|ten)|modif(y|ies|ied|ying)|updat(e|es|ed|ing)|"
        r"delet(e|es|ed|ing)|creat(e|es|ed|ing)|insert(s|ed|ing)?|"
        r"patch(es|ed|ing)?|commit(s|ted|ting)?|push(es|ed|ing)?|"
        r"send(s|ing)?|overwrit(e|es|ing|ten)|remov(e|es|ed|ing))\b",
        re.I,
    ),
    "network": re.compile(r"\b(http|https|url|api|webhook|network|request|download|upload|fetch_url)\b", re.I),
    "browser": re.compile(r"\b(browser|playwright|chromium|page|click|navigate|screenshot|dom)\b", re.I),
    "shell": re.compile(
        r"\b(shell|commands?|execut(e|es|ing|ion)|exec|subprocess|terminal|"
        r"bash|zsh|powershell|runs?|running|spawn(s|ed|ing)?|"
        r"invoke|invokes|system\(|os\.system)\b",
        re.I,
    ),
    "credential": re.compile(
        r"\b(tokens?|secrets?|credentials?|api[_ -]?keys?|oauth|logins?|"
        r"authentication|authorization|authenticate|authorize|auth|"
        r"passwords?)\b",
        re.I,
    ),
}


class PermissionManifest(BaseModel):
    """A conservative, local-only summary of a tool's permission surface."""

    tool_name: str = ""
    source_url: str = ""
    capabilities: dict[str, CapabilityStatus] = Field(default_factory=dict)
    dangerous_flags: list[str] = Field(default_factory=list)
    evidence_source: str = "static-text"
    confidence: Confidence = "low"


def classify_mcp_capabilities(
    text_or_schema: str | None,
    *,
    tool_name: str = "",
    source_url: str = "",
    evidence_source: str = "static-text",
) -> PermissionManifest:
    """Classify capability words without executing any server or tool.

    This deliberately fails closed. Sparse or empty input becomes
    ``unknown=likely`` so policy can require a real manifest or trial before
    trust is granted.
    """

    text = text_or_schema or ""
    capabilities: dict[str, CapabilityStatus] = {key: "unlikely" for key in CAPABILITY_KEYS}

    if not text.strip():
        capabilities["unknown"] = "likely"
        return PermissionManifest(
            tool_name=tool_name,
            source_url=source_url,
            capabilities=capabilities,
            dangerous_flags=["unknown"],
            evidence_source=evidence_source or "empty",
            confidence="low",
        )

    for key, pattern in _PATTERNS.items():
        if pattern.search(text):
            capabilities[key] = "likely"

    if all(capabilities[key] == "unlikely" for key in _PATTERNS):
        capabilities["unknown"] = "likely"

    dangerous = sorted(
        key
        for key, status in capabilities.items()
        if key in DANGEROUS_KEYS and status in {"likely", "possible"}
    )
    matched_count = sum(1 for key in _PATTERNS if capabilities[key] == "likely")
    confidence: Confidence = "high" if matched_count >= 3 else "medium"
    if capabilities["unknown"] == "likely":
        confidence = "low"

    return PermissionManifest(
        tool_name=tool_name,
        source_url=source_url,
        capabilities=capabilities,
        dangerous_flags=dangerous,
        evidence_source=evidence_source,
        confidence=confidence,
    )
