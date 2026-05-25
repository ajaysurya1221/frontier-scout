"""Typed execution packet compiler with stable prompt prefixes."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

from ..core.types import Citation, ToolCall


class PromptBlock(BaseModel):
    name: str
    content: str
    cacheable: bool = True


class ExecutionPacket(BaseModel):
    task: str
    actor: str
    static_prefix: list[PromptBlock]
    dynamic_context: list[PromptBlock]
    citations: list[Citation] = Field(default_factory=list)
    allowed_tools: list[ToolCall] = Field(default_factory=list)

    @property
    def prefix_hash(self) -> str:
        raw = "\n".join(block.content for block in self.static_prefix)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class ContextCompiler:
    def compile(
        self,
        *,
        task: str,
        actor: str,
        policy: str,
        citations: list[Citation],
        allowed_tools: list[ToolCall],
    ) -> ExecutionPacket:
        static_prefix = [
            PromptBlock(name="identity", content="You are Frontier Scout Incident Change Scout."),
            PromptBlock(name="policy", content=policy),
            PromptBlock(name="schemas", content="Return a remediation plan with citations and approval state."),
            PromptBlock(
                name="tool_contracts",
                content="Only call tools listed in allowed_tools; high-risk actions require approval.",
            ),
        ]
        dynamic_context = [
            PromptBlock(name="task", content=task, cacheable=False),
            PromptBlock(
                name="evidence",
                content="\n".join(f"[{c.id}] {c.text}" for c in citations),
                cacheable=False,
            ),
        ]
        return ExecutionPacket(
            task=task,
            actor=actor,
            static_prefix=static_prefix,
            dynamic_context=dynamic_context,
            citations=citations,
            allowed_tools=allowed_tools,
        )
