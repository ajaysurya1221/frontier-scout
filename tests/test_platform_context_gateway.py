from pathlib import Path

import pytest

from frontier_scout.platform.context.compiler import ContextCompiler
from frontier_scout.platform.context.prompt_registry import load_prompt
from frontier_scout.platform.core.budgets import Budget, BudgetLedger
from frontier_scout.platform.core.types import Citation, Provenance, ToolCall
from frontier_scout.platform.gateway.model_gateway import ModelGateway


def _citation() -> Citation:
    return Citation(
        id="c1",
        text="cache-service depends on redis-cluster",
        provenance=Provenance(source_id="doc1", path="runbook.md", checksum="sha"),
    )


def test_context_compiler_keeps_static_prefix_hash_stable():
    compiler = ContextCompiler()
    first = compiler.compile(task="one", actor="user:alice", policy="policy", citations=[_citation()], allowed_tools=[])
    second = compiler.compile(
        task="two",
        actor="user:alice",
        policy="policy",
        citations=[_citation()],
        allowed_tools=[],
    )

    assert first.prefix_hash == second.prefix_hash
    assert first.citations[0].provenance.path == "runbook.md"


def test_prompt_registry_requires_metadata():
    prompt = load_prompt(Path("prompts/incident_change_scout/remediation_plan.md"))

    assert prompt.eval_id == "incident-cache-storm-001"


def test_gateway_enforces_budget():
    packet = ContextCompiler().compile(
        task="cache issue",
        actor="user:alice",
        policy="policy",
        citations=[_citation()],
        allowed_tools=[ToolCall(name="record_plan")],
    )
    gateway = ModelGateway(ledger=BudgetLedger(budget=Budget(max_tokens=1)))

    with pytest.raises(RuntimeError):
        gateway.complete(packet)
