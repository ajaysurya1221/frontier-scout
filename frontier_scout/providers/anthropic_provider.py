"""Anthropic backend — the original path, behind the provider contract.

This backend is a near-passthrough: :meth:`create` forwards every kwarg
to ``client.messages.create`` and returns the raw SDK response, so the
existing extraction code (``resp.content`` / ``resp.usage`` /
``resp.model``) is unchanged.
"""

from __future__ import annotations

import os
from typing import Any

import anthropic

from .base import DEEP

# Defaults match the historical constants in scripts/scout.py and
# scripts/judge.py. Overridable so a user can pin a cheaper/newer model.
_DEFAULT_FAST = "claude-sonnet-4-6"
_DEFAULT_DEEP = "claude-opus-4-7"


def _should_retry(exc: BaseException) -> bool:
    """Transient-error policy lifted from the old llm_client module."""
    retry_types = (
        anthropic.APITimeoutError,
        anthropic.APIConnectionError,
        anthropic.RateLimitError,
        anthropic.InternalServerError,
    )
    if isinstance(exc, retry_types):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        code = getattr(exc, "status_code", None)
        if code in {408, 409, 429, 529} or (
            isinstance(code, int) and 500 <= code < 600
        ):
            return True
    return False


class AnthropicProvider:
    """Wraps ``anthropic.Anthropic`` behind :class:`base.LLMProvider`."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is required for live scans")
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def model(self, tier: str) -> str:
        if tier == DEEP:
            return os.environ.get("FRONTIER_SCOUT_ANTHROPIC_DEEP_MODEL", _DEFAULT_DEEP)
        return os.environ.get("FRONTIER_SCOUT_ANTHROPIC_FAST_MODEL", _DEFAULT_FAST)

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
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if thinking is not None:
            kwargs["thinking"] = thinking
        if extra_body is not None:
            kwargs["extra_body"] = extra_body
        return self.client.messages.create(**kwargs)

    def is_retryable(self, exc: BaseException) -> bool:
        return _should_retry(exc)
