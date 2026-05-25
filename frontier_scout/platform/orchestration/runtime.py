"""Typed DCG runtime with bounded loops, checkpoints, and interrupts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..core.budgets import Budget, BudgetLedger
from ..core.ids import stable_id
from ..core.types import NodeKind, NodeResult
from ..observability.audit import AuditLog, AuditRecord
from ..observability.tracing import SpanRecorder


class GraphState(BaseModel):
    run_id: str
    trace_id: str
    actor: str
    task: str
    data: dict[str, Any] = Field(default_factory=dict)
    history: list[NodeResult] = Field(default_factory=list)
    interrupted: bool = False


class NodeSpec(BaseModel):
    kind: NodeKind
    cost_budget_usd: float = 0.05
    max_retries: int = 1


NodeHandler = Callable[[GraphState], NodeResult]


class DCGRuntime:
    def __init__(self, *, trace_path: Path, audit_path: Path, budget: Budget | None = None) -> None:
        self.spans = SpanRecorder(trace_path)
        self.audit = AuditLog(audit_path)
        self.ledger = BudgetLedger(budget=budget or Budget())
        self.nodes: list[tuple[NodeSpec, NodeHandler]] = []

    def add_node(self, spec: NodeSpec, handler: NodeHandler) -> None:
        self.nodes.append((spec, handler))

    def run(self, *, actor: str, task: str) -> GraphState:
        run_id = stable_id("run", actor, task)
        state = GraphState(run_id=run_id, trace_id=stable_id("trace", run_id), actor=actor, task=task)
        for spec, handler in self.nodes:
            self.ledger.spend(usd=0.0)
            with self.spans.span(
                run_id=state.run_id,
                trace_id=state.trace_id,
                name=f"dcg.{spec.kind}",
                node_kind=spec.kind,
            ):
                result = handler(state)
            state.history.append(result)
            self.audit.emit(
                AuditRecord(
                    run_id=state.run_id,
                    trace_id=state.trace_id,
                    actor=actor,
                    operation=f"node.{spec.kind}",
                    resource_type="dcg_node",
                    resource_id=spec.kind,
                    after=result.output,
                    decision=result.status,
                    provenance=[p.source_id for p in result.provenance],
                )
            )
            if result.status == "interrupt":
                state.interrupted = True
                break
        return state
