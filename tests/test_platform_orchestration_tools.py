import pytest

from frontier_scout.platform.authz.engine import AuthzEngine
from frontier_scout.platform.core.errors import ApprovalRequired
from frontier_scout.platform.core.types import NodeResult, ToolCall
from frontier_scout.platform.orchestration.runtime import DCGRuntime, NodeSpec
from frontier_scout.platform.tools.registry import ToolDefinition, ToolRegistry, read_only_plan_tool


def test_runtime_interrupts_and_emits_trace_and_audit(tmp_path):
    runtime = DCGRuntime(trace_path=tmp_path / "trace.jsonl", audit_path=tmp_path / "audit.jsonl")

    runtime.add_node(NodeSpec(kind="plan"), lambda state: NodeResult(node="plan", status="ok", output={"ok": True}))
    runtime.add_node(
        NodeSpec(kind="act"),
        lambda state: NodeResult(node="act", status="interrupt", output={"approval_required": True}),
    )
    runtime.add_node(NodeSpec(kind="finalize"), lambda state: NodeResult(node="finalize", status="ok"))

    state = runtime.run(actor="user:alice", task="test")

    assert state.interrupted
    assert len(state.history) == 2
    assert (tmp_path / "trace.jsonl").read_text().count("dcg.") == 2
    assert (tmp_path / "audit.jsonl").read_text().count("node.") == 2


def test_tool_registry_enforces_scope_and_approval():
    authz = AuthzEngine()
    authz.add("user:alice", "call", "tool:read")
    registry = ToolRegistry(authz=authz, allowlisted_mcp_servers={"local-demo"})
    registry.register(ToolDefinition(name="record_plan", scope="read"), read_only_plan_tool)
    registry.register(
        ToolDefinition(name="write_config", scope="write", risk="high", requires_approval=True),
        lambda args: args,
    )

    assert registry.call("user:alice", ToolCall(name="record_plan", scope="read"))["status"] == "ok"
    with pytest.raises(PermissionError):
        registry.call("user:alice", ToolCall(name="write_config", scope="write", approved=True))

    authz.add("user:alice", "call", "tool:write")
    with pytest.raises(ApprovalRequired):
        registry.call("user:alice", ToolCall(name="write_config", scope="write"))
