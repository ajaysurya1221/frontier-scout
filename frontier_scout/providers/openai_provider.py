"""OpenAI backend.

Translates Frontier Scout's Anthropic-shaped requests into OpenAI
Chat Completions calls and synthesises an Anthropic-shaped response so
the rest of the pipeline is provider-blind:

  * system blocks (list of ``{type,text,cache_control}``) → one system
    message string (``cache_control`` is Anthropic-only; dropped)
  * Anthropic tools (``{name,description,input_schema}``) → OpenAI
    function tools (``{type:"function",function:{...,parameters}}``)
  * ``tool_choice={"type":"tool","name":X}`` → forced function call;
    ``{"type":"auto"}`` → ``"auto"``
  * the returned function call → a :class:`ToolUseBlock`
"""

from __future__ import annotations

import json
import os
from typing import Any

from .base import ProviderError, ProviderResponse, TextBlock, ToolUseBlock, Usage

_DEFAULT_FAST = "gpt-4o-mini"
_DEFAULT_DEEP = "gpt-4o"


def _system_text(system: Any) -> str:
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    parts: list[str] = []
    for block in system:
        if isinstance(block, dict):
            parts.append(str(block.get("text", "")))
        else:
            parts.append(str(block))
    return "\n\n".join(p for p in parts if p)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "\n\n".join(p for p in parts if p)
    return str(content)


def _to_openai_messages(system: Any, messages: list[dict[str, Any]]) -> list[dict]:
    out: list[dict[str, Any]] = []
    sys_text = _system_text(system)
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    for m in messages:
        out.append({"role": m["role"], "content": _content_text(m.get("content"))})
    return out


def _to_openai_tools(tools: list[dict[str, Any]] | None) -> list[dict] | None:
    if not tools:
        return None
    out = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object"}),
                },
            }
        )
    return out


def _to_openai_tool_choice(tool_choice: dict[str, Any] | None) -> Any:
    if not tool_choice:
        return None
    kind = tool_choice.get("type")
    if kind == "tool" and tool_choice.get("name"):
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    if kind == "auto":
        return "auto"
    if kind == "any":
        return "required"
    return None


class OpenAIProvider:
    """Wraps the OpenAI SDK behind :class:`base.LLMProvider`."""

    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            import openai

            if not self._api_key:
                raise RuntimeError("OPENAI_API_KEY is required for live scans")
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def model(self, tier: str) -> str:
        if tier == "deep":
            return os.environ.get("FRONTIER_SCOUT_OPENAI_DEEP_MODEL", _DEFAULT_DEEP)
        return os.environ.get("FRONTIER_SCOUT_OPENAI_FAST_MODEL", _DEFAULT_FAST)

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
    ) -> ProviderResponse:
        oai_messages = _to_openai_messages(system, messages)
        oai_tools = _to_openai_tools(tools)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            choice = _to_openai_tool_choice(tool_choice)
            if choice is not None:
                kwargs["tool_choice"] = choice
        resp = self.client.chat.completions.create(**kwargs)
        return self._normalise(resp, model)

    @staticmethod
    def _normalise(resp: Any, model: str) -> ProviderResponse:
        content: list[Any] = []
        choice = resp.choices[0] if getattr(resp, "choices", None) else None
        message = getattr(choice, "message", None) if choice else None
        tool_calls = getattr(message, "tool_calls", None) if message else None
        if tool_calls:
            call = tool_calls[0]
            fn = call.function
            # Fail fast on malformed tool-call arguments. Coercing to {} here
            # would silently degrade the whole pipeline to zero scores / empty
            # verdicts instead of surfacing the bad response (and letting the
            # retry wrapper try again).
            if not fn.arguments:
                raise ProviderError(
                    f"OpenAI tool call {fn.name!r} returned empty arguments"
                )
            try:
                parsed = json.loads(fn.arguments)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ProviderError(
                    f"OpenAI tool call {fn.name!r} returned non-JSON arguments: {exc}"
                ) from exc
            content.append(
                ToolUseBlock(name=fn.name, input=parsed, id=getattr(call, "id", "toolu"))
            )
        elif message is not None and getattr(message, "content", None):
            content.append(TextBlock(text=message.content))

        usage_obj = getattr(resp, "usage", None)
        usage = Usage(
            input_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
        )
        return ProviderResponse(
            content=content, usage=usage, model=getattr(resp, "model", model)
        )

    def is_retryable(self, exc: BaseException) -> bool:
        # A malformed/empty tool-call response is often a transient model hiccup;
        # give the retry wrapper a chance rather than failing the whole scan.
        if isinstance(exc, ProviderError):
            return True
        try:
            import openai
        except ImportError:
            return False
        retry_types = (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.InternalServerError,
        )
        if isinstance(exc, retry_types):
            return True
        if isinstance(exc, openai.APIStatusError):
            code = getattr(exc, "status_code", None)
            if code in {408, 409, 429} or (isinstance(code, int) and 500 <= code < 600):
                return True
        return False
