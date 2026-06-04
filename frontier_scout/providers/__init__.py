"""Provider resolution for Frontier Scout's live LLM pipeline.

``resolve_provider()`` is the single entry point. It honours an explicit
pin (argument > ``FRONTIER_SCOUT_PROVIDER`` env) and otherwise
auto-detects in priority order:

    anthropic key → openai key → claude CLI → codex CLI

If nothing is usable it raises :class:`ProviderUnavailable` with a
message that points the user at the offline demo rather than a raw
traceback.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from .anthropic_provider import AnthropicProvider
from .base import (
    DEEP,
    FAST,
    LLMProvider,
    ProviderError,
    ProviderResponse,
    ProviderUnavailable,
    TextBlock,
    ToolUseBlock,
    Usage,
    first_tool_use,
)
from .cli_provider import ClaudeCodeProvider, CodexProvider
from .openai_provider import OpenAICompatibleProvider, OpenAIProvider

__all__ = [
    "AnthropicProvider",
    "ClaudeCodeProvider",
    "CodexProvider",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "LLMProvider",
    "ProviderError",
    "ProviderResponse",
    "ProviderUnavailable",
    "TextBlock",
    "ToolUseBlock",
    "Usage",
    "FAST",
    "DEEP",
    "first_tool_use",
    "resolve_provider",
    "available_providers",
    "PROVIDER_NAMES",
]

PROVIDER_NAMES = ("anthropic", "openai", "openai-compatible", "claude-cli", "codex-cli")


def _has_anthropic() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _has_openai() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _has_openai_base_url() -> bool:
    return bool(
        os.environ.get("FRONTIER_SCOUT_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
    )


# A CLI on PATH isn't necessarily runnable — a broken install (e.g. a codex
# Node-version crash) still satisfies `which`. Probe `<binary> --version` once
# (cached per-process) so a non-runnable CLI is treated as unavailable rather
# than silently selected, which fails a scan cryptically mid-run. On a clean
# machine the `which` short-circuit means no subprocess is ever spawned.
_CLI_PROBE_CACHE: dict[str, bool] = {}


def _reset_cli_probe() -> None:
    """Drop the cached CLI runnability probes (CLIs don't change mid-run)."""
    _CLI_PROBE_CACHE.clear()


def _cli_runs(binary: str) -> bool:
    """True if *binary* is on PATH AND runs cleanly (``--version`` exits 0)."""
    if binary in _CLI_PROBE_CACHE:
        return _CLI_PROBE_CACHE[binary]
    ok = shutil.which(binary) is not None
    if ok:
        try:
            proc = subprocess.run(
                [binary, "--version"], capture_output=True, timeout=10
            )
            ok = proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
    _CLI_PROBE_CACHE[binary] = ok
    return ok


def _has_claude_cli() -> bool:
    return _cli_runs("claude")


def _has_codex_cli() -> bool:
    return _cli_runs("codex")


def _build(name: str) -> LLMProvider:
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai":
        return OpenAIProvider()
    if name == "openai-compatible":
        return OpenAICompatibleProvider()
    if name == "claude-cli":
        return ClaudeCodeProvider()
    if name == "codex-cli":
        return CodexProvider()
    raise ProviderUnavailable(f"Unknown provider {name!r}")


def available_providers() -> list[str]:
    """Names of every backend that could run right now, in priority order."""
    out: list[str] = []
    if _has_anthropic():
        out.append("anthropic")
    if _has_openai():
        out.append("openai-compatible" if _has_openai_base_url() else "openai")
    if _has_claude_cli():
        out.append("claude-cli")
    if _has_codex_cli():
        out.append("codex-cli")
    return out


def resolve_provider(name: str | None = None) -> LLMProvider:
    """Return a usable :class:`LLMProvider`.

    ``name`` (or ``FRONTIER_SCOUT_PROVIDER``) pins a specific backend; a
    pinned backend that isn't usable raises :class:`ProviderUnavailable`
    rather than silently falling through, so the user learns why.
    """
    pinned = name or os.environ.get("FRONTIER_SCOUT_PROVIDER")
    if pinned:
        pinned = pinned.strip().lower()
        # OPENAI_BASE_URL is the standard OpenAI-SDK redirect; a pinned "openai"
        # with a base_url set means "my OpenAI-compatible endpoint".
        if pinned == "openai" and _has_openai_base_url():
            pinned = "openai-compatible"
        usable = available_providers()
        if pinned not in PROVIDER_NAMES:
            raise ProviderUnavailable(
                f"Unknown provider {pinned!r}. Choose one of: {', '.join(PROVIDER_NAMES)}."
            )
        if pinned not in usable:
            raise ProviderUnavailable(
                f"Provider {pinned!r} is pinned but unavailable "
                f"(no API key, or the CLI is missing or not runnable — a broken "
                f"install still satisfies PATH). Available: {usable or 'none'}."
            )
        return _build(pinned)

    for candidate in available_providers():
        return _build(candidate)

    raise ProviderUnavailable(
        "No LLM provider available. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
        "log in to the Claude Code or Codex CLI, or run `frontier-scout --demo` "
        "for the offline radar."
    )
