"""CLI backends — Claude Code (``claude``) and Codex (``codex``).

Neither CLI exposes the structured tool-calling API the SDKs do, so we
fall back to a robust convention: embed the tool's JSON Schema in the
prompt, ask for JSON-only output, run the CLI non-interactively, and
parse the first JSON object out of stdout into a
:class:`ToolUseBlock`. Token usage is unknown for CLI runs (the
subscription absorbs it) so usage is reported as zero and the cost
ledger attributes $0.

These backends widen access for users who only have a CLI logged in —
they are best-effort for large batches, not a drop-in replacement for
the API backends on every workload.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from .base import DEEP, ProviderError, ProviderResponse, ToolUseBlock, Usage

_TIMEOUT = int(os.environ.get("FRONTIER_SCOUT_CLI_TIMEOUT", "180"))


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first balanced JSON object out of arbitrary CLI output.

    Tolerates Markdown code fences and leading/trailing prose. Raises
    :class:`ProviderError` if no parseable object is found.
    """
    if not text:
        raise ProviderError("CLI returned empty output")

    # Strip a ```json … ``` fence if present.
    fenced = text
    if "```" in text:
        chunks = text.split("```")
        for chunk in chunks:
            candidate = chunk
            if candidate.lstrip().lower().startswith("json"):
                candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
            candidate = candidate.strip()
            if candidate.startswith("{"):
                fenced = candidate
                break

    start = fenced.find("{")
    if start == -1:
        raise ProviderError("CLI output contained no JSON object")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(fenced)):
        ch = fenced[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = fenced[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError as exc:
                    raise ProviderError(
                        f"CLI output was not valid JSON: {exc}"
                    ) from exc
    raise ProviderError("CLI output had an unbalanced JSON object")


def _build_prompt(
    system: Any,
    messages: list[dict[str, Any]],
    tool: dict[str, Any],
) -> str:
    from .openai_provider import _content_text, _system_text

    parts: list[str] = []
    sys_text = _system_text(system)
    if sys_text:
        parts.append(sys_text)
    for m in messages:
        parts.append(_content_text(m.get("content")))
    schema = json.dumps(tool.get("input_schema", {"type": "object"}), indent=2)
    parts.append(
        "Respond with ONLY a single JSON object that conforms to this JSON "
        f"Schema for the `{tool['name']}` result. No prose, no Markdown fences, "
        f"no commentary — just the JSON object:\n\n{schema}"
    )
    return "\n\n".join(parts)


class _CLIProvider:
    """Shared Claude Code / Codex behaviour."""

    name = "cli"
    binary = ""
    _model_id = "cli"

    # Per-tier model defaults; subclasses set the env prefix + tier defaults.
    _env_prefix = "FRONTIER_SCOUT_CLI"
    _fast_model_default = ""
    _deep_model_default = ""

    def __init__(self, binary: str | None = None) -> None:
        if binary:
            self.binary = binary

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def model(self, tier: str) -> str:
        """Model id to pass via --model/-m for ``tier``.

        Three-state env knob ``{_env_prefix}_{FAST|DEEP}_MODEL``: unset → our
        tier default; "default"/"" → "" (omit the flag, inherit the CLI's own
        configured model); any other value → that value.
        """
        default = self._deep_model_default if tier == DEEP else self._fast_model_default
        raw = os.environ.get(f"{self._env_prefix}_{tier.upper()}_MODEL")
        if raw is None:
            return default
        return "" if raw.strip().lower() in ("", "default") else raw

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
            raise ProviderError(
                f"{self.binary} CLI timed out after {_TIMEOUT}s"
            ) from exc
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
        # A timed-out CLI is often a transient hang (slow cold-start, contention);
        # give the retry wrapper one shot rather than failing the whole scan.
        return isinstance(exc, ProviderError) and "timed out" in str(exc)


class ClaudeCodeProvider(_CLIProvider):
    name = "claude-cli"
    binary = "claude"
    _model_id = "claude-code-cli"
    _env_prefix = "FRONTIER_SCOUT_CLAUDE_CLI"
    _fast_model_default = "sonnet"  # alias → latest Sonnet on the user's plan
    _deep_model_default = "opus"  # alias → latest Opus on the user's plan

    def _command(self, model: str, effort: str) -> list[str]:
        # Hermetic: no MCP autoload, structured JSON out, no agentic tools.
        # NOT --bare (it forces API-key-only auth and breaks OAuth subscribers).
        cmd = [
            self.binary,
            "-p",
            "--strict-mcp-config",
            "--mcp-config",
            # claude CLI 2.x validates this strictly: a bare "{}" is rejected
            # ("Invalid MCP configuration: mcpServers: expected record, received
            # undefined"). Pass an explicit empty mcpServers map — still hermetic
            # (--strict-mcp-config + no servers = no MCP autoload).
            '{"mcpServers": {}}',
            "--output-format",
            "json",
            "--disallowed-tools",
            "Bash Edit Write Read WebFetch WebSearch",
        ]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        return cmd

    @staticmethod
    def _unwrap(stdout: str) -> str:
        """Peel the `claude --output-format json` envelope to the model's text.

        The envelope is ``{"type": "result", "result": "<assistant text>", ...}``
        and the text is in ``.result``. Falls back to the raw stdout if the
        output isn't that envelope OR if ``result`` isn't a string (e.g. an error
        envelope) — in that case ``extract_json_object`` will raise a clear
        ProviderError on the unexpected shape rather than us guessing.
        """
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
    _fast_model_default = ""  # codex has no cheaper tier we pin — inherit its own
    _deep_model_default = ""

    def _command(self, model: str, effort: str) -> list[str]:
        cmd = [self.binary, "exec", "-s", "read-only"]
        if model:
            cmd += ["-m", model]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        cmd.append("-")  # read the prompt from stdin
        return cmd
