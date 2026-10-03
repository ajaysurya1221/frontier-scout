# tests/test_hook_decision_model.py
"""The opt-in decision model inside the hook: advisory, fail-closed, keyless by default.

A local HTTP server stands in for the decision endpoint so nothing here touches the network.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from frontier_scout.agent_firewall import hook_runtime as hr
from frontier_scout.agent_firewall.lock import policy_hash
from frontier_scout.agent_firewall.models import AgentPolicy, DecisionModelSpec
from frontier_scout.agent_firewall.policy import explain_policy, save_policy

POLICY: dict[str, Any] = {
    "version": 1,
    "allowed_tools": [],
    "blocked_tools": [],
    "allowed_shell_commands": ["pytest", "git status", "git push"],
    "blocked_shell_commands": ["rm -rf", "git push --force"],
    "allowed_file_globs": ["src/**"],
    "protected_file_globs": [".github/workflows/**"],
    "mcp_server_allowlist": [],
    "required_checks": ["pytest"],
    "approval_gates": ["network", "shell"],
    "policy_notes": "",
}


def answers(
    effect: str, confidence: float, destructive: float = 0.0, secret: float = 0.0, privilege: float = 0.0
) -> dict[str, Any]:
    return {
        "effect": {"choice": effect, "confidence": confidence},
        "destructive": destructive,
        "secret_exposure": secret,
        "privilege": privilege,
    }


def api_payload(
    model: str, effect: str, confidence: float, destructive: float = 0.0, secret: float = 0.0, privilege: float = 0.0
) -> dict[str, Any]:
    probabilities = {name: 0.0 for name in hr._EFFECT_CRITERIA}
    probabilities[effect] = confidence
    return {
        "model": model,
        "answers": {
            "effect": {"type": "choice", "choice": effect, "confidence": confidence, "probabilities": probabilities},
            "destructive": {"type": "noul", "noul": destructive},
            "secret_exposure": {"type": "noul", "noul": secret},
            "privilege": {"type": "noul", "noul": privilege},
        },
        "usage": {"input_tokens": 500, "output_tokens": 50},
    }


class FakeEndpoint:
    """A canned decision endpoint; records every request body and Authorization header."""

    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None
        self.raw_body: bytes | None = None
        self.status = 200
        self.delay = 0.0
        self.requests: list[dict[str, Any]] = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                endpoint.requests.append(
                    {"path": self.path, "authorization": self.headers.get("Authorization"), "body": json.loads(body)}
                )
                if endpoint.delay:
                    time.sleep(endpoint.delay)
                raw = (
                    endpoint.raw_body if endpoint.raw_body is not None else json.dumps(endpoint.payload or {}).encode()
                )
                self.send_response(endpoint.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("x-typesafe-request-id", "req_test")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def endpoint() -> Any:
    fake = FakeEndpoint()
    yield fake
    fake.close()


def spec_for(endpoint: FakeEndpoint, **overrides: Any) -> dict[str, Any]:
    spec = DecisionModelSpec(base_url=endpoint.base_url, timeout_seconds=1.0).model_dump()
    spec.update(overrides)
    return spec


# --- combine_with_model: the rule, in isolation -----------------------------------


def test_static_deny_is_never_relaxed() -> None:
    spec = DecisionModelSpec().model_dump()
    assert hr.combine_with_model("deny", answers("read_only", 1.0), spec) == ("deny", "static-deny")


def test_ask_relaxes_only_when_confident_read_only_and_not_risky() -> None:
    spec = DecisionModelSpec().model_dump()
    assert hr.combine_with_model("ask", answers("read_only", 1.0), spec) == ("allow", "relaxed")
    assert hr.combine_with_model("ask", answers("build_or_test", 0.96), spec) == ("allow", "relaxed")
    assert hr.combine_with_model("ask", answers("read_only", 0.9), spec) == ("ask", "abstained")
    assert hr.combine_with_model("ask", answers("read_only", 1.0, destructive=0.1), spec) == ("ask", "abstained")
    assert hr.combine_with_model("ask", answers("writes_inside_repo", 1.0), spec) == ("ask", "abstained")


def test_confident_risk_tightens_allow_and_ask_to_deny() -> None:
    spec = DecisionModelSpec().model_dump()
    assert hr.combine_with_model("allow", answers("destructive", 1.0, destructive=0.95), spec) == ("deny", "tightened")
    assert hr.combine_with_model("ask", answers("read_only", 1.0, secret=0.9), spec) == ("deny", "tightened")
    assert hr.combine_with_model("allow", answers("other", 0.5, privilege=0.89), spec) == ("allow", "abstained")


def test_thresholds_come_from_the_spec() -> None:
    spec = DecisionModelSpec(deny_at=0.6, relax_ask_to_allow_at=0.8).model_dump()
    assert hr.combine_with_model("allow", answers("other", 0.5, destructive=0.6), spec) == ("deny", "tightened")
    assert hr.combine_with_model("ask", answers("read_only", 0.8, destructive=0.2), spec) == ("allow", "relaxed")


# --- ask_decision_model: the wire, against a local endpoint --------------------------


def test_valid_answer_is_parsed_and_the_key_is_sent(endpoint: FakeEndpoint) -> None:
    endpoint.payload = api_payload("jev-1.13.0", "read_only", 1.0)
    result = hr.ask_decision_model("wc -l README.md", spec_for(endpoint), "test-key")
    assert result is not None
    assert result["model"] == "jev-1.13.0" and result["request_id"] == "req_test"
    assert result["answers"]["effect"] == {"choice": "read_only", "confidence": 1.0}
    assert result["answers"]["destructive"] == 0.0
    assert endpoint.requests[0]["path"] == "/v1/systemone"
    assert endpoint.requests[0]["authorization"] == "Bearer test-key"
    assert endpoint.requests[0]["body"]["state"] == {"command": "wc -l README.md"}
    assert endpoint.requests[0]["body"]["model"] == "jev-1.13.0"
    assert set(endpoint.requests[0]["body"]["questions"]) == {"effect", "destructive", "secret_exposure", "privilege"}


@pytest.mark.parametrize(
    "setup",
    [
        lambda e: setattr(e, "payload", api_payload("jev-9.9.9", "read_only", 1.0)),  # wrong model answered
        lambda e: setattr(e, "status", 500),
        lambda e: setattr(e, "status", 429),
        lambda e: setattr(e, "raw_body", b"not json"),
        lambda e: setattr(
            e, "payload", {"model": "jev-1.13.0", "answers": {"effect": {"choice": "nope", "confidence": 1.0}}}
        ),
        lambda e: setattr(
            e, "payload", {"model": "jev-1.13.0", "answers": {"effect": {"choice": "read_only", "confidence": 1.5}}}
        ),
        lambda e: setattr(e, "delay", 1.5),  # slower than the 1 s timeout
    ],
)
def test_any_failure_yields_none(endpoint: FakeEndpoint, setup: Any) -> None:
    setup(endpoint)
    assert hr.ask_decision_model("wc -l README.md", spec_for(endpoint), "test-key") is None


def test_unreachable_endpoint_yields_none() -> None:
    spec = DecisionModelSpec(base_url="http://127.0.0.1:9", timeout_seconds=0.5).model_dump()
    assert hr.ask_decision_model("ls", spec, "test-key") is None


# --- handle_pre_tool_use: end to end, receipts included ------------------------------


def _receipts(repo: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted((repo / ".frontier-scout" / "receipts").glob("*-pre.json"))]


def test_without_the_section_nothing_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    out = hr.handle_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "wc -l README.md"}},
        policy=POLICY,
        policy_hash="h",
        repo=str(tmp_path),
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    receipt = _receipts(tmp_path)[0]
    assert receipt["decision_model"] is None
    assert receipt["decision"] == "ask"


def test_relaxed_ask_is_recorded_without_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoint: FakeEndpoint
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-7f3a")
    endpoint.payload = api_payload("jev-1.13.0", "read_only", 1.0)
    policy = {**POLICY, "decision_model": spec_for(endpoint)}
    out = hr.handle_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "wc -l README.md"}},
        policy=policy,
        policy_hash="h",
        repo=str(tmp_path),
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "Decision model is confident" in out["hookSpecificOutput"]["permissionDecisionReason"]
    receipt = _receipts(tmp_path)[0]
    assert receipt["decision"] == "allow" and receipt["verdict"] == "allow"
    assert receipt["decision_model"]["applied"] == "relaxed"
    assert receipt["decision_model"]["request_id"] == "req_test"
    assert [r["rule_id"] for r in receipt["reasons"]] == ["tool.ask", "decision_model.relaxed"]
    assert "test-key-7f3a" not in json.dumps(receipt)


def test_tightened_allow_denies_a_disguised_destructive_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoint: FakeEndpoint
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    endpoint.payload = api_payload("jev-1.13.0", "destructive", 0.97, destructive=0.98)
    policy = {**POLICY, "decision_model": spec_for(endpoint)}
    out = hr.handle_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "git push origin :main"}},
        policy=policy,
        policy_hash="h",
        repo=str(tmp_path),
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    receipt = _receipts(tmp_path)[0]
    assert receipt["decision_model"]["applied"] == "tightened" and receipt["verdict"] == "block"


def test_static_deny_wins_even_when_the_model_says_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoint: FakeEndpoint
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    endpoint.payload = api_payload("jev-1.13.0", "read_only", 1.0)
    policy = {**POLICY, "decision_model": spec_for(endpoint)}
    out = hr.handle_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}},
        policy=policy,
        policy_hash="h",
        repo=str(tmp_path),
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _receipts(tmp_path)[0]["decision_model"]["applied"] == "static-deny"


def test_no_key_or_unreachable_leaves_the_static_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    policy = {
        **POLICY,
        "decision_model": DecisionModelSpec(base_url="http://127.0.0.1:9", timeout_seconds=0.3).model_dump(),
    }
    out = hr.handle_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "wc -l README.md"}},
        policy=policy,
        policy_hash="h",
        repo=str(tmp_path),
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    receipt = _receipts(tmp_path)[0]
    assert receipt["decision_model"] == {
        "model": "jev-1.13.0",
        "applied": "unavailable",
        "reason": "no key in the environment",
    }

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    out = hr.handle_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "wc -l README.md"}},
        policy=policy,
        policy_hash="h",
        repo=str(tmp_path),
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert _receipts(tmp_path)[-1]["decision_model"]["applied"] == "unavailable"


def test_only_bash_is_consulted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoint: FakeEndpoint) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    endpoint.payload = api_payload("jev-1.13.0", "read_only", 1.0)
    policy = {**POLICY, "decision_model": spec_for(endpoint)}
    hr.handle_pre_tool_use(
        {"tool_name": "Write", "tool_input": {"file_path": "src/x.py"}},
        policy=policy,
        policy_hash="h",
        repo=str(tmp_path),
    )
    assert endpoint.requests == []
    assert _receipts(tmp_path)[0]["decision_model"] is None


# --- policy model, hash and persistence ------------------------------------------------


def test_policy_without_the_section_hashes_and_saves_as_before(tmp_path: Path) -> None:
    policy = AgentPolicy.model_validate(POLICY)
    assert policy.decision_model is None
    assert policy_hash(policy) == policy_hash(POLICY)
    assert policy_hash(policy) == policy_hash({**POLICY, "decision_model": None})
    path = tmp_path / "frontier-scout.policy.json"
    save_policy(policy, str(path))
    assert "decision_model" not in path.read_text()
    assert json.loads(path.read_text()) == POLICY


def test_opting_in_changes_the_hash_and_round_trips(tmp_path: Path) -> None:
    policy = AgentPolicy.model_validate({**POLICY, "decision_model": {"deny_at": 0.8}})
    assert policy.decision_model is not None and policy.decision_model.model == "jev-1.13.0"
    assert policy_hash(policy) != policy_hash(POLICY)
    path = tmp_path / "frontier-scout.policy.json"
    save_policy(policy, str(path))
    reloaded = AgentPolicy.model_validate(json.loads(path.read_text()))
    assert reloaded == policy
    assert "Decision model (opt-in, advisory, fail-closed)" in explain_policy(policy)
    assert "deny at risk >= 0.8" in explain_policy(policy)


def test_spec_rejects_out_of_range_thresholds() -> None:
    with pytest.raises(ValueError):
        DecisionModelSpec(deny_at=0.2)
    with pytest.raises(ValueError):
        DecisionModelSpec(timeout_seconds=0)
