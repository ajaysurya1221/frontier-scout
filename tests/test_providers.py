"""v1.4.0 Stream 1 — the universal provider abstraction.

These tests pin the contract without spending a cent: every backend is
exercised with fakes/mocks. The live conformance smoke (real keys, real
CLIs) lives outside the unit suite.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from frontier_scout.providers import (
    DEEP,
    FAST,
    AnthropicProvider,
    CodexProvider,
    OpenAIProvider,
    ProviderError,
    ProviderResponse,
    ProviderUnavailable,
    ToolUseBlock,
    Usage,
    available_providers,
    first_tool_use,
    resolve_provider,
)
from frontier_scout.providers.cli_provider import ClaudeCodeProvider, extract_json_object

SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


# ---------------------------------------------------------------------------
# resolution + detection
# ---------------------------------------------------------------------------


def _clear_provider_env(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FRONTIER_SCOUT_PROVIDER"):
        monkeypatch.delenv(var, raising=False)


def test_resolve_prefers_anthropic_then_openai(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # pragma: allowlist secret
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    assert resolve_provider().name == "anthropic"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert resolve_provider().name == "openai"


def test_resolve_falls_back_to_cli(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: True)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: True)
    assert resolve_provider().name == "claude-cli"


def test_resolve_raises_when_nothing_available(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    with pytest.raises(ProviderUnavailable) as exc:
        resolve_provider()
    assert "--demo" in str(exc.value)


def test_pinned_unavailable_provider_raises(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    monkeypatch.setenv("FRONTIER_SCOUT_PROVIDER", "openai")
    with pytest.raises(ProviderUnavailable):
        resolve_provider()


def test_pinned_unknown_provider_raises(monkeypatch):
    _clear_provider_env(monkeypatch)
    with pytest.raises(ProviderUnavailable):
        resolve_provider("not-a-provider")


def test_available_providers_order(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: True)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    assert available_providers() == ["openai", "claude-cli"]


# ---------------------------------------------------------------------------
# AnthropicProvider — passthrough
# ---------------------------------------------------------------------------


def test_anthropic_tier_mapping(monkeypatch):
    monkeypatch.delenv("FRONTIER_SCOUT_ANTHROPIC_FAST_MODEL", raising=False)
    monkeypatch.delenv("FRONTIER_SCOUT_ANTHROPIC_DEEP_MODEL", raising=False)
    p = AnthropicProvider(api_key="k")  # pragma: allowlist secret
    assert p.model(FAST) == "claude-sonnet-4-6"
    assert p.model(DEEP) == "claude-opus-4-7"


def test_anthropic_create_forwards_to_sdk():
    p = AnthropicProvider(api_key="k")  # pragma: allowlist secret
    captured = {}

    class _Msgs:
        def create(self, **kw):
            captured.update(kw)
            return "raw-response"

    class _Client:
        messages = _Msgs()

    p._client = _Client()
    out = p.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        system=[{"type": "text", "text": "s"}],
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "t"}],
        tool_choice={"type": "tool", "name": "t"},
    )
    assert out == "raw-response"
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["tool_choice"] == {"type": "tool", "name": "t"}
    # thinking/extra_body omitted when not passed
    assert "thinking" not in captured


# ---------------------------------------------------------------------------
# OpenAIProvider — translation + normalisation
# ---------------------------------------------------------------------------


def test_openai_tier_mapping(monkeypatch):
    monkeypatch.delenv("FRONTIER_SCOUT_OPENAI_FAST_MODEL", raising=False)
    monkeypatch.delenv("FRONTIER_SCOUT_OPENAI_DEEP_MODEL", raising=False)
    p = OpenAIProvider(api_key="k")  # pragma: allowlist secret
    assert p.model(FAST) == "gpt-4o-mini"
    assert p.model(DEEP) == "gpt-4o"


def _fake_openai_response(tool_name, arguments_json, *, prompt=11, completion=22):
    fn = types.SimpleNamespace(name=tool_name, arguments=arguments_json)
    call = types.SimpleNamespace(function=fn, id="call_1")
    msg = types.SimpleNamespace(tool_calls=[call], content=None)
    choice = types.SimpleNamespace(message=msg)
    usage = types.SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    return types.SimpleNamespace(choices=[choice], usage=usage, model="gpt-4o-mini")


def test_openai_create_translates_and_normalises():
    p = OpenAIProvider(api_key="k")  # pragma: allowlist secret
    captured = {}

    class _Completions:
        def create(self, **kw):
            captured.update(kw)
            return _fake_openai_response("score_items", '{"scores": [{"index": 0}]}')

    class _Chat:
        completions = _Completions()

    p._client = types.SimpleNamespace(chat=_Chat())

    resp = p.create(
        model="gpt-4o-mini",
        max_tokens=100,
        system=[{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "score it"}],
        tools=[{"name": "score_items", "description": "d", "input_schema": {"type": "object"}}],
        tool_choice={"type": "tool", "name": "score_items"},
        thinking={"type": "adaptive"},  # ignored
    )
    # system block flattened into a system message, cache_control dropped
    assert captured["messages"][0] == {"role": "system", "content": "sys"}
    # tool translated to OpenAI function shape
    assert captured["tools"][0]["type"] == "function"
    assert captured["tools"][0]["function"]["name"] == "score_items"
    # tool_choice forced
    assert captured["tool_choice"] == {"type": "function", "function": {"name": "score_items"}}
    # response normalised to an Anthropic-shaped tool_use block
    block = first_tool_use(resp.content)
    assert block is not None
    assert block.input == {"scores": [{"index": 0}]}
    assert resp.usage.input_tokens == 11
    assert resp.usage.output_tokens == 22


def test_openai_handles_no_tool_call():
    msg = types.SimpleNamespace(tool_calls=None, content="plain text")
    choice = types.SimpleNamespace(message=msg)
    usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=2)
    resp = OpenAIProvider._normalise(
        types.SimpleNamespace(choices=[choice], usage=usage, model="gpt-4o"), "gpt-4o"
    )
    assert first_tool_use(resp.content) is None
    assert resp.content[0].type == "text"


# ---------------------------------------------------------------------------
# CLI backends
# ---------------------------------------------------------------------------


def test_extract_json_object_plain():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_with_prose_and_fence():
    text = 'Here you go:\n```json\n{"verdicts": [{"x": 2}]}\n```\nDone.'
    assert extract_json_object(text) == {"verdicts": [{"x": 2}]}


def test_extract_json_object_with_braces_in_strings():
    assert extract_json_object('prefix {"k": "a {nested} brace"} suffix') == {
        "k": "a {nested} brace"
    }


def test_extract_json_object_empty_raises():
    with pytest.raises(ProviderError):
        extract_json_object("")


def test_extract_json_object_no_object_raises():
    with pytest.raises(ProviderError):
        extract_json_object("no json here")


def test_cli_provider_runs_and_parses(monkeypatch):
    p = ClaudeCodeProvider()
    completed = types.SimpleNamespace(
        returncode=0, stdout='{"scores": []}', stderr=""
    )
    monkeypatch.setattr(
        "frontier_scout.providers.cli_provider.subprocess.run",
        lambda *a, **k: completed,
    )
    resp = p.create(
        model="claude-code-cli",
        max_tokens=100,
        system="sys",
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "score_items", "input_schema": {"type": "object"}}],
    )
    block = first_tool_use(resp.content)
    assert block.name == "score_items"
    assert block.input == {"scores": []}
    assert resp.model == "claude-code-cli"
    assert resp.usage.input_tokens == 0  # CLI runs are $0 / untracked


def test_cli_provider_nonzero_exit_raises(monkeypatch):
    p = CodexProvider()
    completed = types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(
        "frontier_scout.providers.cli_provider.subprocess.run",
        lambda *a, **k: completed,
    )
    with pytest.raises(ProviderError):
        p.create(
            model="codex-cli",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[{"name": "t", "input_schema": {}}],
        )


def test_cli_provider_requires_tool(monkeypatch):
    p = ClaudeCodeProvider()
    with pytest.raises(ProviderError):
        p.create(
            model="claude-code-cli",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=None,
        )


# ---------------------------------------------------------------------------
# call_with_retry routes through the provider
# ---------------------------------------------------------------------------


def test_call_with_retry_uses_provider_create_and_retry():
    from llm_client import call_with_retry

    class _FlakyProvider:
        name = "flaky"

        def __init__(self):
            self.calls = 0

        def model(self, tier):  # noqa: ARG002
            return "x"

        def create(self, **kw):  # noqa: ARG002
            self.calls += 1
            if self.calls < 2:
                raise ValueError("transient")
            return ProviderResponse(content=[ToolUseBlock("t", {})], usage=Usage())

        def is_retryable(self, exc):
            return isinstance(exc, ValueError)

    prov = _FlakyProvider()
    # Speed up backoff.
    import llm_client

    llm_client.BASE_DELAY = 0.0
    out = call_with_retry(prov, "unit", model="x", max_tokens=1, system="s", messages=[])
    assert prov.calls == 2
    assert isinstance(out, ProviderResponse)


def test_call_with_retry_reraises_non_retryable():
    from llm_client import call_with_retry

    class _HardFail:
        name = "hard"

        def model(self, tier):  # noqa: ARG002
            return "x"

        def create(self, **kw):  # noqa: ARG002
            raise RuntimeError("nope")

        def is_retryable(self, exc):  # noqa: ARG002
            return False

    with pytest.raises(RuntimeError):
        call_with_retry(_HardFail(), "unit", model="x", max_tokens=1, system="s", messages=[])


# ---------------------------------------------------------------------------
# cost tracker — defensive + OpenAI/CLI pricing
# ---------------------------------------------------------------------------


def test_cost_tracker_known_and_unknown_models():
    from cost_tracker import _cost

    usage = types.SimpleNamespace(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    # gpt-4o: $2.50 in + $10 out per MTok
    assert _cost("gpt-4o", usage) == pytest.approx(12.50)
    # CLI backends are free
    assert _cost("claude-code-cli", usage) == 0.0
    # unknown model → $0, never a KeyError
    assert _cost("some-future-model", usage) == 0.0
