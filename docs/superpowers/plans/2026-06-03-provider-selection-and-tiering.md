# Provider Selection, Two-Tier Models & Gateway Interop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider selection a single, transparent, switchable source of truth; restore the cheap-scout / strong-judge two-tier design (model **and** reasoning) on the CLI backends; fix the CLI scout timeout by isolating the subprocess; add a custom OpenAI-compatible `base_url` provider for gateway interop; and surface/switch the provider in the TUI with dead-end-free edges.

**Architecture:** A new `providers/select.py` owns the precedence ladder (flag › saved preference › auto › ask-once/none) and a cached accessor; both the headless scan path (`scripts/scout.py`) and the TUI (`tui3/data.py`) consume it, collapsing today's two divergent detection paths. CLI backends gain real `--model`/`--effort` (claude) and `-m`/`-c model_reasoning_effort` (codex) plus hermetic-subprocess flags. A thin `OpenAICompatibleProvider` subclass injects `base_url`. The TUI mirrors the existing `RepoSwitcherScreen` for a `ProviderSwitcherScreen`.

**Tech Stack:** Python 3.11+, the `anthropic`/`openai` SDKs, Textual 8.2, pytest. Run the suite with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q` (bare `python` is not on PATH in this env; the 3 `tests/test_implement.py` failures are pre-existing, env-only — ignore locally). Spec: [docs/superpowers/specs/2026-06-02-provider-selection-and-tiering-design.md](../specs/2026-06-02-provider-selection-and-tiering-design.md).

---

## Ground rules (carry into every task)

1. **Persist no secrets** — the preferences file holds only the provider *name*.
2. **CLI subprocesses stay hermetic** — no MCP autoload, no inherited agent env; never `--bare` (it breaks OAuth/subscription auth).
3. **One source of truth** — the TUI indicator must reflect exactly what a scan will use. Never reintroduce a second detection path.
4. **TUI invariants** — every new renderable goes through `app._paint(...)` and `glyphs(app.state.unicode)`; refresh a list by `.update()` on one id-tagged widget, never `remove_children()` + remount with the same ids.
5. **Commit after each task** once its tests pass.

## File structure

| File | New/Modify | Responsibility |
|---|---|---|
| `frontier_scout/preferences.py` | **Create** | Read/write `~/.frontier-scout/preferences.json` (provider name only). |
| `frontier_scout/providers/select.py` | **Create** | `Selection`, `select()` ladder, cached `current_provider()` / `reset_provider()`. |
| `frontier_scout/providers/openai_provider.py` | Modify | `OpenAICompatibleProvider` subclass with `base_url`. |
| `frontier_scout/providers/__init__.py` | Modify | Register `openai-compatible` in `PROVIDER_NAMES`, detection, `_build`, `available_providers`. |
| `frontier_scout/providers/cli_provider.py` | Modify | Tiered `model()`, hermetic invocation, `--model`/`--effort`/`-c`, JSON-envelope unwrap, retry-once, model-unavailable fallback. |
| `scripts/scout.py` | Modify | `_provider()` delegates to `select.current_provider()`; fix stale docstring. |
| `frontier_scout/tui3/state.py` | Modify | Add `provider_reason` field. |
| `frontier_scout/tui3/data.py` | Modify | `_detect_provider` → `select.select()`; provider rows include `openai-compatible`. |
| `frontier_scout/tui3/app.py` | Modify | Header reason badge + clickable header; `P` binding; `action_switch_provider`/`switch_provider`; ask-once; no-provider demo; failure recovery. |
| `frontier_scout/tui3/overlays.py` | Modify | `ProviderSwitcherScreen` (mirrors `RepoSwitcherScreen`). |
| `frontier_scout/tui3/panes.py` | Modify | Clickable provider rows; show active FAST/DEEP models. |
| `frontier_scout/report.py`, `scripts/judge.py` | Modify | Replace stale "Sonnet→Sonnet→Opus" narrative with per-provider tiers. |
| `tests/test_providers.py`, `tests/test_preferences.py`, `tests/test_select.py` | Create/Modify | Cover ladder, tiers, isolation flags, base_url, preferences. |

---

## Task 1: Preferences store (`frontier_scout/preferences.py`)

**Files:**
- Create: `frontier_scout/preferences.py`
- Test: `tests/test_preferences.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preferences.py
"""Provider preference persistence — name only, never secrets."""
from __future__ import annotations

import pytest

from frontier_scout import preferences


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    return tmp_path


def test_no_preference_returns_none(home):
    assert preferences.preferred_provider() is None


def test_round_trip(home):
    preferences.save_preferred_provider("claude-cli")
    assert preferences.preferred_provider() == "claude-cli"
    # Only the name is persisted — assert no secret-shaped keys exist.
    data = preferences.load_preferences()
    assert set(data) <= {"schema", "provider"}


def test_corrupt_file_degrades_to_none(home):
    (home / "preferences.json").write_text("{ not valid json", encoding="utf-8")
    assert preferences.preferred_provider() is None
    assert preferences.load_preferences() == {}


def test_overwrite_keeps_single_value(home):
    preferences.save_preferred_provider("openai")
    preferences.save_preferred_provider("anthropic")
    assert preferences.preferred_provider() == "anthropic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_preferences.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'frontier_scout.preferences'`

- [ ] **Step 3: Write the implementation**

```python
# frontier_scout/preferences.py
"""Persisted Mission Control preferences.

Stored in the existing Frontier Scout home dir (``FRONTIER_SCOUT_HOME`` /
``~/.frontier-scout``). Holds NO secrets — only the chosen provider *name*.
A missing or corrupt file degrades to "no preference" so selection always
falls through to auto-detect rather than crashing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frontier_scout import store

_SCHEMA = 1


def _path() -> Path:
    return store.home_dir() / "preferences.json"


def load_preferences() -> dict[str, Any]:
    try:
        with _path().open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def preferred_provider() -> str | None:
    val = load_preferences().get("provider")
    return val if isinstance(val, str) and val else None


def save_preferred_provider(name: str) -> None:
    store.init_home()  # ensure the home dir exists
    data = {"schema": _SCHEMA, "provider": name}
    path = _path()
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    tmp.replace(path)  # atomic on POSIX
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_preferences.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/preferences.py tests/test_preferences.py
git commit -m "feat(providers): persist provider preference (name only, no secrets)"
```

---

## Task 2: Selection module (`frontier_scout/providers/select.py`)

**Files:**
- Create: `frontier_scout/providers/select.py`
- Test: `tests/test_select.py`

This is the single source of truth. It layers *flag › saved preference › auto › ask-once/none* on top of the existing `available_providers()` primitive, and caches the built provider so the headless scan path and the TUI agree.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_select.py
"""The single provider-selection ladder used by both TUI and headless CLI."""
from __future__ import annotations

import pytest

from frontier_scout.providers import select as sel


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                "FRONTIER_SCOUT_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    sel.reset_provider()


def test_flag_wins(monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_PROVIDER", "openai")
    s = sel.select()
    assert (s.name, s.reason) == ("openai", "flag")


def test_saved_preference(monkeypatch):
    from frontier_scout import preferences
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # pragma: allowlist secret
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: True)
    preferences.save_preferred_provider("claude-cli")
    s = sel.select()
    assert (s.name, s.reason) == ("claude-cli", "preference")


def test_preference_ignored_when_unavailable(monkeypatch):
    from frontier_scout import preferences
    preferences.save_preferred_provider("claude-cli")  # not on PATH per fixture
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    s = sel.select()
    assert (s.name, s.reason) == ("openai", "auto")


def test_must_ask_when_ambiguous_and_interactive(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # pragma: allowlist secret
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: True)
    assert sel.select(interactive=True).reason == "must_ask"
    # headless never asks — it takes the deterministic auto pick
    assert sel.select(interactive=False).reason == "auto"


def test_auto_single(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    assert sel.select().name == "openai"


def test_none_available():
    assert sel.select().reason == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_select.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'frontier_scout.providers.select'`

- [ ] **Step 3: Write the implementation**

```python
# frontier_scout/providers/select.py
"""Single source of truth for provider selection (which provider, and why).

Layered on the low-level ``available_providers()`` / ``resolve_provider()``
primitives so BOTH the TUI and the headless scan resolve identically — the UI
indicator can never disagree with what a scan actually used.

Ladder (highest first): explicit flag/env › saved preference › auto-detect.
When >1 provider is available, no preference is saved, and the caller is
interactive (the TUI), ``select()`` returns ``must_ask`` so the UI can prompt
once and remember. Headless callers never get ``must_ask``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from frontier_scout import preferences

from . import available_providers, resolve_provider
from .base import LLMProvider


@dataclass(frozen=True)
class Selection:
    name: str   # "" when reason is "must_ask" or "none"
    reason: str  # "flag" | "preference" | "auto" | "must_ask" | "none"


def select(*, cli_override: str | None = None, interactive: bool = False) -> Selection:
    pinned = (cli_override or os.environ.get("FRONTIER_SCOUT_PROVIDER") or "").strip().lower()
    if pinned:
        return Selection(pinned, "flag")
    avail = available_providers()
    pref = preferences.preferred_provider()
    if pref and pref in avail:
        return Selection(pref, "preference")
    if interactive and len(avail) > 1:
        return Selection("", "must_ask")
    if avail:
        return Selection(avail[0], "auto")
    return Selection("", "none")


_CACHED: LLMProvider | None = None


def current_provider() -> LLMProvider:
    """The built provider for this process, cached. Honors flag + preference.

    Raises ``ProviderUnavailable`` (with the ``--demo`` hint) when nothing is
    usable, exactly as ``resolve_provider()`` does today.
    """
    global _CACHED
    if _CACHED is None:
        chosen = select()
        # resolve_provider("") with no name re-runs auto + raises the canonical
        # ProviderUnavailable message; with a name it validates availability.
        _CACHED = resolve_provider(chosen.name or None)
    return _CACHED


def reset_provider() -> None:
    """Drop the cache so a runtime switch takes effect on the next scan."""
    global _CACHED
    _CACHED = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_select.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/providers/select.py tests/test_select.py
git commit -m "feat(providers): single selection ladder (flag>preference>auto>ask-once)"
```

---

## Task 3: Route the headless scan through `select`

**Files:**
- Modify: `scripts/scout.py:556-564` (the `_provider()` cache)
- Test: `tests/test_select.py` (add cache-invalidation test)

**Why:** so a saved preference and runtime switches are honored by `frontier-scout scout` too, and the scout cache can be invalidated on switch.

- [ ] **Step 1: Add the failing test**

```python
# append to tests/test_select.py
def test_current_provider_caches_and_resets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    first = sel.current_provider()
    assert first is sel.current_provider()      # cached (same object)
    sel.reset_provider()
    assert sel.current_provider() is not first  # rebuilt after reset
```

- [ ] **Step 2: Run to verify it passes already** (current_provider exists from Task 2)

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_select.py -q`
Expected: PASS

- [ ] **Step 3: Point `scripts/scout.py` at the shared cache**

Replace the existing block at `scripts/scout.py:556-564`:

```python
_PROVIDER = None


def _provider():
    """Resolve the live provider once (lazily) and reuse it."""
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = resolve_provider()
    return _PROVIDER
```

with a delegation to the single source of truth:

```python
def _provider():
    """The live provider — resolved via the shared selection ladder so a saved
    preference (and TUI runtime switches) are honored here too."""
    from frontier_scout.providers.select import current_provider

    return current_provider()
```

(Leave the existing `from frontier_scout.providers import FAST, resolve_provider` import at `scripts/scout.py:48` — `resolve_provider` may still be referenced elsewhere; if a linter flags it as unused after this change, narrow the import to `FAST` only.)

- [ ] **Step 4: Run the provider + scout-touching suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_providers.py tests/test_select.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scout.py tests/test_select.py
git commit -m "refactor(scout): resolve provider via the shared selection cache"
```

---

## Task 4: Tiered `model()` on the CLI backends (three-state override)

**Files:**
- Modify: `frontier_scout/providers/cli_provider.py` (the `_CLIProvider.model` + subclass attrs)
- Test: `tests/test_providers.py`

The CLI `model(tier)` currently ignores `tier`. Make it return the per-tier model string to pass after `--model`/`-m`, honoring a three-state env knob: **unset** → our default; **explicit value** → that value; **`default`/empty** → `""` (omit the flag, inherit the CLI's own default).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_providers.py  (DEEP/FAST already imported at top)
def test_claude_cli_tier_models(monkeypatch):
    for v in ("FRONTIER_SCOUT_CLAUDE_CLI_FAST_MODEL", "FRONTIER_SCOUT_CLAUDE_CLI_DEEP_MODEL"):
        monkeypatch.delenv(v, raising=False)
    p = ClaudeCodeProvider()
    assert p.model(FAST) == "sonnet"
    assert p.model(DEEP) == "opus"


def test_claude_cli_model_override_and_sentinel(monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_CLAUDE_CLI_DEEP_MODEL", "opus-4-1")
    assert ClaudeCodeProvider().model(DEEP) == "opus-4-1"
    monkeypatch.setenv("FRONTIER_SCOUT_CLAUDE_CLI_FAST_MODEL", "default")
    assert ClaudeCodeProvider().model(FAST) == ""  # sentinel → inherit CLI default


def test_codex_cli_defaults_to_inherit(monkeypatch):
    for v in ("FRONTIER_SCOUT_CODEX_CLI_FAST_MODEL", "FRONTIER_SCOUT_CODEX_CLI_DEEP_MODEL"):
        monkeypatch.delenv(v, raising=False)
    p = CodexProvider()
    # codex has no cheaper tier we pin by default — inherit its own model for both
    assert p.model(FAST) == ""
    assert p.model(DEEP) == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_providers.py -k cli_tier -q`
Expected: FAIL — `model(FAST)` returns the fixed `_model_id` (`"claude-code-cli"`), not `"sonnet"`.

- [ ] **Step 3: Implement tiered `model()`**

In `frontier_scout/providers/cli_provider.py`, add `from .base import DEEP` to the existing import line:

```python
from .base import DEEP, ProviderError, ProviderResponse, ToolUseBlock, Usage
```

Replace `_CLIProvider.model` (currently `cli_provider.py:118-119`):

```python
    # Per-tier model defaults; subclasses set the env prefix + tier defaults.
    _env_prefix = "FRONTIER_SCOUT_CLI"
    _fast_model_default = ""
    _deep_model_default = ""

    def model(self, tier: str) -> str:
        """Model id to pass via --model/-m for ``tier``.

        Three-state env knob ``{_env_prefix}_{FAST|DEEP}_MODEL``:
        unset → our tier default; "default"/"" → "" (omit flag, inherit the
        CLI's own configured model); any other value → that value.
        """
        default = self._deep_model_default if tier == DEEP else self._fast_model_default
        raw = os.environ.get(f"{self._env_prefix}_{tier.upper()}_MODEL")
        if raw is None:
            return default
        return "" if raw.strip().lower() in ("", "default") else raw
```

Set the per-backend attributes on the subclasses (`cli_provider.py:167-182`):

```python
class ClaudeCodeProvider(_CLIProvider):
    name = "claude-cli"
    binary = "claude"
    _model_id = "claude-code-cli"
    _env_prefix = "FRONTIER_SCOUT_CLAUDE_CLI"
    _fast_model_default = "sonnet"   # alias → latest Sonnet on the user's plan
    _deep_model_default = "opus"     # alias → latest Opus on the user's plan

    def _command(self, model: str, effort: str) -> list[str]:
        ...  # implemented in Task 5


class CodexProvider(_CLIProvider):
    name = "codex-cli"
    binary = "codex"
    _model_id = "codex-cli"
    _env_prefix = "FRONTIER_SCOUT_CODEX_CLI"
    _fast_model_default = ""   # codex has no cheaper tier we pin — inherit its own
    _deep_model_default = ""

    def _command(self, model: str, effort: str) -> list[str]:
        ...  # implemented in Task 5
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_providers.py -k cli -q`
Expected: PASS (the new tier tests pass; existing CLI tests still pass — `_command` is finished in Task 5, but `model()` tests don't call it).

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/providers/cli_provider.py tests/test_providers.py
git commit -m "feat(cli): tiered model() with three-state override on CLI backends"
```

---

## Task 5: Hermetic CLI invocation — flags, effort, JSON envelope, retry

**Files:**
- Modify: `frontier_scout/providers/cli_provider.py` (`create()`, `_command()`, `is_retryable`, a `_unwrap` hook)
- Test: `tests/test_providers.py`

This is the timeout fix. Isolate the subprocess, pass the tier model + judge effort, parse a structured envelope, and make timeouts retryable.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_providers.py
import subprocess as _subprocess


def _fake_run(captured):
    def _run(cmd, **kw):
        captured["cmd"] = cmd
        captured["input"] = kw.get("input")
        return types.SimpleNamespace(returncode=0, stdout=captured["stdout"], stderr="")
    return _run


def test_claude_cli_command_is_hermetic_and_tiered(monkeypatch):
    cap = {"stdout": '{"type":"result","result":"{\\"scores\\": []}"}'}
    monkeypatch.setattr(_subprocess, "run", _fake_run(cap))
    monkeypatch.setattr("frontier_scout.providers.cli_provider.subprocess.run", _fake_run(cap))
    p = ClaudeCodeProvider()
    resp = p.create(
        model="sonnet", max_tokens=100, system="sys",
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "score_items", "input_schema": {"type": "object"}}],
    )
    cmd = cap["cmd"]
    assert cmd[:2] == ["claude", "-p"]
    assert "--strict-mcp-config" in cmd
    assert "--mcp-config" in cmd and "{}" in cmd          # no MCP autoload
    assert "--output-format" in cmd and "json" in cmd     # structured output
    assert "--bare" not in cmd                            # OAuth preserved
    assert "--model" in cmd and "sonnet" in cmd           # tier model pinned
    assert "--effort" not in cmd                          # scout pass: no thinking
    # claude --output-format json envelope unwrapped, then JSON extracted
    assert first_tool_use(resp.content).input == {"scores": []}


def test_claude_cli_judge_adds_effort(monkeypatch):
    cap = {"stdout": '{"type":"result","result":"{\\"verdicts\\": []}"}'}
    monkeypatch.setattr("frontier_scout.providers.cli_provider.subprocess.run", _fake_run(cap))
    p = ClaudeCodeProvider()
    p.create(
        model="opus", max_tokens=100, system="sys",
        messages=[{"role": "user", "content": "judge"}],
        tools=[{"name": "judge", "input_schema": {"type": "object"}}],
        thinking={"type": "adaptive"},   # the judge requests reasoning
    )
    cmd = cap["cmd"]
    assert "--effort" in cmd and "high" in cmd


def test_codex_cli_command(monkeypatch):
    cap = {"stdout": '{"verdicts": []}'}
    monkeypatch.setattr("frontier_scout.providers.cli_provider.subprocess.run", _fake_run(cap))
    p = CodexProvider()
    p.create(
        model="", max_tokens=100, system="sys",
        messages=[{"role": "user", "content": "judge"}],
        tools=[{"name": "judge", "input_schema": {"type": "object"}}],
        thinking={"type": "adaptive"},
    )
    cmd = cap["cmd"]
    assert cmd[:2] == ["codex", "exec"]
    assert "read-only" in cmd                              # hermetic sandbox
    assert "-m" not in cmd                                 # model="" → inherit codex default
    assert any(a.startswith("model_reasoning_effort=") for a in cmd)  # judge reasoning


def test_cli_timeout_is_retryable(monkeypatch):
    def _boom(cmd, **kw):
        raise _subprocess.TimeoutExpired(cmd, 180)
    monkeypatch.setattr("frontier_scout.providers.cli_provider.subprocess.run", _boom)
    p = ClaudeCodeProvider()
    with pytest.raises(ProviderError) as exc:
        p.create(model="sonnet", max_tokens=1, system="s",
                 messages=[{"role": "user", "content": "x"}],
                 tools=[{"name": "t", "input_schema": {}}])
    assert "timed out" in str(exc.value)
    assert p.is_retryable(exc.value) is True   # was False before — one retry now
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_providers.py -k "hermetic or judge_adds_effort or codex_cli_command or timeout_is_retryable" -q`
Expected: FAIL — `_command()` takes no args yet / no isolation flags / `is_retryable` returns False.

- [ ] **Step 3: Implement `create()`, `_command()`, unwrap, retry**

In `frontier_scout/providers/cli_provider.py`, rewrite `_CLIProvider.create` (currently `cli_provider.py:124-161`) and add helpers:

```python
    def _command(self, model: str, effort: str) -> list[str]:
        raise NotImplementedError

    @staticmethod
    def _unwrap(stdout: str) -> str:
        """Default: return stdout unchanged (codex prints the final message)."""
        return stdout

    def _effort(self, thinking: dict[str, Any] | None) -> str:
        """Reasoning effort for this call. Only the judge passes ``thinking``.

        ``{_env_prefix}_DEEP_EFFORT``: unset → "high"; "default"/"" → "" (omit);
        else the given level (low|medium|high|xhigh|max)."""
        if thinking is None:
            return ""
        raw = os.environ.get(f"{self._env_prefix}_DEEP_EFFORT")
        if raw is None:
            return "high"
        return "" if raw.strip().lower() in ("", "default") else raw

    def create(
        self,
        *,
        model: str,
        max_tokens: int,  # noqa: ARG002 — CLI manages its own limits
        system: Any,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,  # noqa: ARG002
        thinking: dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> ProviderResponse:
        if not tools:
            raise ProviderError(f"{self.binary} backend requires a tool schema")
        prompt = _build_prompt(system, messages, tools[0])
        effort = self._effort(thinking)
        try:
            proc = subprocess.run(
                self._command(model, effort),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(f"{self.binary} CLI not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"{self.binary} CLI timed out after {_TIMEOUT}s") from exc
        if proc.returncode != 0:
            raise ProviderError(
                f"{self.binary} CLI exited {proc.returncode}: {proc.stderr[:400]}"
            )
        payload = extract_json_object(self._unwrap(proc.stdout))
        return ProviderResponse(
            content=[ToolUseBlock(name=tools[0]["name"], input=payload)],
            usage=Usage(),
            model=self._model_id,
        )

    def is_retryable(self, exc: BaseException) -> bool:
        # A timed-out CLI is often a transient cold-start; give the retry
        # wrapper one shot rather than failing the whole scan outright.
        return isinstance(exc, ProviderError) and "timed out" in str(exc)
```

Implement the subclass `_command`/`_unwrap` (replace the stub `_command`s from Task 4):

```python
class ClaudeCodeProvider(_CLIProvider):
    name = "claude-cli"
    binary = "claude"
    _model_id = "claude-code-cli"
    _env_prefix = "FRONTIER_SCOUT_CLAUDE_CLI"
    _fast_model_default = "sonnet"
    _deep_model_default = "opus"

    def _command(self, model: str, effort: str) -> list[str]:
        # Hermetic: no MCP autoload, structured JSON out, no agentic tools.
        # NOT --bare (it forces API-key-only auth and breaks OAuth subscribers).
        cmd = [
            self.binary, "-p",
            "--strict-mcp-config", "--mcp-config", "{}",
            "--output-format", "json",
            "--disallowed-tools", "Bash Edit Write Read WebFetch WebSearch",
        ]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        return cmd

    @staticmethod
    def _unwrap(stdout: str) -> str:
        # `claude --output-format json` returns an envelope; the model's text is
        # in .result. Fall back to the raw stdout if it isn't the envelope.
        try:
            obj = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            return stdout
        if isinstance(obj, dict) and isinstance(obj.get("result"), str):
            return obj["result"]
        return stdout


class CodexProvider(_CLIProvider):
    name = "codex-cli"
    binary = "codex"
    _model_id = "codex-cli"
    _env_prefix = "FRONTIER_SCOUT_CODEX_CLI"
    _fast_model_default = ""
    _deep_model_default = ""

    def _command(self, model: str, effort: str) -> list[str]:
        cmd = [self.binary, "exec", "-s", "read-only"]
        if model:
            cmd += ["-m", model]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        cmd.append("-")  # read the prompt from stdin
        return cmd
```

> **Verify during implementation (not a placeholder — a check):** confirm `--disallowed-tools` is the correct flag name and that `model_reasoning_effort` is codex's config key, via `claude --help | grep -i disallowed` and `codex --help` / `codex exec --help`. Adjust the literals if the installed versions differ; the test asserts the *shape* (`read-only` present, a `model_reasoning_effort=` token present), which is version-stable.

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_providers.py -q`
Expected: PASS — including the existing `test_cli_provider_runs_and_parses` (its stdout `'{"scores": []}'` is not the envelope, so `_unwrap` returns it unchanged and `extract_json_object` still parses it).

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/providers/cli_provider.py tests/test_providers.py
git commit -m "fix(cli): hermetic invocation + tier model/effort + retryable timeout"
```

---

## Task 6: The `openai-compatible` provider (gateway interop)

**Files:**
- Modify: `frontier_scout/providers/openai_provider.py` (subclass), `frontier_scout/providers/__init__.py` (register/detect)
- Test: `tests/test_providers.py`

A thin subclass that injects `base_url`; only available when `OPENAI_BASE_URL` (or the namespaced var) is set, and mutually exclusive with the stock `openai` provider.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_providers.py
from frontier_scout.providers import available_providers as _avail
from frontier_scout.providers.openai_provider import OpenAICompatibleProvider


def test_openai_compatible_tier_models(monkeypatch):
    for v in ("FRONTIER_SCOUT_OPENAI_COMPAT_FAST_MODEL",
              "FRONTIER_SCOUT_OPENAI_COMPAT_DEEP_MODEL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("FRONTIER_SCOUT_OPENAI_COMPAT_FAST_MODEL", "local-small")
    p = OpenAICompatibleProvider()
    assert p.model(FAST) == "local-small"
    # DEEP unset → falls back to FAST (single-tier collapse, never crashes)
    assert p.model(DEEP) == "local-small"


def test_openai_compatible_passes_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")  # pragma: allowlist secret
    captured = {}

    class _OpenAIMod:
        def OpenAI(self, **kw):  # noqa: N802
            captured.update(kw)
            return "client"

    monkeypatch.setitem(__import__("sys").modules, "openai", _OpenAIMod())
    p = OpenAICompatibleProvider()
    _ = p.client
    assert captured["base_url"] == "http://localhost:4000/v1"


def test_base_url_swaps_openai_for_compatible(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "FRONTIER_SCOUT_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert "openai" in _avail() and "openai-compatible" not in _avail()
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:4000/v1")
    out = _avail()
    assert "openai-compatible" in out and "openai" not in out  # mutually exclusive
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_providers.py -k "compatible or base_url" -q`
Expected: FAIL — `OpenAICompatibleProvider` undefined; `available_providers` has no `openai-compatible`.

- [ ] **Step 3: Add the subclass** (append to `frontier_scout/providers/openai_provider.py`)

```python
_COMPAT_DEFAULT_FAST = ""  # no built-in default — driven by the user's endpoint
_COMPAT_DEFAULT_DEEP = ""


class OpenAICompatibleProvider(OpenAIProvider):
    """OpenAI-compatible endpoint (LiteLLM/Bifrost/vLLM/Ollama/OpenLLM/…).

    Identical to :class:`OpenAIProvider` except the client is pointed at
    ``OPENAI_BASE_URL`` (or ``FRONTIER_SCOUT_OPENAI_BASE_URL``). Reaching the
    whole gateway ecosystem costs us one ``base_url`` — no extra dependency.
    """

    name = "openai-compatible"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key
            or os.environ.get("FRONTIER_SCOUT_OPENAI_COMPAT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or "not-needed"  # many local servers accept any key
        )
        self._base_url = (
            base_url
            or os.environ.get("FRONTIER_SCOUT_OPENAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
        )

    @property
    def client(self) -> Any:
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def model(self, tier: str) -> str:
        fast = os.environ.get("FRONTIER_SCOUT_OPENAI_COMPAT_FAST_MODEL", _COMPAT_DEFAULT_FAST)
        if tier == "deep":
            return os.environ.get("FRONTIER_SCOUT_OPENAI_COMPAT_DEEP_MODEL", fast)
        return fast
```

> Note the DEEP fallback: if `FRONTIER_SCOUT_OPENAI_COMPAT_DEEP_MODEL` is unset, DEEP reuses the FAST model (single-tier collapse) so a one-model gateway never needs two-tier config.

- [ ] **Step 4: Register + detect** in `frontier_scout/providers/__init__.py`

Add the import (top, near the other provider imports):

```python
from .openai_provider import OpenAICompatibleProvider, OpenAIProvider
```

Add to `__all__` and `PROVIDER_NAMES` (`__init__.py:55`):

```python
PROVIDER_NAMES = ("anthropic", "openai", "openai-compatible", "claude-cli", "codex-cli")
```

Add a detector + `_build` branch + `available_providers` slot:

```python
def _has_openai_base_url() -> bool:
    return bool(
        os.environ.get("FRONTIER_SCOUT_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
    )
```

In `_build()` add before the unknown-provider raise:

```python
    if name == "openai-compatible":
        return OpenAICompatibleProvider()
```

In `available_providers()` replace the OpenAI slot (`__init__.py:91-92`) so base_url swaps stock `openai` for `openai-compatible`:

```python
    if _has_openai():
        out.append("openai-compatible" if _has_openai_base_url() else "openai")
```

- [ ] **Step 5: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_providers.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontier_scout/providers/openai_provider.py frontier_scout/providers/__init__.py tests/test_providers.py
git commit -m "feat(providers): openai-compatible base_url backend (gateway interop)"
```

---
## Task 7: TUI state + data wiring + header reason badge

**Files:**
- Modify: `frontier_scout/tui3/state.py` (`AppState`), `frontier_scout/tui3/data.py` (`_detect_provider`, `initial_state`, `providers`), `frontier_scout/tui3/app.py` (`_header_text` + a module helper)
- Test: `tests/test_tui3_provider.py`

These TUI tasks use **pure-function** unit tests (no Textual `Pilot`) to stay fast and non-flaky; CLAUDE.md notes some tui3 Pilot tests run the real demo scan and time out on a cluttered tree.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tui3_provider.py
"""TUI provider surface — pure helpers (no Pilot)."""
from __future__ import annotations

import pytest

from frontier_scout.tui3 import data
from frontier_scout.tui3.app import _provider_reason_label
from frontier_scout.tui3.state import AppState


def test_appstate_has_provider_reason():
    s = AppState(repo="/x", repo_name="x")
    assert s.provider_reason == ""
    assert s.with_(provider_reason="auto").provider_reason == "auto"


@pytest.mark.parametrize("reason,expected", [
    ("flag", " · pinned"), ("preference", " · pinned"),
    ("auto", " · auto"), ("demo", ""), ("none", ""), ("must_ask", ""),
])
def test_reason_label(reason, expected):
    assert _provider_reason_label(reason) == expected


def test_detect_provider_demo():
    assert data._detect_provider(demo=True) == ("local", "demo")


def test_detect_provider_none(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
              "FRONTIER_SCOUT_PROVIDER"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    assert data._detect_provider(demo=False) == ("local", "none")
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -q`
Expected: FAIL — `AppState` has no `provider_reason`; `_provider_reason_label` undefined; `_detect_provider` returns a `str`, not a tuple.

- [ ] **Step 3a: Add the state field**

In `frontier_scout/tui3/state.py`, inside the `AppState` dataclass, add `provider_reason` directly below the existing `provider:` field:

```python
    provider: str = "local"
    provider_reason: str = ""   # "flag"|"preference"|"auto"|"demo"|"none"
```

(Keep whatever default the existing `provider:` field already has; only the new `provider_reason` line is added.)

- [ ] **Step 3b: Rewrite `_detect_provider` + its call site** in `frontier_scout/tui3/data.py`

Replace `_detect_provider` (`data.py:146-158`):

```python
def _detect_provider(*, demo: bool) -> tuple[str, str]:
    """Return (provider_name, reason) via the single selection ladder so the
    header can never disagree with what a scan uses. Never crashes."""
    if demo:
        return ("local", "demo")
    try:
        from frontier_scout.providers import select

        s = select.select(interactive=False)
        return ("local", "none") if s.reason == "none" else (s.name, s.reason)
    except Exception:  # noqa: BLE001 — opening state must never crash
        return ("local", "none")
```

Update the `initial_state` construction (`data.py:85-94`) to unpack the tuple:

```python
    prov_name, prov_reason = _detect_provider(demo=demo)
    return AppState(
        repo=repo_path,
        repo_name=_repo_name(repo_path),
        languages=languages,
        provider=prov_name,
        provider_reason=prov_reason,
        verdicts=verdicts,
        funnel=funnel,
        demo=demo,
        unread=_unread_count(),
    )
```

- [ ] **Step 3c: Add the header badge helper + use it** in `frontier_scout/tui3/app.py`

Add a module-level helper (near `_dossier_result_lines`, `app.py:1243`):

```python
def _provider_reason_label(reason: str) -> str:
    return {"flag": " · pinned", "preference": " · pinned", "auto": " · auto"}.get(reason, "")
```

Update the provider line in `_header_text` (`app.py:237-240`):

```python
        if not micro:
            prov = self.state.provider
            if " " in prov:
                prov = prov.split(" ", 1)[0].lower()
            left += f"  [#6e8aa1]{g['dot']} {prov}{_provider_reason_label(self.state.provider_reason)}[/]"
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/tui3/state.py frontier_scout/tui3/data.py frontier_scout/tui3/app.py tests/test_tui3_provider.py
git commit -m "feat(tui): provider reason in state + header badge, via the selection ladder"
```

---

## Task 8: Provider switcher (overlay + switch + binding + clickable rows)

**Files:**
- Modify: `frontier_scout/tui3/data.py` (`provider_choices`), `frontier_scout/tui3/overlays.py` (`ProviderSwitcherScreen`), `frontier_scout/tui3/app.py` (binding + `action_switch_provider` + `switch_provider`), `frontier_scout/tui3/panes.py` (clickable provider rows)
- Test: `tests/test_tui3_provider.py`

- [ ] **Step 1: Add the failing tests**

```python
# append to tests/test_tui3_provider.py
from frontier_scout.tui3.overlays import ProviderSwitcherScreen


def test_provider_choices_marks_active_and_availability(monkeypatch):
    monkeypatch.setattr("frontier_scout.tui3.data.available_providers",
                        lambda: ["claude-cli"], raising=False)
    # available_providers is imported lazily inside provider_choices; patch source:
    monkeypatch.setattr("frontier_scout.providers.available_providers",
                        lambda: ["claude-cli"])
    rows = data.provider_choices(current="claude-cli")
    by_id = {r["id"]: r for r in rows}
    assert by_id["claude-cli"]["available"] and by_id["claude-cli"]["active"]
    assert not by_id["openai"]["available"]
    assert by_id["openai"]["hint"]            # tells the user how to enable it
    assert by_id["openai-compatible"]["label"] == "Custom endpoint (your gateway)"


def test_switcher_only_selects_available():
    choices = [
        {"id": "anthropic", "label": "Anthropic API", "available": False, "hint": "set key", "active": False},
        {"id": "claude-cli", "label": "Claude (CLI subscription)", "available": True, "hint": "", "active": True},
    ]
    scr = ProviderSwitcherScreen(choices)
    assert scr._selectable() == [1]          # the unavailable row is skipped
    assert scr._sel == 1                      # starts on the active/available row
    assert "set key" in scr._list_markup()    # unavailable row shows its hint
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -k "provider_choices or switcher" -q`
Expected: FAIL — `provider_choices` / `ProviderSwitcherScreen` undefined.

- [ ] **Step 3a: Add `provider_choices`** to `frontier_scout/tui3/data.py` (below `providers()`):

```python
def provider_choices(current: str | None = None) -> list[dict[str, Any]]:
    """Switchable providers with human labels + availability (for the switcher)."""
    try:
        from frontier_scout.providers import available_providers

        avail = set(available_providers())
    except Exception:  # noqa: BLE001 — the switcher must never crash
        avail = set()
    labels = {
        "anthropic": ("Anthropic API", "set ANTHROPIC_API_KEY"),
        "openai": ("OpenAI API", "set OPENAI_API_KEY"),
        "openai-compatible": ("Custom endpoint (your gateway)", "set OPENAI_BASE_URL"),
        "claude-cli": ("Claude (CLI subscription)", "log in to the claude CLI"),
        "codex-cli": ("Codex (CLI subscription)", "log in to the codex CLI"),
    }
    cur = (current or "").lower()
    out: list[dict[str, Any]] = []
    for pid, (label, fix) in labels.items():
        ok = pid in avail
        out.append({
            "id": pid, "label": label, "available": ok,
            "hint": "" if ok else fix, "active": cur == pid,
        })
    return out
```

- [ ] **Step 3b: Add `ProviderSwitcherScreen`** to `frontier_scout/tui3/overlays.py` (after `RepoSwitcherScreen`, ~`overlays.py:660`):

```python
class ProviderSwitcherScreen(_Modal):
    """Switch the active LLM provider. j/k + ⏎ (and mouse). Persists the choice
    and re-scouts. Unavailable providers are shown greyed with how to enable them."""

    BINDINGS = [Binding("escape", "dismiss", "close", show=False)]

    def __init__(self, choices: list[dict], *, first_run: bool = False) -> None:
        super().__init__()
        self._choices = choices
        self._first_run = first_run
        avail = self._selectable()
        active = next((i for i, c in enumerate(choices) if c.get("active")), None)
        self._sel = active if (active in avail) else (avail[0] if avail else 0)

    def _selectable(self) -> list[int]:
        return [i for i, c in enumerate(self._choices) if c.get("available")]

    def body(self) -> Iterable[Static]:
        yield self._static("[#24d6a8 b]Switch provider[/]")
        intro = (
            "More than one engine is available — pick one to start. Change it "
            "anytime with [#24d6a8 b]P[/]."
            if self._first_run
            else "Pick the engine for scouting & judging. Remembered for next time."
        )
        yield self._static(f"[#6e8aa1]{intro}[/]")
        line_map = {
            i: (lambda n=c["id"]: self._choose(n))
            for i, c in enumerate(self._choices) if c.get("available")
        }
        yield LineClickStatic(self.app._paint(self._list_markup()), line_map, id="prov-list")
        yield self._static("\n[#6e8aa1]j/k move · ⏎ select · esc cancel[/]")

    def _list_markup(self) -> str:
        lines = []
        for i, c in enumerate(self._choices):
            mark = "[#24d6a8 b]▸ [/]" if i == self._sel else "  "
            if c.get("available"):
                act = " [#24d6a8]· active[/]" if c.get("active") else ""
                lines.append(f"{mark}[#d9f7ff]{c['label']}[/]{act}")
            else:
                lines.append(f"  [#41566b]{c['label']} — {c['hint']}[/]")
        return "\n".join(lines)

    def _repaint(self) -> None:
        try:
            self.query_one("#prov-list", LineClickStatic).update(self.app._paint(self._list_markup()))
        except Exception:  # noqa: BLE001
            pass

    def on_key(self, event) -> None:  # noqa: ANN001 — Textual Key event
        sel = self._selectable()
        if not sel:
            return
        if event.key in ("j", "down"):
            event.stop()
            nxt = [i for i in sel if i > self._sel]
            self._sel = nxt[0] if nxt else sel[-1]
            self._repaint()
        elif event.key in ("k", "up"):
            event.stop()
            prv = [i for i in sel if i < self._sel]
            self._sel = prv[-1] if prv else sel[0]
            self._repaint()
        elif event.key == "enter":
            event.stop()
            self._choose(self._choices[self._sel]["id"])

    def _choose(self, name: str) -> None:
        self.app.pop_screen()
        self.app.switch_provider(name)
```

- [ ] **Step 3c: Binding + actions + `switch_provider`** in `frontier_scout/tui3/app.py`

Add to `BINDINGS` (after the `w` repo-switch binding, `app.py:61`):

```python
        Binding("P", "switch_provider", "switch provider", show=False),
```

Add the action + the switch method (next to `action_switch_repo` / `switch_repo`, `app.py:971-998`):

```python
    def action_switch_provider(self) -> None:
        from frontier_scout.tui3.overlays import ProviderSwitcherScreen

        self.push_screen(ProviderSwitcherScreen(data.provider_choices(self.state.provider)))

    def switch_provider(self, name: str) -> None:
        """Pin ``name`` for this session, persist it, drop the scout cache, re-scout."""
        import os

        from frontier_scout import preferences
        from frontier_scout.providers import select

        os.environ["FRONTIER_SCOUT_PROVIDER"] = name
        try:
            preferences.save_preferred_provider(name)
        except Exception:  # noqa: BLE001 — persistence is best-effort
            pass
        select.reset_provider()  # next scan rebuilds with the new choice
        self.state = self.state.with_(provider=name, provider_reason="preference")
        self._refresh_chrome()
        try:
            self.notify(f"provider → {name} · re-scouting")
        except Exception:  # noqa: BLE001
            pass
        self._scanning = False
        self.run_scout(dry_run=self.state.demo)
```

- [ ] **Step 3d: Make the Settings provider rows clickable** in `frontier_scout/tui3/panes.py`

At the top of `panes.py`, ensure `ClickStatic` is importable (it already backs other clickable rows; confirm the import line includes it, e.g. `from frontier_scout.tui3.widgets import ClickStatic`). In `_settings` (`panes.py:270-279`), wrap the provider row in a `ClickStatic` that opens the switcher:

```python
    for p in data.providers():
        present = p["present"]
        dot = f"[#24d6a8]{gl['dot']}[/]" if present else f"[#6e8aa1]{gl['ring']}[/]"
        bcol = "#24d6a8" if present else "#6e8aa1"
        mark = " [#24d6a8]· active[/]" if active and active in (p["id"].lower(), p["name"].lower()) else ""
        box.compose_add_child(ClickStatic(
            app._paint(f"{dot} [#d9f7ff]{p['name']}[/]  [{bcol}]{p['badge']}[/]  [#6e8aa1]{p['cost']}[/]{mark}"),
            app.action_switch_provider,
        ))
        if p["detail"]:
            box.compose_add_child(_S(app, f"    [#6e8aa1]{p['detail']}[/]"))
```

(Also add a hint line under the Provider header: `box.compose_add_child(_S(app, "[#6e8aa1]click a row or press [#24d6a8 b]P[/] to switch[/]"))`.)

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -q`
Expected: PASS

- [ ] **Step 5: Verify the TUI still boots (no DuplicateIds / import errors)**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -c "import frontier_scout.tui3.app, frontier_scout.tui3.overlays, frontier_scout.tui3.panes; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add frontier_scout/tui3/ tests/test_tui3_provider.py
git commit -m "feat(tui): provider switcher overlay + P binding + clickable Settings rows"
```

---

## Task 9: Ask-once first-run picker · no-provider demo nudge · failure recovery

**Files:**
- Modify: `frontier_scout/tui3/app.py` (`on_mount` hook, `_maybe_ask_provider`, `on_work_failed` + a module helper)
- Test: `tests/test_tui3_provider.py`

- [ ] **Step 1: Add the failing test** (the pure failure-compass formatter)

```python
# append to tests/test_tui3_provider.py
from frontier_scout.tui3.app import _failure_compass


def test_failure_compass_offers_recovery_for_scout():
    msg = _failure_compass("scout", "claude CLI timed out after 180s")
    assert "timed out" in msg
    assert "switch" in msg and "retry" in msg and "--demo" in msg


def test_failure_compass_plain_for_other_kinds():
    msg = _failure_compass("guard", "boom")
    assert "boom" in msg
    assert "retry" not in msg     # recovery affordance is scout-specific
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -k failure_compass -q`
Expected: FAIL — `_failure_compass` undefined.

- [ ] **Step 3a: Add the failure-compass helper + use it** in `frontier_scout/tui3/app.py`

Module-level (next to `_provider_reason_label`):

```python
def _failure_compass(kind: str, error: str) -> str:
    hint = (
        " [#6e8aa1]· press [#24d6a8 b]P[/] switch · [#24d6a8 b]r[/] retry · or --demo[/]"
        if kind == "scout" else ""
    )
    return f"[#ff6b6b]{kind} failed: {error}[/]{hint}"
```

Replace the body of `on_work_failed` (`app.py:1238-1240`):

```python
    def on_work_failed(self, message: WorkFailed) -> None:
        self._scanning = False
        self._set("#mc-compass", _failure_compass(message.kind, message.error))
```

- [ ] **Step 3b: Ask-once + no-provider nudge on mount**

Add the helper method to `MissionControlApp`:

```python
    def _maybe_ask_provider(self) -> None:
        """First-run provider flow: prompt once when ambiguous, nudge when none."""
        if self.state.demo:
            return
        from frontier_scout.providers import select

        s = select.select(interactive=True)
        if s.reason == "must_ask":
            from frontier_scout.tui3.overlays import ProviderSwitcherScreen

            self.push_screen(
                ProviderSwitcherScreen(data.provider_choices(self.state.provider), first_run=True)
            )
        elif s.reason == "none":
            self._set(
                "#mc-compass",
                "[#e3c26f]no provider connected[/] "
                "[#6e8aa1]· press [#24d6a8 b]P[/] to set one up, or relaunch with --demo[/]",
            )
```

Call it at the end of the app's existing `on_mount` (locate `def on_mount` in `app.py`; append the call as the last statement so the first paint is already on screen):

```python
        self._maybe_ask_provider()
```

> No-provider does **not** crash or exit: the app is already initialized with `provider="local"`; this only adds the nudge. A scout attempted with no provider surfaces `ProviderUnavailable` through `on_work_failed`, which now shows the recovery affordance.

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_tui3_provider.py -q`
Expected: PASS

- [ ] **Step 5: Boot check + commit**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -c "import frontier_scout.tui3.app; print('ok')"`
Expected: `ok`

```bash
git add frontier_scout/tui3/app.py tests/test_tui3_provider.py
git commit -m "feat(tui): ask-once picker, no-provider demo nudge, scout failure recovery"
```

---

## Task 10: Retire the stale Sonnet→Sonnet→Opus narrative (docs)

**Files:**
- Modify: `frontier_scout/report.py:617-619`, `scripts/scout.py:12-14`, `scripts/judge.py:2-5`

Docs-only — no behavior change, so no TDD; verify with grep.

- [ ] **Step 1: Generalize the report cost table** — replace `report.py:617-619`:

```
| Scout score pass (fast tier) | $0.15 |
| Scout verdict pass (fast tier) | $0.04 |
| Optional judge pass (deep tier) | $0.12 |
```

(Add a one-line note below the table: `Exact models depend on the active provider — see the provider switcher / Settings.`)

- [ ] **Step 2: Generalize the scout pipeline docstring** — replace `scripts/scout.py:12-14`:

```
      → fast-tier score pass (0–10 + category)
      → fast-tier verdict pass (structured tool use)
      → optional deep-tier judge pass (gated by ``JUDGE_ENABLED``)
```

- [ ] **Step 3: Generalize the judge header** — replace `scripts/judge.py:2-5` prose so it describes the **deep tier (strong model + reasoning)** over the **fast-tier verdicts**, rather than naming Opus/Sonnet. Leave the `JUDGE_MODEL`/`thinking` *code* untouched (behavior is unchanged; only the comment narrative is generalized).

- [ ] **Step 4: Verify no stale narrative remains**

Run: `grep -rniE "sonnet (score|verdict) pass|opus judge|Sonnet-generated" frontier_scout/report.py scripts/scout.py scripts/judge.py`
Expected: no matches (the model-name *constants* may still mention claude-opus — that's fine; only the misleading pipeline *narrative* is gone).

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/report.py scripts/scout.py scripts/judge.py
git commit -m "docs: describe scout/judge as fast/deep tiers, not hardcoded Sonnet/Opus"
```

---

## Task 11: Finalize — full suite, changelog, version

**Files:**
- Modify: `CHANGELOG.md`, `pyproject.toml`, `frontier_scout/__init__.py`

- [ ] **Step 1: Run the full suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q`
Expected: all green except the 3 known env-only `tests/test_implement.py` failures (they shell out to `python`). If anything else fails, STOP and fix before continuing.

- [ ] **Step 2: Add a CHANGELOG entry** under a new `## [1.7.0]` heading: single selection ladder; CLI timeout fix (hermetic subprocess); restored scout/judge two-tier (model + reasoning) on CLI; `openai-compatible` base_url provider; TUI provider switcher + ask-once + failure recovery.

- [ ] **Step 3: Bump the version** to `1.7.0` in both `pyproject.toml` (`version = "1.7.0"`) and `frontier_scout/__init__.py` (`__version__ = "1.7.0"`). Keep them identical (release.yml guard).

- [ ] **Step 4: Final commit**

```bash
git add CHANGELOG.md pyproject.toml frontier_scout/__init__.py
git commit -m "chore: v1.7.0 — provider selection, two-tier CLI, gateway interop"
```

> **Out of scope for this plan:** tagging, the GitHub Release, and PyPI publish (the relax→merge→restore dance + deployment approval) — that's the release runbook in CLAUDE.md, run after this branch is reviewed and merged.

---

## Self-review

**1. Spec coverage** — every spec stream maps to a task:
- Stream 1 (selection module) → Tasks 2, 3. Stream 2 (preferences) → Task 1.
- Stream 3 (CLI timeout fix) → Task 5. Stream 4 (two-tier + reasoning) → Tasks 4, 5.
- Stream 5 (openai-compatible) → Task 6. Stream 6 (TUI surface/switch/ask-once/nudge/recovery) → Tasks 7, 8, 9. Stream 7 (docs + tests) → Task 10 + tests throughout.

**2. Type consistency** — `select()` reasons (`flag|preference|auto|must_ask|none`) are consistent across Tasks 2/7/9; `_detect_provider` returns the demo/none extras (`demo`, `none`) which `_provider_reason_label` maps to `""` (Task 7). `switch_provider` stores `provider_reason="preference"` → label "· pinned" (consistent). `_CLIProvider._command(self, model, effort)` signature is identical in the Task 4 stub and the Task 5 implementation. `provider_choices` dict keys (`id|label|available|hint|active`) match what `ProviderSwitcherScreen` reads.

**3. No-placeholder check** — every code step carries full code; the two "verify during implementation" notes (codex `model_reasoning_effort` key, claude `--disallowed-tools` name) are *verification commands to run*, not unfilled blanks, and the tests assert version-stable shapes.

**4. Known fix folded in** — `OpenAICompatibleProvider.model()` in Task 6 was corrected inline to drop a pointless self-conditional; DEEP falls back to the FAST model when its env override is unset (single-tier collapse), so a one-model gateway never needs two-tier config.

