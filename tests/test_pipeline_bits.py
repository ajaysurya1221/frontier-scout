"""
Unit tests for pipeline plumbing: stratified_cap redistribution,
Pulse state-machine migration, Slack dead-letter behavior.

No API calls — runs on every PR.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Stratified cap redistribution ────────────────────────────────────────────

class TestStratifiedCap:
    def _items(self, source: str, n: int, base_date: str = "2026-05-20") -> list[dict]:
        return [
            {"source": source, "title": f"{source} #{i}", "date": base_date, "summary": ""}
            for i in range(n)
        ]

    def test_quotas_respected_when_groups_oversubscribed(self):
        from scout import stratified_cap, SOURCE_QUOTAS

        # Every group has way more items than its quota
        items = []
        items += self._items("Hugging Face Blog", 200)
        items += self._items("Release: LangGraph", 200)
        items += self._items("Trending: GitHub/python", 200)
        items += self._items("Trending: HF Models", 200)
        items += self._items("HN (llm)", 200)
        items += self._items("ProductHunt AI", 200)
        items += self._items("PapersWithCode", 200)
        items += self._items("arXiv cs.AI", 200)

        out = stratified_cap(items)
        # Output should equal MAX_ITEMS (250) when total quota matches
        assert len(out) == sum(SOURCE_QUOTAS.values())

    def test_late_source_groups_survive(self):
        from scout import stratified_cap, _source_group

        # 500 RSS items first (would dominate v2's list slice), tiny arxiv last
        items = self._items("Hugging Face Blog", 500) + self._items("arXiv cs.AI", 8)
        out = stratified_cap(items)
        groups = {_source_group(i["source"]) for i in out}
        assert "arxiv" in groups, "arxiv must NOT be dropped by stratified cap"
        # The 8 arxiv items should all survive (well under quota)
        arxiv_items = [i for i in out if _source_group(i["source"]) == "arxiv"]
        assert len(arxiv_items) == 8

    def test_unused_quota_redistributes(self):
        from scout import stratified_cap, SOURCE_QUOTAS

        # ProductHunt + PapersWithCode + HF Trending have empty supply.
        # Their unused capacity (15+10+20=45 slots) should redistribute to
        # groups that have more items.
        items = []
        items += self._items("Hugging Face Blog", 500)  # only rss group has many
        items += self._items("Release: LangGraph", 50)
        items += self._items("arXiv cs.AI", 50)
        # Other groups: zero items

        out = stratified_cap(items)
        # Total cap is 250 (MAX_ITEMS). With redistribution, we should fill
        # close to it (not the original ~180 = rss_quota+github_release_quota+arxiv_quota).
        assert len(out) > 180, (
            f"redistribution failed; got {len(out)} items, expected closer to 250"
        )

    def test_deterministic_output(self):
        """Same input → same output, no randomness."""
        from scout import stratified_cap
        items = self._items("Hugging Face Blog", 200) + self._items("arXiv cs.AI", 200)
        out1 = stratified_cap(items)
        out2 = stratified_cap(items)
        assert [i["title"] for i in out1] == [i["title"] for i in out2]


# ── Pulse state migration ────────────────────────────────────────────────────

class TestPulseStateMigration:
    def test_legacy_log_migrates_to_posted(self, tmp_path, monkeypatch):
        """A legacy pulse-log.md with URLs should yield posted state on load."""
        import pulse

        legacy = tmp_path / "pulse-log.md"
        legacy.write_text(
            "# Pulse Log\n"
            "_All Tier-S URLs ever posted (dedupe state)._\n\n"
            "- `2026-05-19` https://github.com/anthropics/anthropic-sdk-python/releases/tag/v0.45.0\n"
            "- `2026-05-20` https://github.com/openai/openai-python/releases/tag/v1.55.0\n"
        )
        state_file = tmp_path / "pulse-state.json"

        monkeypatch.setattr(pulse, "PULSE_LOG", legacy)
        monkeypatch.setattr(pulse, "PULSE_STATE", state_file)

        state = pulse._load_state()
        assert "https://github.com/anthropics/anthropic-sdk-python/releases/tag/v0.45.0" in state
        assert state["https://github.com/openai/openai-python/releases/tag/v1.55.0"]["state"] == "posted"
        assert pulse.already_seen(state, "https://github.com/openai/openai-python/releases/tag/v1.55.0")

    def test_state_machine_failed_delivery_not_terminal(self, tmp_path, monkeypatch):
        import pulse
        monkeypatch.setattr(pulse, "PULSE_LOG", tmp_path / "pulse-log.md")
        monkeypatch.setattr(pulse, "PULSE_STATE", tmp_path / "pulse-state.json")

        state: dict = {}
        pulse.record_state(state, "https://example.com/a", "failed_delivery")
        assert not pulse.already_seen(state, "https://example.com/a"), (
            "failed_delivery must allow retry on next run"
        )
        # Promotion to posted → terminal
        pulse.record_state(state, "https://example.com/a", "posted")
        assert pulse.already_seen(state, "https://example.com/a")

    def test_state_machine_vetoed_terminal(self):
        import pulse
        state: dict = {}
        pulse.record_state(state, "https://example.com/b", "vetoed")
        assert pulse.already_seen(state, "https://example.com/b")

    def test_state_save_load_round_trip(self, tmp_path, monkeypatch):
        import pulse
        monkeypatch.setattr(pulse, "PULSE_STATE", tmp_path / "pulse-state.json")
        state = {"https://x.com/a": {"state": "posted", "first_seen": "t", "last_attempt": "t"}}
        pulse._save_state(state)
        loaded = pulse._load_state()
        assert loaded == state


# ── Slack dead-letter ────────────────────────────────────────────────────────

class TestSlackDeadLetter:
    def test_dead_letter_written_on_repeated_failure(self, tmp_path, monkeypatch):
        import slack_post

        # Force DEAD_LETTER to a temp path
        dead_letter = tmp_path / "slack-dead-letter.jsonl"
        monkeypatch.setattr(slack_post, "DEAD_LETTER", dead_letter)

        # Force at least one auth path so we don't hit the "no credentials" raise
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.invalid/slack/webhook")
        monkeypatch.delenv("DRY_RUN", raising=False)

        # Mock _do_post to always raise
        def raise_(*a, **kw):
            import requests
            r = requests.Response()
            r.status_code = 500
            raise requests.HTTPError("simulated 5xx", response=r)

        monkeypatch.setattr(slack_post, "_do_post", raise_)
        # Speed up the test: no real sleep
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}]
        with pytest.raises(Exception):
            slack_post.post(blocks, max_retries=2)

        assert dead_letter.exists(), "dead-letter file should be created"
        record = json.loads(dead_letter.read_text().strip().splitlines()[-1])
        # Round 4: the shared retry helper passes the full payload dict
        # ({"blocks": ..., "thread_ts": ...}) under the top-level "blocks" key
        # of the dead-letter record. The blocks themselves live one level deeper.
        assert "blocks" in record
        assert record["blocks"]["blocks"] == blocks
        assert record["blocks"].get("thread_ts") in (None, "")
        assert "simulated 5xx" in record.get("error", "")

    def test_dry_run_skips_dead_letter(self, tmp_path, monkeypatch):
        import slack_post
        dead_letter = tmp_path / "slack-dead-letter.jsonl"
        monkeypatch.setattr(slack_post, "DEAD_LETTER", dead_letter)
        monkeypatch.setenv("DRY_RUN", "1")
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}]
        result = slack_post.post(blocks)
        assert result is None
        assert not dead_letter.exists()


# ── Slack threaded format (Round 4) ──────────────────────────────────────────

class TestSlackThreaded:
    def _verdicts(self) -> list[dict]:
        # 1 ADOPT + 2 TRIAL + 1 ASSESS = 4 cards
        return [
            {
                "tool_name": "LangGraph", "verdict": "adopt", "category": "orchestration",
                "soc2": "safe", "what": "Multi-agent orchestration.",
                "why_it_matters": "Backbone of reference agent platform.",
                "adoption_cost": "Already done.", "next_action": "Track 0.6.x releases.",
                "source_url": "https://github.com/langchain-ai/langgraph",
                "severity": "high", "readiness": 5,
            },
            {
                "tool_name": "mem0", "verdict": "trial", "category": "data",
                "soc2": "conditional", "what": "Persistent semantic memory.",
                "why_it_matters": "Cleaner than Redis session store.",
                "adoption_cost": "~4 hrs.", "next_action": "Lab swap on one flow.",
                "source_url": "https://github.com/mem0ai/mem0",
                "severity": "high", "readiness": 4,
            },
            {
                "tool_name": "Forge", "verdict": "trial", "category": "orchestration",
                "soc2": "conditional", "what": "Guardrail framework.",
                "why_it_matters": "Lifts agentic task success.",
                "adoption_cost": "~4-6 hrs.", "next_action": "Lab on one LangGraph node.",
                "source_url": "https://github.com/antoinezambelli/forge",
                "severity": "standard", "readiness": 2,
            },
            {
                "tool_name": "Qwen3.6-35B", "verdict": "assess", "category": "frontier_model",
                "soc2": "conditional", "what": "Open-weight MoE model.",
                "why_it_matters": "Self-hostable on AWS.",
                "adoption_cost": "1-2 days to stand up.", "next_action": "Monitor 3 months.",
                "source_url": "https://huggingface.co/Qwen/Qwen3.6-35B-A3B",
                "severity": "standard", "readiness": 4,
            },
        ]

    def test_dry_run_prints_parent_and_thread_cards(self, capsys, monkeypatch):
        import slack_post
        monkeypatch.setenv("DRY_RUN", "1")
        slack_post.weekly_briefing_threaded(
            date="2026-05-20",
            scanned=377,
            cost=0.31,
            verdicts=self._verdicts(),
            judge_rating="high",
            judge_summary="Tight upstream pass.",
            dedup_drops=22,
            prior_drops=5,
            duration_s=232.0,
        )
        out = capsys.readouterr().out
        assert "threaded · parent" in out
        # One card block per verdict (4 verdicts → 4 card blocks)
        assert out.count("threaded · #") == 4
        # Tier anchors: ADOPT, TRIAL, ASSESS (HOLD has 0 verdicts in fixture)
        assert out.count("thread anchor ·") == 3
        assert "Tight upstream pass" in out
        assert "would add reactions" in out

    def test_real_send_posts_parent_then_threads_then_reacts(self, monkeypatch):
        import slack_post

        # Configure the bot path
        monkeypatch.delenv("DRY_RUN", raising=False)
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake-token-for-test")
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKECHAN")

        # Mock the slack_sdk WebClient
        post_calls: list[dict] = []
        react_calls: list[dict] = []

        class FakeClient:
            def __init__(self, token):
                self.token = token

            def chat_postMessage(self, **kwargs):
                post_calls.append(kwargs)
                return {"ts": f"172000000.{len(post_calls):06d}"}

            def reactions_add(self, **kwargs):
                react_calls.append(kwargs)
                return {"ok": True}

        # slack_sdk is imported lazily inside _bot_client; patch the module loader
        import sys
        fake_mod = type(sys)("slack_sdk")
        fake_mod.WebClient = FakeClient  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "slack_sdk", fake_mod)

        result = slack_post.weekly_briefing_threaded(
            date="2026-05-20",
            scanned=377,
            cost=0.31,
            verdicts=self._verdicts(),
            judge_rating="high",
            judge_summary="Tight upstream pass.",
            dedup_drops=22,
            prior_drops=5,
            duration_s=232.0,
        )

        # 1 parent + 3 tier anchors (ADOPT, TRIAL, ASSESS — HOLD has 0) +
        # 4 verdict cards = 8 chat.postMessage calls
        assert len(post_calls) == 8

        # First call: parent, no thread_ts, has bot identity override
        assert post_calls[0].get("thread_ts") in (None, "")
        assert post_calls[0].get("username") == "AI Telemetry"
        assert post_calls[0].get("icon_emoji") == ":satellite_antenna:"

        # All subsequent calls thread under the parent ts
        for reply in post_calls[1:]:
            assert reply.get("thread_ts") == "172000000.000001"

        # Tier anchors are blocks-only (no attachments) and contain the tier label;
        # verdict cards have an attachment with a tier color.
        anchor_calls = [c for c in post_calls[1:] if (c.get("blocks") and not c.get("attachments"))]
        verdict_calls = [c for c in post_calls[1:] if c.get("attachments")]
        assert len(anchor_calls) == 3, "expected 3 tier anchors (ADOPT/TRIAL/ASSESS)"
        assert len(verdict_calls) == 4, "expected 4 verdict cards"

        anchor_texts = []
        for ac in anchor_calls:
            for b in ac["blocks"]:
                if b.get("type") == "section":
                    anchor_texts.append(b["text"]["text"])
        assert any("🟢 ADOPT" in t for t in anchor_texts)
        assert any("🟡 TRIAL" in t for t in anchor_texts)
        assert any("⚪ ASSESS" in t for t in anchor_texts)

        colors = [v["attachments"][0].get("color") for v in verdict_calls]
        assert "#36a64f" in colors, "ADOPT card should have green color bar"
        assert "#f2c744" in colors, "TRIAL card should have amber color bar"
        assert "#9aa0a6" in colors, "ASSESS card should have gray color bar"

        # 3 reactions per verdict × 4 verdicts = 12 reactions_add calls.
        # Tier anchors do NOT get reactions.
        assert len(react_calls) == 12
        reaction_names = {r["name"] for r in react_calls}
        assert reaction_names == {"test_tube", "+1", "-1"}

        # Returned parent_ts is the first chat.postMessage call's ts
        assert result == "172000000.000001"


# ── Slack threaded partial-delivery (Round 5) ────────────────────────────────

class TestSlackThreadedPartialFailure:
    def test_thread_reply_failure_recorded_in_last_delivery(self, tmp_path, monkeypatch):
        """Parent succeeds, then one thread reply fails permanently. The
        run should not be counted as a full success — LAST_DELIVERY captures
        the per-leg outcome so quality-log.jsonl shows partial delivery."""
        import slack_post

        monkeypatch.delenv("DRY_RUN", raising=False)
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKE")
        # Isolate the dead-letter file so we don't pollute .scratch/ in the repo
        monkeypatch.setattr(slack_post, "DEAD_LETTER", tmp_path / "dl.jsonl")
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        # Track per-call kwargs and fail FOREVER (all 3 retries) on the first
        # verdict card so the partial-delivery flag is permanently raised.
        call_counter = {"n": 0, "verdict_cards_failed": 0}
        post_calls = []
        react_calls = []

        class FakeClient:
            def __init__(self, token):
                self.token = token

            def chat_postMessage(self, **kwargs):
                call_counter["n"] += 1
                post_calls.append(kwargs)
                # Verdict cards carry `attachments`; anchors carry `blocks` only.
                is_verdict_card = bool(kwargs.get("attachments"))
                # Fail every attempt of the FIRST verdict card (all retries)
                if is_verdict_card:
                    call_counter["verdict_cards_failed"] += 1
                    if call_counter["verdict_cards_failed"] <= 4:
                        raise RuntimeError("simulated permanent thread failure")
                return {"ts": f"172.{call_counter['n']:06d}"}

            def reactions_add(self, **kwargs):
                react_calls.append(kwargs)
                return {"ok": True}

        import sys
        fake_mod = type(sys)("slack_sdk")
        fake_mod.WebClient = FakeClient  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "slack_sdk", fake_mod)
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        # One ADOPT + one TRIAL verdict so we get two anchor messages
        verdicts = [
            {
                "tool_name": "X", "verdict": "adopt", "category": "orchestration",
                "soc2": "safe", "what": "x", "why_it_matters": "y",
                "adoption_cost": "z", "next_action": "w",
                "source_url": "https://github.com/foo/x",
                "severity": "high", "readiness": 5,
            },
            {
                "tool_name": "Y", "verdict": "trial", "category": "data",
                "soc2": "conditional", "what": "y", "why_it_matters": "z",
                "adoption_cost": "x", "next_action": "w",
                "source_url": "https://github.com/foo/y",
                "severity": "standard", "readiness": 3,
            },
        ]
        slack_post.weekly_briefing_threaded(
            date="2026-05-21", scanned=10, cost=0.1, verdicts=verdicts,
            judge_rating="medium", judge_summary="", dedup_drops=0, prior_drops=0,
        )

        d = slack_post.LAST_DELIVERY
        assert d["parent"] is True, "parent succeeded"
        assert d["verdicts_attempted"] == 2
        assert d["verdicts_failed"] >= 1, "at least one verdict reply failed"


# ── Lambda S3 mirror path-traversal + size cap (Round 5) ──────────────────────

class TestLambdaMirrorGuards:
    def test_path_traversal_key_rejected(self, monkeypatch, tmp_path):
        """A malicious key like '../../etc/passwd' must be rejected before download."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
        import radar_query

        monkeypatch.setattr(radar_query, "LOCAL_MIRROR", tmp_path / "mirror")
        monkeypatch.setattr(radar_query, "CHROMA_LOCAL", tmp_path / "mirror" / "memory" / "chroma")
        monkeypatch.setattr(radar_query, "RADAR_LOCAL", tmp_path / "mirror" / "tech-radar.md")
        monkeypatch.setenv("S3_MIRROR_BUCKET", "fake-bucket")
        monkeypatch.delenv("S3_MIRROR_PREFIX", raising=False)

        # Fake boto3 with one good key and one path-traversal key
        download_attempts = []

        class FakeS3:
            def get_paginator(self, _):
                class P:
                    def paginate(self, **kw):
                        return [{
                            "Contents": [
                                {"Key": "tech-radar.md", "Size": 100},
                                {"Key": "../../etc/passwd", "Size": 100},
                            ],
                        }]
                return P()

            def download_file(self, bucket, key, dest):
                # Should be called ONLY for the safe key
                download_attempts.append((key, dest))
                Path(dest).write_text("safe content")

        class FakeBoto3Module:
            @staticmethod
            def client(name, region_name=None):
                return FakeS3()

        import sys as _sys
        _sys.modules["boto3"] = FakeBoto3Module  # type: ignore

        ok = radar_query._ensure_mirror()
        assert ok is True
        downloaded_keys = [k for k, _ in download_attempts]
        assert "tech-radar.md" in downloaded_keys
        assert "../../etc/passwd" not in downloaded_keys, "path-traversal key should be rejected"

    def test_byte_cap_aborts_sync(self, monkeypatch, tmp_path):
        """Cumulative byte count > MAX_MIRROR_BYTES aborts the sync."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
        import radar_query

        monkeypatch.setattr(radar_query, "LOCAL_MIRROR", tmp_path / "mirror")
        monkeypatch.setattr(radar_query, "CHROMA_LOCAL", tmp_path / "mirror" / "memory" / "chroma")
        monkeypatch.setattr(radar_query, "RADAR_LOCAL", tmp_path / "mirror" / "tech-radar.md")
        monkeypatch.setattr(radar_query, "MAX_MIRROR_BYTES", 1000)  # tiny cap
        monkeypatch.setenv("S3_MIRROR_BUCKET", "fake-bucket")
        monkeypatch.delenv("S3_MIRROR_PREFIX", raising=False)

        class FakeS3:
            def get_paginator(self, _):
                class P:
                    def paginate(self, **kw):
                        return [{
                            "Contents": [
                                {"Key": "small.md", "Size": 500},
                                {"Key": "huge.bin", "Size": 10_000_000},  # over the cap
                            ],
                        }]
                return P()

            def download_file(self, bucket, key, dest):
                Path(dest).write_text("x" * 100)

        class FakeBoto3Module:
            @staticmethod
            def client(name, region_name=None):
                return FakeS3()

        import sys as _sys
        _sys.modules["boto3"] = FakeBoto3Module  # type: ignore

        ok = radar_query._ensure_mirror()
        assert ok is False, "sync should abort when byte cap exceeded"


# ── Judge fallback (Round 5) ──────────────────────────────────────────────────

class TestJudgeFallback:
    def test_first_attempt_no_tool_use_falls_back_to_forced(self, monkeypatch):
        """If adaptive thinking emits no tool_use, second attempt with forced
        tool_choice should run and its tool_use result should be used."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import judge as judge_mod

        attempts = []

        class FakeBlock:
            def __init__(self, type_, input_=None):
                self.type = type_
                self.input = input_ or {}

        class FakeResp:
            def __init__(self, content, usage):
                self.content = content
                self.usage = usage

        class FakeUsage:
            input_tokens = 100
            output_tokens = 50
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0

        def fake_call_with_retry(client, component, **kwargs):
            attempts.append((component, kwargs.get("tool_choice"), "thinking" in kwargs))
            if component == "scout-judge":
                # First attempt: thinking pass with no tool_use (only text)
                return FakeResp([FakeBlock("text")], FakeUsage())
            if component == "scout-judge-forced":
                # Second attempt: forced tool_choice returns tool_use
                payload = {
                    "decisions": [
                        {"index": 0, "action": "keep", "reason": "ok",
                         "severity": "high", "readiness": 4},
                    ],
                    "missed": [],
                    "quality_self_rating": "medium",
                    "judge_summary": "fallback worked",
                }
                return FakeResp([FakeBlock("tool_use", payload)], FakeUsage())
            raise RuntimeError(f"unexpected component {component!r}")

        monkeypatch.setattr(judge_mod, "call_with_retry", fake_call_with_retry)
        monkeypatch.setattr(judge_mod, "log_call", lambda *a, **kw: 0.01)
        monkeypatch.setattr(judge_mod, "CLIENT", object())

        verdicts = [{"tool_name": "X", "verdict": "trial", "category": "tool",
                     "soc2": "safe", "what": "x", "why_it_matters": "y",
                     "adoption_cost": "z", "next_action": "w",
                     "source_url": "https://github.com/foo/x"}]
        scored = [{"title": "X", "score": 7, "category": "tool", "source": "test",
                   "summary": "s", "url": "https://github.com/foo/x"}]

        result, cost = judge_mod.critique(verdicts, scored)

        assert len(attempts) == 2, f"expected 2 attempts, got {len(attempts)}"
        assert attempts[0][0] == "scout-judge"
        assert attempts[0][2] is True, "first attempt uses thinking"
        assert attempts[1][0] == "scout-judge-forced"
        assert attempts[1][1] == {"type": "tool", "name": "critique_verdicts"}, "second attempt forces the tool"
        assert attempts[1][2] is False, "second attempt has no thinking"
        assert result["judge_summary"] == "fallback worked"
        assert result.get("_judge_used_fallback") is True, "result marked as fallback"

    def test_both_attempts_fail_returns_fail_closed(self, monkeypatch):
        """If both attempts emit no tool_use, fail-closed result is returned."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import judge as judge_mod

        class FakeBlock:
            type = "text"

        class FakeResp:
            content = [FakeBlock()]
            class usage:
                input_tokens = 10
                output_tokens = 10
                cache_read_input_tokens = 0
                cache_creation_input_tokens = 0

        def always_text(client, component, **kwargs):
            return FakeResp()

        monkeypatch.setattr(judge_mod, "call_with_retry", always_text)
        monkeypatch.setattr(judge_mod, "log_call", lambda *a, **kw: 0.01)
        monkeypatch.setattr(judge_mod, "CLIENT", object())

        result, _ = judge_mod.critique(
            [{"tool_name": "X", "verdict": "trial", "category": "tool",
              "soc2": "safe", "what": "x", "why_it_matters": "y",
              "adoption_cost": "z", "next_action": "w",
              "source_url": "https://github.com/foo/x"}],
            [{"title": "X", "score": 7, "source": "t", "summary": "s", "url": "u"}],
        )
        assert result.get("_judge_failed") is True
        assert result["quality_self_rating"] == "low"
        # Fail-closed = every draft vetoed
        assert all(d.get("action") == "veto" for d in result["decisions"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
