import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


SAMPLE_VERDICT = {
    "tool_name": "PydanticAI v1.100.0",
    "verdict": "adopt",
    "category": "security",
    "soc2": "safe",
    "what": "Security release that closes an SSRF bypass.",
    "why_it_matters": "Directly relevant to agent fetch flows in production.",
    "adoption_cost": "1 hour to patch and verify.",
    "next_action": "Patch this sprint and run SSRF regression tests.",
    "source_url": "https://github.com/pydantic/pydantic-ai/releases/tag/v1.100.0",
    "severity": "critical",
    "readiness": 5,
}


def _load_module(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    if "evaluate_from_slack" in sys.modules:
        del sys.modules["evaluate_from_slack"]
    return importlib.import_module("evaluate_from_slack")


def test_requester_label_prefers_slack_id(monkeypatch):
    mod = _load_module(monkeypatch)
    assert mod._requester_label("U0123456789") == "<@U0123456789>"
    assert mod._requester_label("ajay") == "@ajay"


def test_post_reply_builds_descriptive_fallback(monkeypatch):
    mod = _load_module(monkeypatch)

    captured = {}

    def fake_retry(fn, thread_ts, blocks, attachments, **kwargs):
        captured["thread_ts"] = thread_ts
        captured["blocks"] = blocks
        captured["attachments"] = attachments
        captured["kwargs"] = kwargs
        return "172.0001"

    monkeypatch.setattr(mod.slack_post, "_with_slack_retry", fake_retry)

    ok = mod._post_reply(SAMPLE_VERDICT, channel="C123", thread_ts="171.0001", user="ajay")
    assert ok is True
    assert captured["thread_ts"] == "171.0001"
    assert "Deep evaluation" in captured["blocks"][0]["text"]["text"]

    fallback = captured["kwargs"]["text_fallback"]
    assert "Deep evaluation for" in fallback
    assert "next action" in fallback.lower()


def test_post_reply_returns_false_on_error(monkeypatch):
    mod = _load_module(monkeypatch)

    def raise_retry(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod.slack_post, "_with_slack_retry", raise_retry)
    ok = mod._post_reply(SAMPLE_VERDICT, channel="C123", thread_ts="171.0001", user="ajay")
    assert ok is False
