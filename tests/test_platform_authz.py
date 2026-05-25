import pytest

from frontier_scout.platform.authz.engine import AuthzEngine
from frontier_scout.platform.core.errors import AuthorizationDenied


def test_document_read_is_enforced():
    authz = AuthzEngine()
    authz.add("user:alice", "read", "document:cache-service:runbook")

    assert authz.can_read_document("user:alice", "cache-service:runbook")
    assert not authz.can_read_document("user:bob", "cache-service:runbook")


def test_action_path_requires_tool_scope():
    authz = AuthzEngine()
    authz.add("user:alice", "call", "tool:read")

    assert authz.can_call_tool("user:alice", "read")
    assert not authz.can_call_tool("user:alice", "write")


def test_require_raises_on_denied_relation():
    authz = AuthzEngine()

    with pytest.raises(AuthorizationDenied):
        authz.require("user:bob", "read", "document:secret")


def test_owner_can_approve_service_action():
    authz = AuthzEngine()
    authz.add("user:alice", "owner", "service:cache-service")

    assert authz.can_approve_action("user:alice", "cache-service")
    assert not authz.can_approve_action("user:bob", "cache-service")

