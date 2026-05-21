"""
Unit tests for the Slack interactivity Lambda. No network, no AWS calls.

Coverage:
  - slack_verify: valid signature, invalid signature, stale timestamp
  - handler routing: slash command dispatch, button dispatch, url_verification
  - radar_query: empty input → usage message, no-mirror → fallback
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))


SIGNING_SECRET = "test-signing-secret"  # pragma: allowlist secret


def _sign(body: str, ts: int) -> dict:
    basestring = f"v0:{ts}:{body}".encode("utf-8")
    sig = "v0=" + hmac.new(
        SIGNING_SECRET.encode(), basestring, hashlib.sha256
    ).hexdigest()
    return {
        "x-slack-request-timestamp": str(ts),
        "x-slack-signature": sig,
        "content-type": "application/x-www-form-urlencoded",
    }


# ── slack_verify ─────────────────────────────────────────────────────────────

class TestSlackVerify:
    def test_valid_signature_passes(self):
        from slack_verify import verify_slack_request
        body = "command=/radar&text=mem0"
        ts = int(time.time())
        headers = _sign(body, ts)
        assert verify_slack_request(SIGNING_SECRET, headers, body)

    def test_invalid_signature_fails(self):
        from slack_verify import verify_slack_request
        body = "command=/radar&text=mem0"
        ts = int(time.time())
        headers = _sign(body, ts)
        headers["x-slack-signature"] = "v0=" + "0" * 64
        assert not verify_slack_request(SIGNING_SECRET, headers, body)

    def test_stale_timestamp_rejected(self):
        from slack_verify import verify_slack_request
        body = "command=/radar&text=mem0"
        ts = int(time.time()) - 60 * 10   # 10 minutes ago
        headers = _sign(body, ts)
        assert not verify_slack_request(SIGNING_SECRET, headers, body)

    def test_missing_headers_rejected(self):
        from slack_verify import verify_slack_request
        assert not verify_slack_request(SIGNING_SECRET, {}, "")
        assert not verify_slack_request(SIGNING_SECRET, {"x-slack-signature": "v0=abc"}, "")

    def test_missing_secret_rejected(self):
        from slack_verify import verify_slack_request
        body = "x"
        ts = int(time.time())
        headers = _sign(body, ts)
        assert not verify_slack_request("", headers, body)


# ── handler routing ──────────────────────────────────────────────────────────

class TestHandlerRouting:
    def _event(self, body: str, headers: dict) -> dict:
        return {
            "headers": headers,
            "body": body,
            "isBase64Encoded": False,
        }

    def test_url_verification_challenge(self, monkeypatch):
        import handler
        monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)
        body = json.dumps({"type": "url_verification", "challenge": "abc123"})
        ts = int(time.time())
        headers = _sign(body, ts)
        headers["content-type"] = "application/json"

        resp = handler.lambda_handler(self._event(body, headers), None)
        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == {"challenge": "abc123"}

    def test_bad_signature_returns_401(self, monkeypatch):
        import handler
        monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)
        body = "command=/radar&text=mem0"
        headers = _sign(body, int(time.time()))
        headers["x-slack-signature"] = "v0=bad"

        resp = handler.lambda_handler(self._event(body, headers), None)
        assert resp["statusCode"] == 401

    def test_slash_radar_routed(self, monkeypatch):
        import handler, radar_query
        monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)

        called = {}
        def fake_radar(text, user_id):
            called["text"] = text
            called["user_id"] = user_id
            return {"statusCode": 200, "body": "{}"}
        monkeypatch.setattr(radar_query, "radar", fake_radar)

        body = "command=%2Fradar&text=mem0&user_id=U001"
        headers = _sign(body, int(time.time()))
        resp = handler.lambda_handler(self._event(body, headers), None)
        assert resp["statusCode"] == 200
        assert called == {"text": "mem0", "user_id": "U001"}

    def test_slash_recall_routed(self, monkeypatch):
        import handler, radar_query
        monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)

        called = {}
        def fake_recall(text, user_id):
            called["text"] = text
            return {"statusCode": 200, "body": "{}"}
        monkeypatch.setattr(radar_query, "recall", fake_recall)

        body = "command=%2Frecall&text=agent+memory&user_id=U001"
        headers = _sign(body, int(time.time()))
        resp = handler.lambda_handler(self._event(body, headers), None)
        assert resp["statusCode"] == 200
        assert called["text"] == "agent memory"

    def test_button_action_routed(self, monkeypatch):
        import handler, button_dispatch
        monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)

        called = {}
        def fake_handle(payload):
            called["action_id"] = payload["actions"][0]["action_id"]
            return {"statusCode": 200, "body": ""}
        monkeypatch.setattr(button_dispatch, "handle", fake_handle)

        action_payload = {
            "type": "block_actions",
            "actions": [{
                "action_id": "verdict_lab",
                "value": json.dumps({"tool_name": "mem0"}),
            }],
            "user": {"id": "U001", "username": "alice"},
            "response_url": "https://hooks.slack.com/actions/...",
        }
        body = "payload=" + json.dumps(action_payload).replace("+", "%2B")
        # Use a less-mangled body for signing
        from urllib.parse import quote
        body = "payload=" + quote(json.dumps(action_payload))
        headers = _sign(body, int(time.time()))
        resp = handler.lambda_handler(self._event(body, headers), None)
        assert resp["statusCode"] == 200
        assert called["action_id"] == "verdict_lab"


# ── radar_query slash commands ───────────────────────────────────────────────

class TestRadarQuery:
    def test_radar_empty_input_shows_usage(self):
        import radar_query
        resp = radar_query.radar("", "U001")
        body = json.loads(resp["body"])
        assert "Usage" in body["text"]

    def test_recall_empty_input_shows_usage(self):
        import radar_query
        resp = radar_query.recall("", "U001")
        body = json.loads(resp["body"])
        assert "Usage" in body["text"]

    def test_radar_no_mirror_returns_fallback_warning(self, monkeypatch):
        import radar_query
        # Force S3 mirror check to return False
        monkeypatch.setattr(radar_query, "_ensure_mirror", lambda: False)
        # Make the radar.md fallback empty too
        monkeypatch.setattr(radar_query, "_grep_radar_fallback", lambda t: "")
        resp = radar_query.radar("mem0", "U001")
        body = json.loads(resp["body"])
        assert ":warning:" in body["text"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
