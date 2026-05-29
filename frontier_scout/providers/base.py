"""Provider-agnostic LLM interface.

Frontier Scout's live pipeline (scout score/verdict, Opus judge, lab
classify/generate/interpret) was historically wired straight to the
Anthropic SDK. This module introduces a thin abstraction so the same
pipeline runs on any of four backends:

  * ``anthropic``   — Anthropic API key (the original path)
  * ``openai``      — OpenAI API key
  * ``claude-cli``  — the Claude Code CLI (``claude``), $0 marginal for
                      Max subscribers
  * ``codex-cli``   — the Codex CLI (``codex``)

The design goal is **surgical**: the Anthropic backend returns the raw
SDK response object, so every existing response-extraction site
(``resp.content`` → ``block.type == "tool_use"`` → ``tool_use.input``)
keeps working byte-for-byte. The OpenAI and CLI backends synthesise a
response with the *same shape* (a list of :class:`ToolUseBlock` /
:class:`TextBlock` plus a :class:`Usage`) so the callers never branch on
provider.

Callers pass a *tier* (``"fast"`` or ``"deep"``) rather than a hardcoded
model id; each provider maps the tier to its own model and reports the
actual model back via :attr:`ProviderResponse.model` so the cost ledger
attributes spend to the model that really ran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# Tiers the pipeline asks for. "fast" is the high-throughput scoring /
# verdict / lab model; "deep" is the judge model.
FAST = "fast"
DEEP = "deep"


class ProviderUnavailable(RuntimeError):
    """No usable backend could be resolved (no key, no CLI on PATH)."""


class ProviderError(RuntimeError):
    """A backend failed in a way the caller should surface, not retry."""


@dataclass
class Usage:
    """Token accounting in the shape the Anthropic SDK exposes.

    OpenAI and CLI backends fill what they can and leave cache fields at
    zero (those providers either auto-cache invisibly or don't cache).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class ToolUseBlock:
    """Mirrors an Anthropic ``tool_use`` content block."""

    name: str
    input: dict[str, Any]
    id: str = "toolu_synthetic"
    type: str = "tool_use"


@dataclass
class TextBlock:
    """Mirrors an Anthropic ``text`` content block."""

    text: str
    type: str = "text"


@dataclass
class ProviderResponse:
    """Anthropic-shaped response used by the non-Anthropic backends.

    The Anthropic backend skips this and returns the raw SDK object
    (which already exposes ``.content``, ``.usage`` and ``.model``).
    """

    content: list[Any] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    """The contract every backend implements.

    Implementations must be cheap to construct (detection happens before
    construction) and must not perform any network or subprocess work
    until :meth:`create` is called.
    """

    name: str

    def model(self, tier: str) -> str:
        """Return the concrete model id this backend uses for ``tier``."""
        ...

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: Any,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        thinking: dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> Any:
        """Run one completion and return an Anthropic-shaped response.

        ``model`` is the concrete id (already resolved from a tier by the
        caller via :meth:`model`). ``thinking`` / ``extra_body`` are
        Anthropic-only knobs that non-Anthropic backends ignore.
        """
        ...

    def is_retryable(self, exc: BaseException) -> bool:
        """Whether ``exc`` from :meth:`create` is a transient error."""
        ...


def first_tool_use(content: list[Any]) -> ToolUseBlock | None:
    """Return the first ``tool_use`` block in ``content`` (or None).

    A small helper so synthesised backends and tests share the exact
    selection logic the pipeline uses.
    """
    for block in content or []:
        if getattr(block, "type", None) == "tool_use":
            return block  # type: ignore[return-value]
    return None
