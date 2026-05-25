"""End-to-end Incident Change Scout workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..authz.engine import AuthzEngine
from ..context.compiler import ContextCompiler
from ..core.ids import stable_id
from ..core.types import NodeKind, NodeResult, ToolCall
from ..evals.harness import EvalCase, EvalScore, grade_answer, load_cases
from ..gateway.model_gateway import ModelGateway
from ..memory.store import ingest_directory
from ..orchestration.runtime import DCGRuntime, GraphState, NodeSpec
from ..retrieval.hybrid import HybridRetriever
from ..tools.registry import ToolDefinition, ToolRegistry, read_only_plan_tool


def run_incident_demo(
    *,
    corpus_dir: Path,
    ticket_path: Path,
    output_dir: Path,
    actor: str = "user:alice",
    approved: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    store = ingest_directory(corpus_dir)
    authz = _demo_authz(actor, store)
    retriever = HybridRetriever(store, authz)
    compiler = ContextCompiler()
    gateway = ModelGateway()
    tools = ToolRegistry(authz=authz, allowlisted_mcp_servers={"local-demo"})
    tools.register(
        ToolDefinition(name="record_plan", scope="read", risk="low", requires_approval=False),
        read_only_plan_tool,
    )
    tools.register(
        ToolDefinition(name="propose_config_change", scope="write", risk="high", requires_approval=True),
        lambda args: {"status": "proposed", "change": args},
    )

    ticket = ticket_path.read_text()
    runtime = DCGRuntime(trace_path=output_dir / "trace.jsonl", audit_path=output_dir / "audit.jsonl")

    def plan(state: GraphState) -> NodeResult:
        state.data["plan"] = (
            "Retrieve cache-service evidence, reason over dependencies, then require approval before write."
        )
        return NodeResult(node="plan", status="ok", output={"plan": state.data["plan"]})

    def retrieve(state: GraphState) -> NodeResult:
        results = retriever.retrieve(ticket, actor=actor, limit=6)
        citations = [citation for result in results for citation in result.citations]
        state.data["citations"] = [c.model_dump() for c in citations]
        state.data["retrieved"] = [result.chunk.text for result in results]
        return NodeResult(
            node="retrieve",
            status="ok",
            output={"citations": len(citations)},
            provenance=[c.provenance for c in citations],
        )

    def reason(state: GraphState) -> NodeResult:
        citations = [result.citations[0] for result in retriever.retrieve(ticket, actor=actor, limit=6)]
        packet = compiler.compile(
            task=ticket,
            actor=actor,
            policy="Use only cited evidence. High-risk changes require approval.",
            citations=citations,
            allowed_tools=[
                ToolCall(name="record_plan", risk="low", scope="read"),
                ToolCall(name="propose_config_change", risk="high", scope="write", approved=approved),
            ],
        )
        response = gateway.complete(packet)
        state.data["packet"] = packet.model_dump()
        state.data["answer"] = response.text
        state.data["prefix_hash"] = packet.prefix_hash
        return NodeResult(
            node="reason",
            status="ok",
            output={"model": response.model, "prefix_hash": packet.prefix_hash},
        )

    def act(state: GraphState) -> NodeResult:
        low_risk = tools.call(actor, ToolCall(name="record_plan", args={"plan": state.data["answer"]}, scope="read"))
        if not approved:
            return NodeResult(
                node="act",
                status="interrupt",
                output={"approval_required": "propose_config_change", "record_plan": low_risk},
            )
        high_risk = tools.call(
            actor,
            ToolCall(
                name="propose_config_change",
                args={"service": "cache-service", "change": "lower rollout concurrency"},
                scope="write",
                risk="high",
                approved=True,
            ),
        )
        return NodeResult(node="act", status="ok", output={"record_plan": low_risk, "proposed_change": high_risk})

    def review(state: GraphState) -> NodeResult:
        return NodeResult(
            node="review",
            status="ok",
            output={"review": "citations-bound", "approval_state": "approved" if approved else "interrupted"},
        )

    def finalize(state: GraphState) -> NodeResult:
        answer = _render_answer(state)
        state.data["final_answer"] = answer
        (output_dir / "answer.md").write_text(answer)
        return NodeResult(node="finalize", status="ok", output={"answer_path": str(output_dir / "answer.md")})

    node_handlers: tuple[tuple[NodeKind, Any], ...] = (
        ("plan", plan),
        ("retrieve", retrieve),
        ("reason", reason),
        ("act", act),
        ("review", review),
        ("finalize", finalize),
    )
    for kind, handler in node_handlers:
        runtime.add_node(NodeSpec(kind=kind), handler)

    state = runtime.run(actor=actor, task=ticket)
    if state.interrupted:
        finalize(state)
    eval_score = _run_eval(output_dir, ticket, state)
    summary = {
        "run_id": state.run_id,
        "trace_path": str(output_dir / "trace.jsonl"),
        "audit_path": str(output_dir / "audit.jsonl"),
        "answer_path": str(output_dir / "answer.md"),
        "eval_path": str(output_dir / "eval.json"),
        "interrupted": state.interrupted,
        "eval": eval_score.model_dump(),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _demo_authz(actor: str, store: Any) -> AuthzEngine:
    authz = AuthzEngine()
    authz.add(actor, "tool:read", "platform")
    authz.add(actor, "call", "tool:read")
    authz.add(actor, "owner", "service:cache-service")
    authz.add(actor, "approver", "service:cache-service")
    for doc in store.documents.values():
        if doc.service == "cache-service":
            authz.add(actor, "read", f"document:{doc.id}")
    return authz


def _render_answer(state: GraphState) -> str:
    citations = state.data.get("citations", [])
    lines = [
        "# Incident Change Scout Answer",
        "",
        state.data.get("answer", "No answer generated."),
        "",
        "## Approval",
        "",
        (
            "High-risk config changes are paused for owner approval."
            if state.interrupted
            else "Owner approval was present for the high-risk proposal."
        ),
        "",
        "## Citations",
        "",
    ]
    for citation in citations[:6]:
        lines.append(f"- `{citation['id']}` from `{citation['provenance']['path']}`")
    return "\n".join(lines) + "\n"


def _run_eval(output_dir: Path, ticket: str, state: GraphState) -> EvalScore:
    eval_path = Path("evals/incident_change_scout/golden.json")
    cases = load_cases(eval_path) if eval_path.exists() else []
    if cases:
        case = cases[0]
    else:
        case = EvalCase(
            id=stable_id("case", ticket),
            question=ticket,
            required_terms=["cache", "approval"],
            min_citations=2,
        )
    answer = state.data.get("final_answer") or state.data.get("answer", "")
    citation_count = len(state.data.get("citations", []))
    score = grade_answer(case, answer, citation_count)
    (output_dir / "eval.json").write_text(score.model_dump_json(indent=2) + "\n")
    return score
