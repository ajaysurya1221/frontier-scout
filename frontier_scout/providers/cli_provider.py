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

from .base import ProviderError, ProviderResponse, ToolUseBlock, Usage

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
                    raise ProviderError(f"CLI output was not valid JSON: {exc}") from exc
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

    def __init__(self, binary: str | None = None) -> None:
        if binary:
            self.binary = binary

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def model(self, tier: str) -> str:  # noqa: ARG002 — CLI uses its own model
        return self._model_id

    def _command(self) -> list[str]:
        raise NotImplementedError

    def create(
        self,
        *,
        model: str,
        max_tokens: int,  # noqa: ARG002 — CLI manages its own limits
        system: Any,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,  # noqa: ARG002
        thinking: dict[str, Any] | None = None,  # noqa: ARG002
        extra_body: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> ProviderResponse:
        if not tools:
            raise ProviderError(f"{self.binary} backend requires a tool schema")
        prompt = _build_prompt(system, messages, tools[0])
        try:
            proc = subprocess.run(
                self._command(),
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
        payload = extract_json_object(proc.stdout)
        return ProviderResponse(
            content=[ToolUseBlock(name=tools[0]["name"], input=payload)],
            usage=Usage(),
            model=self._model_id,
        )

    def is_retryable(self, exc: BaseException) -> bool:  # noqa: ARG002
        return False


class ClaudeCodeProvider(_CLIProvider):
    name = "claude-cli"
    binary = "claude"
    _model_id = "claude-code-cli"

    def _command(self) -> list[str]:
        return [self.binary, "-p"]


class CodexProvider(_CLIProvider):
    name = "codex-cli"
    binary = "codex"
    _model_id = "codex-cli"

    def _command(self) -> list[str]:
        return [self.binary, "exec", "-"]
