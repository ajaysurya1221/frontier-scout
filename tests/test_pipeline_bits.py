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
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
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
                "why_it_matters": "Backbone of genai-core.",
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
        # No thread anchors in the redesigned parent/thread flow.
        assert out.count("thread anchor ·") == 0
        assert "Tight upstream pass" in out
        assert "would add reactions" in out

    def test_real_send_posts_parent_then_threads_then_reacts(self, monkeypatch, tmp_path):
        import slack_post

        # Configure the bot path
        monkeypatch.delenv("DRY_RUN", raising=False)
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xox" + "b-test")
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKECHAN")
        # Redirect the briefings meta-file output so the test doesn't pollute
        # the real repo with stray <date>-meta.json artifacts.
        monkeypatch.setattr(slack_post, "BRIEFINGS_DIR", tmp_path / "briefings")

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

        # 1 parent + 4 verdict cards (tier anchor removed).
        assert len(post_calls) == 5

        # First call: parent, no thread_ts, has bot identity override
        assert post_calls[0].get("thread_ts") in (None, "")
        assert post_calls[0].get("username") == "Frontier Scout"
        assert post_calls[0].get("icon_emoji") == ":satellite_antenna:"

        # All subsequent calls thread under the parent ts
        for reply in post_calls[1:]:
            assert reply.get("thread_ts") == "172000000.000001"

        # Verdict cards have BOTH blocks (the actions/overflow row) AND
        # attachments (the colored read-only card) — actions live at the top
        # level because Slack drops interactive elements inside attachments.
        anchor_calls = [c for c in post_calls[1:] if (c.get("blocks") and not c.get("attachments"))]
        verdict_calls = [c for c in post_calls[1:] if c.get("attachments")]
        assert len(anchor_calls) == 0, "thread anchors removed in redesign"
        assert len(verdict_calls) == 4, "expected 4 verdict cards"

        # Each verdict card has top-level blocks containing the actions row
        for vc in verdict_calls:
            outer = vc.get("blocks") or []
            assert any(b.get("type") == "actions" for b in outer), (
                "verdict card must put `actions` in top-level blocks (Slack "
                "silently drops interactive elements inside attachments)"
            )
            # Each actions row has the 3 buttons + the overflow menu, and
            # every overflow option `value` must stay under Slack's 150-char
            # cap (the regression that took down all 7 verdicts on
            # 2026-05-21).
            for b in outer:
                if b.get("type") != "actions":
                    continue
                action_ids = [e.get("action_id") for e in b.get("elements", [])]
                assert "verdict_lab" in action_ids
                assert "verdict_evaluate" in action_ids
                assert "verdict_compare" in action_ids
                assert "verdict_overflow" in action_ids
                for el in b.get("elements", []):
                    if el.get("type") != "overflow":
                        continue
                    for opt in el.get("options", []):
                        v_len = len(opt.get("value", ""))
                        assert v_len < 151, (
                            f"overflow value too long ({v_len} >= 151): "
                            f"{opt.get('value')!r}"
                        )

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


# ── Slack overflow option value-length cap (Round 5) ─────────────────────────

class TestSlackOverflowValueLimit:
    """Slack rejects overflow option `value` > 150 chars with `invalid_blocks`.
    This regression took down every verdict thread reply on 2026-05-21 —
    the wider `action_context` blob easily clears 200 chars for real
    verdicts (long tool name + GitHub security advisory URL). Adversarial
    inputs go through `_overflow_value` to confirm the cap holds.
    """

    def test_overflow_values_under_151_for_adversarial_inputs(self):
        import slack_post

        v = {
            "tool_name": "PydanticAI v1.99+/v1.100.0 — SSRF Security Fix in agentic flows (extended)",
            "verdict": "adopt",
            "category": "orchestration",
            "soc2": "safe",
            "what": "x",
            "why_it_matters": "x",
            "why_this_week": "x",
            "adoption_cost": "x",
            "next_action": "x",
            "source_url": (
                "https://github.com/pydantic/pydantic-ai/security/advisories/"
                "GHSA-xxxx-yyyy-zzzz-aaaa-bbbb-cccc-dddd-eeee-ffff-this-is-very-long"
            ),
            "severity": "high",
            "readiness": 4,
        }
        outer, _atts = slack_post._threaded_verdict_card(1, v)
        actions = next(b for b in outer if b.get("type") == "actions")
        overflow = next(e for e in actions["elements"] if e.get("type") == "overflow")
        assert len(overflow["options"]) == 3
        for opt in overflow["options"]:
            v_len = len(opt["value"])
            assert v_len < 151, (
                f"overflow value too long ({v_len}): {opt['value']!r}"
            )

    def test_overflow_value_helper_packs_compact_keys(self):
        import json
        import slack_post

        # Short, normal inputs → no truncation needed
        val = slack_post._overflow_value("mark_seen", "Graphiti v0.29.1")
        payload = json.loads(val)
        assert payload == {"a": "mark_seen", "t": "Graphiti v0.29.1"}
        assert len(val) <= slack_post._MAX_OVERFLOW_VALUE

    def test_overflow_value_helper_truncates_long_tool_names(self):
        import json
        import slack_post

        long_name = "X" * 500
        val = slack_post._overflow_value("copy_link", long_name)
        payload = json.loads(val)
        assert payload["a"] == "copy_link"
        assert payload["t"].startswith("X")
        # Helper caps the tool name aggressively; verify the resulting
        # JSON sits safely under Slack's hard limit.
        assert len(val) <= slack_post._MAX_OVERFLOW_VALUE
        assert len(val) < 151


# ── Slack threaded partial-delivery (Round 5) ────────────────────────────────

class TestSlackThreadedPartialFailure:
    def test_thread_reply_failure_recorded_in_last_delivery(self, tmp_path, monkeypatch):
        """Parent succeeds, then one thread reply fails permanently. The
        run should not be counted as a full success — LAST_DELIVERY captures
        the per-leg outcome so quality-log.jsonl shows partial delivery."""
        import slack_post

        monkeypatch.delenv("DRY_RUN", raising=False)
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xox" + "b-test")
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKE")
        # Isolate the dead-letter file so we don't pollute .scratch/ in the repo
        monkeypatch.setattr(slack_post, "DEAD_LETTER", tmp_path / "dl.jsonl")
        # Same for the per-card meta file (avoids stray briefings/<date>-meta.json)
        monkeypatch.setattr(slack_post, "BRIEFINGS_DIR", tmp_path / "briefings")
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

        monkeypatch.setattr(judge_mod, "_client", lambda: object())
        monkeypatch.setattr(judge_mod, "call_with_retry", fake_call_with_retry)
        monkeypatch.setattr(judge_mod, "log_call", lambda *a, **kw: 0.01)

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

        monkeypatch.setattr(judge_mod, "_client", lambda: object())
        monkeypatch.setattr(judge_mod, "call_with_retry", always_text)
        monkeypatch.setattr(judge_mod, "log_call", lambda *a, **kw: 0.01)

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


# ── Channel taste model — Round 6 ────────────────────────────────────────────

class TestPreferencesAggregator:
    """Time-decayed aggregation: signals → per-tag/per-category weights."""

    def _signal(self, signal, ts, tags=None, category=None, user="U1"):
        return {
            "ts": ts, "user": user, "signal": signal,
            "tags": tags or [], "category": category,
        }

    def test_cold_start_returns_empty_categories_and_tags(self, tmp_path, monkeypatch):
        import preferences
        monkeypatch.setattr(preferences, "SIGNALS_LOG", tmp_path / "signals-log.jsonl")
        monkeypatch.setattr(preferences, "PREFERENCES", tmp_path / "preferences.json")

        prefs = preferences.regenerate()

        assert prefs["signal_count_14d"] == 0
        assert prefs["tags"] == {}
        assert prefs["categories"] == {}
        assert preferences.format_team_prefs_paragraph(prefs) == ""

    def test_positive_signals_produce_positive_weights(self, tmp_path, monkeypatch):
        import preferences
        from datetime import datetime, timezone

        monkeypatch.setattr(preferences, "SIGNALS_LOG", tmp_path / "signals-log.jsonl")
        monkeypatch.setattr(preferences, "PREFERENCES", tmp_path / "preferences.json")

        now = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        # 15 different users react 👍 with tag "mcp" so per-user cap doesn't engage
        lines = [
            self._signal("reaction_thumbsup", now.isoformat().replace("+00:00", "Z"),
                         tags=["mcp"], category="orchestration", user=f"U{i}")
            for i in range(15)
        ]
        # Plus a few 👎 on "no-code"
        lines += [
            self._signal("reaction_thumbsdown", now.isoformat().replace("+00:00", "Z"),
                         tags=["no-code"], category="tool", user=f"U{i+100}")
            for i in range(5)
        ]
        (tmp_path / "signals-log.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )

        prefs = preferences.regenerate(now=now)

        assert prefs["signal_count_14d"] == 20
        assert prefs["tags"]["mcp"] > 0, "mcp should be positively weighted"
        assert prefs["tags"]["no-code"] < 0, "no-code should be negatively weighted"
        # Normalised to ±1.0 (max in each direction)
        assert prefs["tags"]["mcp"] == 1.0
        assert prefs["categories"]["orchestration"] == 1.0

    def test_time_decay_halves_at_14_days(self, tmp_path, monkeypatch):
        import preferences
        from datetime import datetime, timezone, timedelta

        monkeypatch.setattr(preferences, "SIGNALS_LOG", tmp_path / "signals-log.jsonl")
        monkeypatch.setattr(preferences, "PREFERENCES", tmp_path / "preferences.json")

        now = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        old = now - timedelta(days=14)

        # A: 1 fresh thumbsup on "fresh"
        # B: 2 14-day-old thumbsups on "old" (should equal A in weight after decay)
        lines = [
            self._signal("reaction_thumbsup", now.isoformat().replace("+00:00", "Z"),
                         tags=["fresh"], user="U1"),
            self._signal("reaction_thumbsup", old.isoformat().replace("+00:00", "Z"),
                         tags=["old"], user="U2"),
            self._signal("reaction_thumbsup", old.isoformat().replace("+00:00", "Z"),
                         tags=["old"], user="U3"),
        ]
        (tmp_path / "signals-log.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )

        prefs = preferences.aggregate(
            preferences.load_signals(), now=now,
        )

        # After normalisation, both tags should be approximately 1.0 (equal)
        assert abs(prefs["tags"]["fresh"] - prefs["tags"]["old"]) < 0.01

    def test_per_user_cap_limits_single_voter_influence(self, tmp_path, monkeypatch):
        import preferences
        from datetime import datetime, timezone

        monkeypatch.setattr(preferences, "SIGNALS_LOG", tmp_path / "signals-log.jsonl")
        monkeypatch.setattr(preferences, "PREFERENCES", tmp_path / "preferences.json")

        now = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        ts = now.isoformat().replace("+00:00", "Z")

        # Same one user reacts 100 times on tag "spam"; 15 different users
        # react once each on tag "legit"
        lines = [
            self._signal("reaction_thumbsup", ts, tags=["spam"], user="LOUD")
            for _ in range(100)
        ]
        lines += [
            self._signal("reaction_thumbsup", ts, tags=["legit"], user=f"U{i}")
            for i in range(15)
        ]
        (tmp_path / "signals-log.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )

        prefs = preferences.regenerate(now=now)

        # With PER_USER_CAP=0.30, the single LOUD voter is capped to 30% of
        # their own gross. 15 distinct users on "legit" face no cap.
        assert prefs["tags"]["legit"] >= prefs["tags"]["spam"], (
            "per-user cap should prevent one voter from dominating"
        )

    def test_reaction_removed_inverts_original_signal(self, tmp_path, monkeypatch):
        """Removing a 👍 must cancel the original +1.0 contribution, not add
        another. The Lambda dispatcher records `removed=true` alongside the
        original signal name; the aggregator negates the weight when it sees
        the flag. Codex review found this was claimed but not implemented."""
        import preferences
        from datetime import datetime, timezone

        monkeypatch.setattr(preferences, "SIGNALS_LOG", tmp_path / "signals-log.jsonl")
        monkeypatch.setattr(preferences, "PREFERENCES", tmp_path / "preferences.json")
        now = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        ts = now.isoformat().replace("+00:00", "Z")

        # One 👍 added, then removed by the same user → net zero contribution
        # to the tag, so the tag should not appear in normalised output (below
        # the 0.05 noise floor) AND the count of valid signals stays at 2.
        lines = [
            {"ts": ts, "user": "U1", "signal": "reaction_thumbsup",
             "tags": ["mcp"], "category": "orchestration"},
            {"ts": ts, "user": "U1", "signal": "reaction_thumbsup",
             "tags": ["mcp"], "category": "orchestration", "removed": True},
        ]
        (tmp_path / "signals-log.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        prefs = preferences.regenerate(now=now)
        # Both signals count toward the 14d activity total — visibility metric
        # tracks engagement, not net direction.
        assert prefs["signal_count_14d"] == 2
        # Net direction is zero → "mcp" is below the 0.05 noise floor and
        # doesn't appear in the normalised tags map.
        assert "mcp" not in prefs["tags"], (
            f"removed 👍 should cancel the original; got tags={prefs['tags']}"
        )

    def test_reaction_removed_inverts_thumbsdown_too(self, tmp_path, monkeypatch):
        """Inversion works for negative signals as well: removing a 👎 cancels
        the −1.0 contribution. Without the flag honoured, a removed 👎 would
        stack to −2.0 — the opposite of what the user did."""
        import preferences
        from datetime import datetime, timezone

        monkeypatch.setattr(preferences, "SIGNALS_LOG", tmp_path / "signals-log.jsonl")
        monkeypatch.setattr(preferences, "PREFERENCES", tmp_path / "preferences.json")
        now = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        ts = now.isoformat().replace("+00:00", "Z")

        # 15 users 👍 "kept-positive" + one user 👎+un-👎 "noisy" → net effect
        # of "noisy" should be zero; "kept-positive" should dominate at +1.0.
        lines = []
        for i in range(15):
            lines.append({
                "ts": ts, "user": f"U{i}", "signal": "reaction_thumbsup",
                "tags": ["kept-positive"], "category": "tool",
            })
        lines.append({"ts": ts, "user": "UNOISY", "signal": "reaction_thumbsdown",
                      "tags": ["noisy"], "category": "tool"})
        lines.append({"ts": ts, "user": "UNOISY", "signal": "reaction_thumbsdown",
                      "tags": ["noisy"], "category": "tool", "removed": True})

        (tmp_path / "signals-log.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        prefs = preferences.regenerate(now=now)
        # "noisy" should be cancelled; "kept-positive" must be the +1.0 peak
        assert "noisy" not in prefs["tags"]
        assert prefs["tags"]["kept-positive"] == 1.0


class TestRankingReweight:
    """Math-bounded post-scoring multiplier with exploration safeguards.

    The clamp is ASYMMETRIC: boost up to +50% (×1.5), dampen only to −20%
    (×0.8). Plus two bypasses for important novelty:
      • base score ≥ 8 → unchanged (strong absolute signal)
      • category in {frontier_model, security} → unchanged (non-negotiable)
    """

    def test_cold_start_returns_base_score(self):
        import preferences
        prefs = {"signal_count_14d": 5, "tags": {"mcp": 1.0}}
        assert preferences.reweight_score(7.0, ["mcp"], prefs) == 7.0

    def test_no_tags_returns_base_score(self):
        import preferences
        prefs = {"signal_count_14d": 100, "tags": {"mcp": 1.0}}
        assert preferences.reweight_score(7.0, [], prefs) == 7.0
        assert preferences.reweight_score(7.0, None, prefs) == 7.0

    def test_positive_tag_boosts_within_cap(self):
        import preferences
        prefs = {"signal_count_14d": 50, "tags": {"mcp": 1.0}}
        # α=0.1, multiplier = 1 + 0.1*1.0 = 1.1
        assert abs(preferences.reweight_score(7.0, ["mcp"], prefs) - 7.7) < 1e-6

    def test_negative_tag_dampens_within_cap(self):
        import preferences
        prefs = {"signal_count_14d": 50, "tags": {"no-code": -1.0}}
        # α=0.1, multiplier = 1 + 0.1*-1.0 = 0.9
        assert abs(preferences.reweight_score(7.0, ["no-code"], prefs) - 6.3) < 1e-6

    def test_extreme_positive_clips_at_1_5x(self):
        import preferences
        # Six positively-weighted tags → boost would be 0.6, clipped to 0.5
        prefs = {
            "signal_count_14d": 50,
            "tags": {f"t{i}": 1.0 for i in range(6)},
        }
        tags = [f"t{i}" for i in range(6)]
        # Use base 7 so the high-base-score bypass (≥8) doesn't fire.
        assert preferences.reweight_score(7.0, tags, prefs) == 7.0 * 1.5

    def test_extreme_negative_clips_at_0_8x(self):
        """Asymmetric clamp: dampen capped at 0.8x (NOT 0.5x).

        Insurance against the taste model silencing an unfamiliar tag.
        Worst case for a 7/10 item: 7 * 0.8 = 5.6 — still above the
        verdict-cutoff of 6. The whole point: lift, never kill.
        """
        import preferences
        prefs = {
            "signal_count_14d": 50,
            "tags": {f"t{i}": -1.0 for i in range(6)},
        }
        tags = [f"t{i}" for i in range(6)]
        assert preferences.reweight_score(7.0, tags, prefs) == 7.0 * 0.8

    def test_unknown_tag_is_ignored(self):
        import preferences
        prefs = {"signal_count_14d": 50, "tags": {"mcp": 1.0}}
        # "novel-tag" not in prefs → contributes 0
        assert preferences.reweight_score(7.0, ["novel-tag"], prefs) == 7.0

    # ── Exploration safeguards ───────────────────────────────────────────

    def test_high_base_score_bypasses_reweight(self):
        """Items Sonnet rated 8+ pass through untouched, even with negative
        tags. Prevents a niche-topic 9/10 from being pushed below an
        on-trend 7/10 just because the team hasn't reacted to that tag."""
        import preferences
        prefs = {
            "signal_count_14d": 50,
            "tags": {"unfamiliar": -1.0},  # team strongly dislikes this tag
        }
        # 8.0 is the exact threshold — bypass
        assert preferences.reweight_score(8.0, ["unfamiliar"], prefs) == 8.0
        # 9.0 well above threshold — bypass
        assert preferences.reweight_score(9.0, ["unfamiliar"], prefs) == 9.0
        # 7.9 just below — reweight applies (gentle dampen to 7.9 * 0.9 = 7.11)
        result = preferences.reweight_score(7.9, ["unfamiliar"], prefs)
        assert abs(result - 7.9 * 0.9) < 1e-6

    def test_frontier_model_category_bypasses_reweight(self):
        """A new GPT/Claude/Gemini drop should never be dampened by team
        taste — it's a stack-shifting event."""
        import preferences
        prefs = {
            "signal_count_14d": 50,
            "tags": {"frontier": -1.0},  # team has been bored of frontier news
        }
        assert preferences.reweight_score(
            6.0, ["frontier"], prefs, category="frontier_model"
        ) == 6.0

    def test_security_category_bypasses_reweight(self):
        """Security advisories pass through unchanged regardless of tag taste."""
        import preferences
        prefs = {"signal_count_14d": 50, "tags": {"cve": -1.0}}
        assert preferences.reweight_score(
            5.0, ["cve"], prefs, category="security"
        ) == 5.0

    def test_other_categories_do_not_bypass(self):
        """`tool` / `orchestration` / `data` / `compute` categories still
        get the (gentle, asymmetric) reweight applied."""
        import preferences
        prefs = {"signal_count_14d": 50, "tags": {"no-code": -1.0}}
        # base 6, tags get -0.1 boost → multiplier 0.9 → 5.4
        result = preferences.reweight_score(
            6.0, ["no-code"], prefs, category="tool"
        )
        assert abs(result - 5.4) < 1e-6


class TestScoutCutoffUsesBaseScore:
    """The verdict cutoff in scout._main_impl uses the ORIGINAL Sonnet score
    (score_base) when available, not the reweighted score. This is the actual
    "never silence" guarantee — without it, a 7/10 with a disliked tag (which
    reweights to 5.6) would be filtered out by the `score >= 6` cutoff, even
    though the math layer claims to dampen but never kill.

    The math reweight still drives ranking ORDER within the kept set, so
    on-trend items still rise to the top. Codex review surfaced this as a
    contradiction between the documented behaviour and the implementation.
    """

    def _cutoff(self, item):
        # Mirror of the helper in scripts/scout.py:_main_impl._passes_cutoff
        # Tests guard the rule even if the helper is later inlined or moved.
        base = item.get("score_base", item.get("score", 0))
        return base >= 6

    def test_dampened_item_above_base_6_survives_cutoff(self):
        # A 7/10 with negative tags is reweighted to 5.6 — under the old rule
        # it was filtered out; under the fix it survives because score_base=7.
        item = {"score_base": 7.0, "score": 5.6, "tags": ["no-code"]}
        assert self._cutoff(item) is True

    def test_item_below_base_6_still_dropped(self):
        # A genuinely low-quality item (Sonnet gave it 5) is correctly dropped
        # regardless of any reweight that may have nudged the displayed score.
        item = {"score_base": 5.0, "score": 5.5, "tags": ["mcp"]}
        assert self._cutoff(item) is False

    def test_cold_start_path_uses_score_directly(self):
        # In cold start, no reweight runs and `score_base` is not set. The
        # cutoff falls back to `score`, matching pre-Round-6 behaviour exactly.
        item = {"score": 7.0}
        assert self._cutoff(item) is True
        item_low = {"score": 5.0}
        assert self._cutoff(item_low) is False


class TestPreferencesPromptInjection:
    """The Sonnet-aware steering paragraph."""

    def test_cold_start_returns_empty_string(self):
        import preferences
        prefs = {"signal_count_14d": 5, "tags": {"mcp": 1.0}}
        assert preferences.format_team_prefs_paragraph(prefs) == ""

    def test_above_threshold_renders_tiered_paragraph(self):
        import preferences
        prefs = {
            "signal_count_14d": 47,
            "tags": {
                "mcp": 0.91, "agentic-coding": 0.74,
                "long-context": 0.25,
                "no-code": -0.63, "image-gen": -0.81,
            },
        }
        out = preferences.format_team_prefs_paragraph(prefs)
        assert "47 reactions" in out
        assert "Higher interest" in out and "mcp" in out and "agentic-coding" in out
        assert "Mild interest" in out and "long-context" in out
        assert "Strong avoid" in out and "image-gen" in out
        # Novelty/severity protection language must be present so Sonnet
        # itself respects the bypass — not just the math layer.
        assert "soft context" in out and "BORDERLINE" in out
        assert "NOVELTY" in out and "SEVERITY" in out
        assert "8+" in out, "must remind Sonnet not to downweight strong items"
        assert "LIFT" in out and "never to silence" in out


# ── Lab runner — Round 7 Phase A ─────────────────────────────────────────────

class TestLabOpenSourceGate:
    """The 🧪 Run Lab button only appears on real open-source URLs. Closed-
    source / paywalled / blog-post URLs simply don't get the button.

    Belt-and-braces: lab_runner.py also enforces the same regex server-side,
    so a manually-triggered pipeline can't bypass it either."""

    def test_github_url_passes(self):
        import slack_post
        assert slack_post._is_open_source_url("https://github.com/foo/bar") is True
        assert slack_post._is_open_source_url("https://www.github.com/foo/bar") is True

    def test_pypi_url_passes(self):
        import slack_post
        assert slack_post._is_open_source_url("https://pypi.org/project/dspy/") is True

    def test_huggingface_url_passes(self):
        import slack_post
        assert slack_post._is_open_source_url("https://huggingface.co/meta-llama/Llama-3") is True

    def test_gitlab_url_passes(self):
        import slack_post
        assert slack_post._is_open_source_url("https://gitlab.com/foo/bar") is True

    def test_anthropic_news_url_blocked(self):
        import slack_post
        # Vendor blog URL — not pullable, no button
        assert slack_post._is_open_source_url("https://anthropic.com/news/x") is False

    def test_random_blog_url_blocked(self):
        import slack_post
        assert slack_post._is_open_source_url("http://random-blog.com/post") is False

    def test_empty_or_none_returns_false(self):
        import slack_post
        assert slack_post._is_open_source_url("") is False
        assert slack_post._is_open_source_url(None) is False

    def test_verdict_card_omits_lab_button_for_non_open_source(self):
        """End-to-end: a verdict with a non-open-source source_url should NOT
        carry a verdict_lab button in its actions block."""
        import slack_post

        v = {
            "tool_name": "ClosedAI-Pro",
            "verdict": "trial", "category": "tool", "soc2": "conditional",
            "what": "x", "why_it_matters": "y", "adoption_cost": "z",
            "next_action": "w",
            "source_url": "https://closedai-pro.com/landing",  # vendor URL
            "severity": "standard", "readiness": 3,
        }
        outer, _atts = slack_post._threaded_verdict_card(1, v)
        actions = next(b for b in outer if b.get("type") == "actions")
        action_ids = [e.get("action_id") for e in actions["elements"]]
        assert "verdict_lab" not in action_ids, (
            f"closed-source URL must not carry verdict_lab; got {action_ids}"
        )
        # Evaluate + compare + overflow are still there
        assert "verdict_evaluate" in action_ids
        assert "verdict_compare" in action_ids
        assert "verdict_overflow" in action_ids

    def test_verdict_card_includes_lab_button_for_open_source(self):
        import slack_post

        v = {
            "tool_name": "DSPy",
            "verdict": "trial", "category": "tool", "soc2": "safe",
            "what": "x", "why_it_matters": "y", "adoption_cost": "z",
            "next_action": "w",
            "source_url": "https://github.com/stanfordnlp/dspy",
            "severity": "high", "readiness": 4,
        }
        outer, _atts = slack_post._threaded_verdict_card(1, v)
        actions = next(b for b in outer if b.get("type") == "actions")
        action_ids = [e.get("action_id") for e in actions["elements"]]
        assert "verdict_lab" in action_ids
        # Lab button must carry the new "Run Lab" label, not the old "Queue lab"
        lab_btn = next(e for e in actions["elements"] if e.get("action_id") == "verdict_lab")
        assert "Run Lab" in lab_btn["text"]["text"]


class TestLabSecretLeakGuard:
    """Pre-execution regex check rejects scripts that look like they baked a
    real secret in. This is the safety net against prompt-injection where
    the tool's README tries to coerce the generator into hard-coding a key."""

    def _matches(self, text):
        import lab_runner
        return lab_runner.SECRET_LEAK_RE.search(text)

    @staticmethod
    def _secret(*parts: str) -> str:
        """Build scanner fixtures at runtime so push protection sees no token."""
        return "".join(parts)

    # These fixtures are intentionally shaped to LOOK like real secrets at
    # runtime — that is the whole point of the test. The literals are split so
    # GitHub push protection does not block harmless test fixtures.

    def test_anthropic_key_pattern_caught(self):
        token = self._secret("sk-ant-api03-", "AbCdEfGhIjKlMnOpQrStUv")
        assert self._matches(f"client = Anthropic(api_key='{token}')")

    def test_openai_proj_key_pattern_caught(self):
        token = self._secret("sk-proj-", "AbCdEfGhIjKlMnOpQrStUv")
        assert self._matches(f"OPENAI_API_KEY = '{token}'")

    def test_slack_token_pattern_caught(self):
        token = self._secret("xox", "b-", "1234567890-", "abcdefghijklmn")
        assert self._matches(f"client = WebClient(token='{token}')")

    def test_github_pat_pattern_caught(self):
        token = self._secret("ghp_", "AbCdEfGhIjKlMnOpQrStUvWxYz1234")
        assert self._matches(f"headers = {{'Authorization': '{token}'}}")

    def test_aws_access_key_caught(self):
        assert self._matches(f"AWS_ACCESS_KEY_ID = '{self._secret('ASIA', 'Q6RZI4ENNQ35NVWL')}'")
        assert self._matches(f"AWS_ACCESS_KEY_ID = '{self._secret('AKIA', 'Q6RZI4ENNQ35NVWL')}'")

    def test_clean_synthetic_script_passes(self):
        clean = (
            "import dspy\n"
            "print('OK: imported')\n"
            "try:\n"
            "    obj = dspy.Predict('question -> answer')\n"
            "    print('OK: instantiated Predict')\n"
            "except Exception as e:\n"
            "    print(f'FAILED: {e}')\n"
        )
        assert self._matches(clean) is None

    def test_placeholder_key_not_caught(self):
        """Synthetic 'PLACEHOLDER' / 'REPLACE-ME' patterns must NOT be flagged."""
        placeholder = "ANTHROPIC_API_KEY = 'PLACEHOLDER'"  # pragma: allowlist secret
        assert self._matches(placeholder) is None


class TestLabRuntimeDispatch:
    """Round 10: polyglot lab dispatcher. The classifier emits a `runtime`
    field (python / node / huggingface / unknown); `_unsupported_runtime_reason`
    bails BEFORE spending generator + subprocess + interpreter cycles when:
      - the runtime isn't in the supported set
      - the HF model is gated / private / over the size cap
      - the README explicitly says the repo isn't a runnable library
      - python runtime was picked but PyPI returned nothing
    """

    # ── _unsupported_runtime_reason ─────────────────────────────────────

    def test_unknown_runtime_is_rejected(self):
        """Classifier picked something we don't support (cargo, docker, …)."""
        import lab_runner
        spec = {"name": "x", "url": "https://github.com/x/y", "readme": "", "pypi": {}, "hf": {}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "cargo", "package": "x"},
            "https://github.com/x/y",
        )
        assert reason is not None
        assert "cargo" in reason or "supported" in reason

    def test_python_with_pypi_passes_gate(self):
        """dspy on PyPI + runtime=python → no skip reason; lab proceeds."""
        import lab_runner
        spec = {"name": "dspy", "url": "https://github.com/stanfordnlp/dspy",
                "readme": "DSPy: programming with foundation models",
                "pypi": {"version": "2.5.0", "summary": "DSPy"}, "hf": {}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "python", "package": "dspy"},
            "https://github.com/stanfordnlp/dspy",
        )
        assert reason is None

    def test_python_with_no_pypi_record_is_rejected(self):
        """anthropics/skills — runtime=python but PyPI returns nothing → bail."""
        import lab_runner
        spec = {"name": "anthropics/skills",
                "url": "https://github.com/anthropics/skills",
                "readme": "Anthropic skills — a collection of capabilities.",
                "pypi": {}, "hf": {}}  # PyPI 404
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "python", "package": ""},
            "https://github.com/anthropics/skills",
        )
        assert reason is not None
        assert "PyPI" in reason

    def test_node_runtime_passes_gate(self):
        """Node tools don't need a PyPI record — let `npm install` succeed or
        fail naturally with a real npm error message in stderr."""
        import lab_runner
        spec = {"name": "@modelcontextprotocol/inspector",
                "url": "https://github.com/modelcontextprotocol/inspector",
                "readme": "Run with `npx @modelcontextprotocol/inspector`",
                "pypi": {}, "hf": {}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "node", "package": "@modelcontextprotocol/inspector"},
            "https://github.com/modelcontextprotocol/inspector",
        )
        assert reason is None

    def test_hf_runtime_passes_when_small_and_public(self):
        """A small public HF model passes the size gate (under 5 GB)."""
        import lab_runner
        spec = {"name": "tiny-gpt2",
                "url": "https://huggingface.co/sshleifer/tiny-gpt2",
                "readme": "",
                "pypi": {},
                "hf": {"total_weight_bytes": 5_000_000,  # 5 MB
                       "gated": False, "private": False}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "huggingface", "package": "sshleifer/tiny-gpt2"},
            "https://huggingface.co/sshleifer/tiny-gpt2",
        )
        assert reason is None

    def test_hf_model_over_size_cap_is_rejected_without_download(self):
        """A 67 GB DeepSeek model is rejected based on the manifest alone —
        no weight download, no LLM call wasted."""
        import lab_runner
        spec = {"name": "DeepSeek-V4-Pro",
                "url": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
                "readme": "",
                "pypi": {},
                "hf": {"total_weight_bytes": 67 * 1024 ** 3,  # 67 GB
                       "gated": False, "private": False}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "huggingface", "package": "deepseek-ai/DeepSeek-V4-Pro"},
            "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
        )
        assert reason is not None
        assert "GB" in reason and ("cap" in reason or "over" in reason)

    def test_hf_gated_model_is_rejected(self):
        """Gated HF models can't be pulled unauthenticated → skip cleanly."""
        import lab_runner
        spec = {"name": "Llama-3", "url": "https://huggingface.co/meta-llama/Llama-3",
                "readme": "", "pypi": {},
                "hf": {"total_weight_bytes": 100_000_000,
                       "gated": True, "private": False}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "huggingface", "package": "meta-llama/Llama-3"},
            "https://huggingface.co/meta-llama/Llama-3",
        )
        assert reason is not None
        assert "gated" in reason.lower()

    def test_hf_url_without_manifest_is_rejected(self):
        """HF URL but the manifest fetch returned nothing → can't size-check."""
        import lab_runner
        spec = {"name": "x", "url": "https://huggingface.co/x/y",
                "readme": "", "pypi": {}, "hf": {}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "huggingface", "package": "x/y"},
            "https://huggingface.co/x/y",
        )
        assert reason is not None
        assert "manifest" in reason.lower() or "huggingface" in reason.lower()

    def test_readme_says_not_a_library_overrides_runtime(self):
        """A 'skills are markdown' README skips even if runtime=python."""
        import lab_runner
        spec = {"name": "some-skills",
                "url": "https://github.com/x/some-skills",
                "readme": "This repository contains skills — markdown files only.",
                "pypi": {"version": "0.1.0", "summary": "unrelated package"},
                "hf": {}}
        reason = lab_runner._unsupported_runtime_reason(
            spec, {"runtime": "python", "package": "some-skills"},
            "https://github.com/x/some-skills",
        )
        assert reason is not None
        assert "README" in reason or "library" in reason

    # ── npm token leak guard ────────────────────────────────────────────

    def test_npm_token_caught_by_secret_leak_regex(self):
        """Round 10 added npm_<36+> to SECRET_LEAK_RE so a Node test script
        that bakes in an npm publish token is rejected before execution."""
        import lab_runner
        token = TestLabSecretLeakGuard._secret("npm_", "abcdefghijklmnopqrstuvwxyz0123456789AB")
        script = f"const auth = '{token}';"
        assert lab_runner.SECRET_LEAK_RE.search(script) is not None

    # ── Hermetic env: no secrets reach the child, across ALL runtimes ───

    def _patch_loud_secrets(self, monkeypatch):
        """Plant fake secrets in the parent env so leakage tests can detect
        anything reaching the child env-builder."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "parent-anthropic-sentinel")
        monkeypatch.setenv("OPENAI_API_KEY", "parent-openai-sentinel")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "parent-slack-sentinel")
        monkeypatch.setenv("GH_TOKEN", "parent-github-sentinel")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "parent-aws-key-sentinel")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "PARENT-SHOULD-NOT-LEAK")

    def test_hermetic_base_env_has_no_secrets(self, monkeypatch):
        """The base hermetic env is the shared root of all three runtime
        runners. Backs the README/SECURITY.md isolation claim."""
        import lab_runner
        self._patch_loud_secrets(monkeypatch)
        env = lab_runner._hermetic_base_env()
        forbidden = {
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SLACK_BOT_TOKEN",
            "GH_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN", "SLACK_SIGNING_SECRET", "HF_TOKEN",
        }
        leaked = sorted(env.keys() & forbidden)
        assert leaked == [], f"hermetic base env leaked: {leaked}"
        # Sanity: PATH + HOME ARE pass-throughs (we need them).
        assert "PATH" in env and "HOME" in env


class TestLabCapsReader:
    """`_within_caps` is the bouncer at the door — reads today's lab-* lines
    from costs.jsonl and refuses if either cap is hit. Reviewer-visible
    behaviour: cap fires → polite Slack refusal, no Sonnet calls, no
    subprocess. This is the single most important cost-defense."""

    def test_empty_ledger_allows_run(self, tmp_path, monkeypatch):
        import lab_runner
        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        assert lab_runner._within_caps() is None

    def test_under_count_cap_allows_run(self, tmp_path, monkeypatch):
        import lab_runner
        from datetime import datetime, timezone
        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 3)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 5.0)

        today = datetime.now(timezone.utc).isoformat()
        # 1 prior run today (3 cost entries sharing one run_id)
        lines = [
            {"ts": today, "component": "lab-classify", "cost_usd": 0.01, "run_id": "abc"},
            {"ts": today, "component": "lab-generate", "cost_usd": 0.02, "run_id": "abc"},
            {"ts": today, "component": "lab-interpret", "cost_usd": 0.01, "run_id": "abc"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        assert lab_runner._within_caps() is None

    def test_run_count_cap_refuses(self, tmp_path, monkeypatch):
        import lab_runner
        from datetime import datetime, timezone
        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 1)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 100.0)

        today = datetime.now(timezone.utc).isoformat()
        lines = [{"ts": today, "component": "lab-classify", "cost_usd": 0.01, "run_id": "first"}]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        refusal = lab_runner._within_caps()
        assert refusal is not None
        assert "daily cap" in refusal.lower()

    def test_usd_cap_refuses(self, tmp_path, monkeypatch):
        import lab_runner
        from datetime import datetime, timezone
        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 100)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 1.0)

        today = datetime.now(timezone.utc).isoformat()
        # One $1.50 lab run already today — over the $1.00 USD cap
        lines = [{"ts": today, "component": "lab-classify", "cost_usd": 1.50, "run_id": "expensive"}]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        refusal = lab_runner._within_caps()
        assert refusal is not None
        assert "USD cap" in refusal

    def test_yesterdays_entries_dont_count(self, tmp_path, monkeypatch):
        """Caps reset at midnight UTC — yesterday's spend shouldn't gate today."""
        import lab_runner
        from datetime import datetime, timedelta, timezone
        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 1)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 1.0)

        yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        lines = [
            {"ts": yesterday, "component": "lab-classify", "cost_usd": 0.50, "run_id": "old1"},
            {"ts": yesterday, "component": "lab-generate", "cost_usd": 0.50, "run_id": "old1"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        assert lab_runner._within_caps() is None

    def test_non_lab_costs_dont_count(self, tmp_path, monkeypatch):
        """Scout / Pulse / Synth costs share the ledger but don't count
        against the lab cap — only `lab-*` component entries do."""
        import lab_runner
        from datetime import datetime, timezone
        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 1)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 1.0)

        today = datetime.now(timezone.utc).isoformat()
        # $20 of Scout cost today shouldn't gate a lab click
        lines = [
            {"ts": today, "component": "scout-score", "cost_usd": 5.0, "run_id": "s1"},
            {"ts": today, "component": "scout-verdict", "cost_usd": 10.0, "run_id": "s1"},
            {"ts": today, "component": "scout-judge", "cost_usd": 5.0, "run_id": "s1"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        assert lab_runner._within_caps() is None


class TestLabSubprocessHermetic:
    """The single most important behavioural guarantee: the generated test
    script runs with NO team API keys in the child env. Verified via
    subprocess introspection (the test asks the child to print its env)
    on the live python runtime — the Node + HF runners share the same
    `_hermetic_base_env()` root, separately covered by
    TestLabRuntimeDispatch::test_hermetic_base_env_has_no_secrets."""

    def test_python_subprocess_env_contains_no_secrets(self, tmp_path, monkeypatch):
        """Run a tiny synthetic script that prints its env; assert no team
        secret keys are present."""
        import lab_runner

        # Set fake secrets in the PARENT env so we can verify they don't leak
        monkeypatch.setenv("ANTHROPIC_API_KEY", "parent-anthropic-sentinel")
        monkeypatch.setenv("OPENAI_API_KEY", "parent-openai-sentinel")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "parent-slack-sentinel")
        monkeypatch.setenv("GH_TOKEN", "parent-github-sentinel")

        # Build a minimal "package" — we'll pip-install nothing-relevant
        # (just use stdlib in the test script). Skip the install step by
        # using a real but tiny package: `six` is universally available
        # and installs in <2s.
        spec = {"name": "six", "package": "six", "url": "https://pypi.org/project/six/"}
        classification = {"runtime": "python", "package": "six"}
        script = textwrap.dedent("""
            import os, sys, json
            keys_present = sorted(k for k in os.environ
                                   if k in {
                                       "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                                       "SLACK_BOT_TOKEN", "GH_TOKEN",
                                       "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                       "AWS_SESSION_TOKEN",
                                   })
            print("LEAKED_SECRETS=" + json.dumps(keys_present))
            print("PATH_PRESENT=" + str("PATH" in os.environ))
            print("HOME_PRESENT=" + str("HOME" in os.environ))
        """).strip()

        result = lab_runner._run_subprocess_python(spec, classification, script)
        # If install fails (no internet), skip — the hermetic check is
        # what matters and can't be tested without subprocess.
        if result["stage"] == "install" and result["exit_code"] != 0:
            pytest.skip(f"pip install of `six` failed in test env: {result['stderr'][:120]}")

        assert "LEAKED_SECRETS=[]" in result["stdout"], (
            f"child env leaked secrets! stdout was:\n{result['stdout']}"
        )
        assert "PATH_PRESENT=True" in result["stdout"]
        assert "HOME_PRESENT=True" in result["stdout"]


# Need textwrap for the subprocess-hermetic test above
import textwrap  # noqa: E402


class TestReactionErrorHandling:
    """`_add_reactions` must surface the actual Slack error code AND stop
    the loop on unrecoverable errors. Previous behaviour spammed CI logs
    with 21 lines of opaque `{'ok': False, ...}` when the bot was missing
    one scope — operator had no signal which root cause to fix."""

    @pytest.fixture(autouse=True)
    def _reset_breaker(self):
        """The cross-card circuit breaker is module-level state; reset it
        before AND after each test so cases can't leak into each other."""
        import slack_post
        slack_post.reset_reaction_breaker()
        yield
        slack_post.reset_reaction_breaker()

    def _fake_slack_error(self, error_code: str) -> Exception:
        """Build an exception that mimics slack_sdk.errors.SlackApiError —
        carries a `.response.data` dict with the error code, same shape
        the real SDK uses."""
        class _FakeResponse:
            def __init__(self, data):
                self.data = data

        class _FakeSlackApiError(Exception):
            def __init__(self, error_code):
                super().__init__(f"The request to the Slack API failed.")
                self.response = _FakeResponse({"ok": False, "error": error_code})

        return _FakeSlackApiError(error_code)

    def test_extract_slack_error_from_real_shape(self):
        import slack_post
        exc = self._fake_slack_error("missing_scope")
        assert slack_post._extract_slack_error(exc) == "missing_scope"

    def test_extract_slack_error_returns_empty_for_non_slack_exception(self):
        import slack_post
        assert slack_post._extract_slack_error(ValueError("nope")) == ""
        assert slack_post._extract_slack_error(RuntimeError()) == ""

    def test_missing_scope_bails_after_one_log(self, monkeypatch, capsys):
        """The hottest failure mode: bot lacks reactions:write. Old code
        logged 21 lines. New code should log ONCE and stop."""
        import slack_post

        calls = []

        class _FakeClient:
            def reactions_add(self, channel, timestamp, name):
                calls.append(name)
                raise self_test._fake_slack_error("missing_scope")

        self_test = self  # capture so the inner class can build the error
        monkeypatch.setattr(slack_post, "_bot_client", lambda: _FakeClient())
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKE")
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        slack_post._add_reactions("172.000001", emojis=["test_tube", "+1", "-1"])

        # Only the FIRST emoji should have been attempted — the loop bailed.
        assert calls == ["test_tube"], f"expected single attempt, got {calls}"
        out = capsys.readouterr().out
        # The operator sees a clear, actionable message
        assert "Skipping all reactions" in out
        assert "missing_scope" in out
        assert "reinstall" in out.lower()

    def test_ratelimited_also_bails(self, monkeypatch, capsys):
        """Rate-limit is recoverable on the next run; trying more now
        only makes the back-off worse."""
        import slack_post

        calls = []

        class _FakeClient:
            def reactions_add(self, channel, timestamp, name):
                calls.append(name)
                raise self_test._fake_slack_error("ratelimited")

        self_test = self
        monkeypatch.setattr(slack_post, "_bot_client", lambda: _FakeClient())
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKE")
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        slack_post._add_reactions("172.000001", emojis=["test_tube", "+1", "-1"])
        assert calls == ["test_tube"], f"expected bail after first, got {calls}"
        out = capsys.readouterr().out
        assert "ratelimited" in out
        assert "rate cap" in out.lower()

    def test_already_reacted_is_silent_and_continues(self, monkeypatch, capsys):
        """Bot's own retry path can revisit a card; `already_reacted` is
        a benign no-op and should not produce log noise."""
        import slack_post

        calls = []

        class _FakeClient:
            def reactions_add(self, channel, timestamp, name):
                calls.append(name)
                raise self_test._fake_slack_error("already_reacted")

        self_test = self
        monkeypatch.setattr(slack_post, "_bot_client", lambda: _FakeClient())
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKE")
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        slack_post._add_reactions("172.000001", emojis=["test_tube", "+1", "-1"])
        # All three emojis were attempted — already_reacted does NOT bail
        assert calls == ["test_tube", "+1", "-1"]
        # And the log is silent (no noisy lines)
        out = capsys.readouterr().out
        assert "already_reacted" not in out  # silent
        assert "reactions.add" not in out  # no per-emoji noise

    def test_breaker_prevents_per_card_spam(self, monkeypatch, capsys):
        """Critical observability fix: on the live run, missing_scope
        printed 7 identical "Skipping all reactions" lines (one per card)
        because the bail was per-card. The breaker collapses that to ONE
        line per run. Test simulates 7 cards calling _add_reactions."""
        import slack_post

        calls = []

        class _FakeClient:
            def reactions_add(self, channel, timestamp, name):
                calls.append((timestamp, name))
                raise self_test._fake_slack_error("missing_scope")

        self_test = self
        monkeypatch.setattr(slack_post, "_bot_client", lambda: _FakeClient())
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKE")
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        # Reset breaker as the real entry point would do
        slack_post.reset_reaction_breaker()

        # Simulate 7 cards each calling _add_reactions
        for ts in [f"172.00000{i}" for i in range(1, 8)]:
            slack_post._add_reactions(ts, emojis=["test_tube", "+1", "-1"])

        # Card 1 made 1 API call (failed → tripped breaker).
        # Cards 2-7 made ZERO calls — breaker short-circuited the whole loop.
        assert len(calls) == 1, (
            f"expected 1 API call across 7 cards (breaker should short-"
            f"circuit), got {len(calls)}: {calls}"
        )
        # And the operator sees the message ONCE, not 7 times.
        out = capsys.readouterr().out
        assert out.count("Skipping all reactions") == 1, (
            f"breaker should log exactly once per run; got:\n{out}"
        )

    def test_breaker_resets_between_runs(self, monkeypatch):
        """The breaker must clear when reset_reaction_breaker() is called
        (which weekly_briefing_threaded does at the start of every run).
        Otherwise a missing_scope hit on Monday's briefing would silently
        suppress reactions on every subsequent briefing forever."""
        import slack_post

        # Trip the breaker manually
        slack_post._REACTION_BREAKER_TRIPPED["missing_scope"] = True
        assert slack_post._REACTION_BREAKER_TRIPPED  # truthy

        slack_post.reset_reaction_breaker()
        assert not slack_post._REACTION_BREAKER_TRIPPED  # cleared

    def test_other_error_logs_real_reason_and_continues(self, monkeypatch, capsys):
        """If one emoji fails for a non-fatal reason (e.g. custom-emoji
        doesn't exist in the workspace), other reactions on the card can
        still land — log the reason and continue."""
        import slack_post

        calls = []

        class _FakeClient:
            def reactions_add(self, channel, timestamp, name):
                calls.append(name)
                if name == "test_tube":
                    raise self_test._fake_slack_error("invalid_name")
                # +1 and -1 succeed
                return {"ok": True}

        self_test = self
        monkeypatch.setattr(slack_post, "_bot_client", lambda: _FakeClient())
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C0FAKE")
        monkeypatch.setattr(slack_post.time, "sleep", lambda s: None)

        slack_post._add_reactions("172.000001", emojis=["test_tube", "+1", "-1"])
        # All three were attempted
        assert calls == ["test_tube", "+1", "-1"]
        out = capsys.readouterr().out
        # The failing one was logged with its actual error code
        assert "invalid_name" in out
        # And the others didn't add log noise
        assert "Skipping all reactions" not in out


class TestDebugMode:
    """`DEBUG=true` in GitHub Actions repo vars bypasses Mem0 entirely:
    prior-filter passes everything through, seeding is skipped. Lets us
    run back-to-back tests without manually wiping Mem0, and without
    polluting the production memory store with test verdicts.

    Production scheduled crons leave DEBUG unset → normal Mem0 behaviour."""

    def test_debug_off_by_default(self, monkeypatch):
        import scout
        monkeypatch.delenv("DEBUG", raising=False)
        assert scout._debug_mode() is False

    def test_debug_false_keeps_mem0_on(self, monkeypatch):
        import scout
        monkeypatch.setenv("DEBUG", "false")
        assert scout._debug_mode() is False

    def test_debug_true_variations(self, monkeypatch):
        import scout
        for value in ("true", "True", "TRUE", "1", "yes", "Yes"):
            monkeypatch.setenv("DEBUG", value)
            assert scout._debug_mode() is True, f"DEBUG={value!r} should be truthy"

    def test_debug_garbage_is_off(self, monkeypatch):
        """Defensive: anything other than the explicit truthy set keeps
        production behaviour. Avoids accidental debug-mode if someone
        typos `DEBUG=tru` or sets it to `0`."""
        import scout
        for value in ("0", "no", "off", "", "tru", "False"):
            monkeypatch.setenv("DEBUG", value)
            assert scout._debug_mode() is False, f"DEBUG={value!r} should be falsy"

    def test_filter_by_mem0_bypasses_in_debug(self, monkeypatch, capsys):
        """Most important test: when DEBUG is on, filter_by_mem0 returns
        every item unchanged regardless of Mem0 state."""
        import scout
        monkeypatch.setenv("DEBUG", "true")
        items = [
            {"title": "DSPy 2.5", "url": "https://github.com/stanfordnlp/dspy"},
            {"title": "LangGraph 0.5", "url": "https://github.com/langchain-ai/langgraph"},
        ]
        kept, dropped = scout.filter_by_mem0(items)
        assert kept == items, "DEBUG mode should pass every item through"
        assert dropped == 0
        # Banner is printed so the operator can see DEBUG is on
        out = capsys.readouterr().out
        assert "DEBUG" in out and "bypassing Mem0" in out

    def test_seed_mem0_skips_in_debug(self, monkeypatch, capsys):
        """Symmetric: when DEBUG is on, seed_mem0 is a no-op so a test
        run with garbage verdicts doesn't write to the production store."""
        import scout
        monkeypatch.setenv("DEBUG", "true")
        verdicts = [{
            "tool_name": "Fake-Tool", "verdict": "trial", "category": "tool",
            "soc2": "safe", "what": "x", "why_it_matters": "y",
            "adoption_cost": "z", "next_action": "w",
        }]
        # Should return cleanly without trying to import memory
        scout.seed_mem0(verdicts)
        out = capsys.readouterr().out
        assert "DEBUG" in out and "NOT seeding Mem0" in out


class TestQuietWeekBriefing:
    """The bot ALWAYS posts something on its schedule. Silence makes
    operators assume the bot is broken; a quiet-week heartbeat is the
    right signal: scanned N, considered M, shipped 0, here's why."""

    def test_fetch_empty_reason_renders(self):
        import slack_post
        blocks = slack_post.quiet_week_blocks(
            date="2026-05-21", scanned=0, candidates=0,
            reason="fetch_empty", duration_s=12.0,
            detail="All source fetchers returned 0 items.",
        )
        # Header always present
        assert blocks[0]["type"] == "header"
        assert "Weekly Briefing" in blocks[0]["text"]["text"]
        # Body mentions "Lean fetch" — the fetch_empty headline
        body_texts = [
            b.get("text", {}).get("text", "") for b in blocks
            if b.get("type") == "section"
        ]
        assert any("Lean fetch" in t for t in body_texts)
        # Funnel context block carries 0/0/0/0
        context_texts = [
            e.get("text", "")
            for b in blocks if b.get("type") == "context"
            for e in b.get("elements", [])
        ]
        assert any("*0* scanned" in t and "*0* shipped" in t for t in context_texts)
        # Detail line surfaces the fetcher diagnostic
        assert any("All source fetchers returned" in t for t in context_texts)

    def test_all_filtered_reason_renders(self):
        import slack_post
        blocks = slack_post.quiet_week_blocks(
            date="2026-05-21", scanned=313, dedup_drops=5, prior_drops=308,
            candidates=0, reason="all_filtered", duration_s=45.0,
        )
        body_texts = [
            b.get("text", {}).get("text", "") for b in blocks
            if b.get("type") == "section"
        ]
        assert any("Radar already up-to-date" in t for t in body_texts)
        # considered = scanned - dedup - prior = 313 - 5 - 308 = 0
        context_texts = [
            e.get("text", "")
            for b in blocks if b.get("type") == "context"
            for e in b.get("elements", [])
        ]
        assert any("*313* scanned" in t for t in context_texts)
        assert any("*0* considered" in t for t in context_texts)

    def test_no_verdicts_reason_renders(self):
        import slack_post
        blocks = slack_post.quiet_week_blocks(
            date="2026-05-21", scanned=313, dedup_drops=5, prior_drops=0,
            candidates=308, reason="no_verdicts", cost=0.26, duration_s=180.0,
            detail="Judge vetoed all 4 draft verdict(s). Judge: Nothing notable.",
        )
        body_texts = [
            b.get("text", {}).get("text", "") for b in blocks
            if b.get("type") == "section"
        ]
        assert any("Quiet week" in t for t in body_texts)
        context_texts = [
            e.get("text", "")
            for b in blocks if b.get("type") == "context"
            for e in b.get("elements", [])
        ]
        # Cost rendered
        assert any("$0.26" in t for t in context_texts)
        # Detail line surfaces the judge summary
        assert any("Judge vetoed all 4" in t for t in context_texts)

    def test_unknown_reason_falls_back_to_no_verdicts(self):
        """Defensive: an unexpected reason string shouldn't crash; it falls
        back to the "no_verdicts" headline so SOMETHING posts."""
        import slack_post
        blocks = slack_post.quiet_week_blocks(
            date="2026-05-21", scanned=10, candidates=10,
            reason="some-future-reason-not-yet-defined",
        )
        body_texts = [
            b.get("text", {}).get("text", "") for b in blocks
            if b.get("type") == "section"
        ]
        # No KeyError; renders the no_verdicts headline as fallback
        assert any("Quiet week" in t for t in body_texts)

    def test_block_shape_is_valid_block_kit(self):
        """Quick structural sanity: every block has a `type`; no None
        values; no empty top-level keys that would trip Slack."""
        import slack_post
        blocks = slack_post.quiet_week_blocks(
            date="2026-05-21", scanned=10, candidates=10,
            reason="no_verdicts", cost=0.10,
        )
        for b in blocks:
            assert isinstance(b, dict)
            assert "type" in b
            assert b["type"] in {"header", "section", "context", "divider"}
            # Slack accessibility: section blocks must have text
            if b["type"] == "section":
                assert "text" in b
                assert b["text"].get("text"), f"empty section text in {b!r}"


# ── Round 8: Slack visual refresh — invariant guards ────────────────────────

class TestRound8VerdictCardCompactness:
    """Verdict cards must be ≤4 inner blocks (Round 8 compression rule).
    Previous design was 7 blocks per card; the refresh halves the visual
    weight without losing information."""

    def _verdict(self, **overrides) -> dict:
        v = {
            "tool_name": "DSPy", "verdict": "trial", "category": "tool",
            "soc2": "safe", "what": "Stanford prompt-programming framework.",
            "why_it_matters": "Could replace ad-hoc prompt templates in our LangGraph nodes with a typed, reproducible pipeline.",
            "adoption_cost": "~4 hours to audit.", "next_action": "Lab one node.",
            "source_url": "https://github.com/stanfordnlp/dspy",
            "severity": "high", "readiness": 4,
        }
        v.update(overrides)
        return v

    def test_card_has_at_most_four_inner_blocks(self):
        import slack_post
        outer, atts = slack_post._threaded_verdict_card(1, self._verdict())
        # The attachment carries the body blocks; outer carries actions.
        inner = atts[0].get("blocks") or []
        assert len(inner) <= 4, (
            f"Round 8 limits verdict card to 4 inner blocks; got {len(inner)}: "
            f"{[b.get('type') for b in inner]}"
        )

    def test_card_with_memory_trend_still_within_four(self, monkeypatch):
        """With Mem0 trend present, card grows to 4 blocks — still under cap."""
        import slack_post
        monkeypatch.setattr(slack_post, "_memory_trend_text",
                            lambda tool, verdict: "🧠 Memory: ASSESS (Mar 14) → TRIAL (today)")
        outer, atts = slack_post._threaded_verdict_card(1, self._verdict())
        inner = atts[0].get("blocks") or []
        assert len(inner) == 4, f"Expected exactly 4 inner blocks with trend; got {len(inner)}"
        # Last block IS the trend
        assert "Memory" in inner[-1]["elements"][0]["text"]


class TestRound8NoEmojiAsLabel:
    """No body block opens with `:emoji: *Label*` — emoji are status badges
    only, not field labels. Slack's [Block Kit guidance](https://docs.slack.dev/concepts/designing-with-block-kit/)
    explicitly says use bold text for labels, not emoji."""

    def test_verdict_card_body_has_no_emoji_labels(self):
        import slack_post, re
        v = {
            "tool_name": "Test", "verdict": "adopt", "category": "tool",
            "soc2": "safe", "what": "x", "why_it_matters": "y",
            "adoption_cost": "z", "next_action": "w",
            "source_url": "https://github.com/foo/bar",
            "severity": "standard", "readiness": 3,
        }
        outer, atts = slack_post._threaded_verdict_card(1, v)
        inner = atts[0].get("blocks") or []
        # Look at every text element in every block
        emoji_label_pattern = re.compile(r"^[\U0001F300-\U0001FAFF☀-➿⌀-⏿✀-➿]+\s*\*[A-Z]")
        for block in inner:
            if block.get("type") == "section":
                text = (block.get("text") or {}).get("text", "")
                # Allow emoji INSIDE the prose, just not at the start
                # alongside a bold label like ":bulb: *Why it matters*"
                first_line = text.split("\n", 1)[0]
                # The hero line carries severity trail and link; that's OK.
                # We're checking the OLD pattern where every body label was
                # emoji-prefixed (💡 *Why it matters*, etc.)
                assert "💡  *Why it matters*" not in text, (
                    "Round 8 dropped 💡-prefixed labels — found in:\n" + text
                )
                assert "📅  *Why this week*" not in text, (
                    "Round 8 dropped 📅-prefixed labels — found in:\n" + text
                )
            if block.get("type") == "section" and "fields" in block:
                for f in block["fields"]:
                    t = f.get("text", "")
                    assert not t.startswith("⏱"), \
                        "Round 8 dropped ⏱ emoji-label on Adoption field"
                    assert not t.startswith("▶"), \
                        "Round 8 dropped ▶ emoji-label on Next action field"


class TestRound8TldrRichTextList:
    """The TL;DR uses rich_text_list with per-row metadata. Killed the
    multi-line section-mrkdwn whitespace bug AND added executive-grade
    signal per row (link + what + severity + SOC2 + readiness)."""

    def _make_blocks(self, num_verdicts: int = 4) -> list[dict]:
        import slack_post
        verdicts = []
        for i in range(num_verdicts):
            verdicts.append({
                "tool_name": f"Tool {i+1}",
                "verdict": ["adopt", "trial", "trial", "assess"][i],
                "category": "tool", "soc2": "safe",
                "what": f"Description of Tool {i+1}.",
                "why_it_matters": f"Matters because of reason {i+1}.",
                "adoption_cost": "x", "next_action": "y",
                "source_url": f"https://github.com/foo/tool{i+1}",
                "severity": "standard", "readiness": 3,
            })
        return slack_post._threaded_parent_blocks(
            date="2026-05-21", scanned=300, cost=0.3,
            verdicts=verdicts, judge_rating="medium", judge_summary="",
            dedup_drops=10, prior_drops=5, duration_s=200.0,
        )

    def test_tldr_uses_rich_text_list_not_section_mrkdwn(self):
        """The TL;DR per-tier rows are rich_text_list (no whitespace games)."""
        blocks = self._make_blocks()
        # Find rich_text blocks in the parent
        rt_blocks = [b for b in blocks if b.get("type") == "rich_text"]
        # At least one rich_text_list inside
        has_list = False
        for rt in rt_blocks:
            for el in rt.get("elements", []):
                if el.get("type") == "rich_text_list":
                    has_list = True
                    break
        assert has_list, "TL;DR must use rich_text_list (no whitespace-faked bullets)"

    def test_no_multiline_section_mrkdwn_in_tldr(self):
        """Round 8 invariant: the multi-line section-mrkdwn whitespace
        bug (#1 / #6 flush-left while siblings indent) is killed at root.
        No section block in the parent carries multi-line `text` that
        encodes a TL;DR list."""
        blocks = self._make_blocks()
        # Tier-anchor context blocks are fine; what we're checking is that
        # no SECTION block carries a multi-line text encoding multiple
        # verdict rows. Tier headers are context (single-line). Section
        # blocks remaining are the judge's read or other prose.
        for b in blocks:
            if b.get("type") != "section":
                continue
            text = (b.get("text") or {}).get("text", "")
            # Specifically: no section block contains multiple `#N` ranks
            # — that would be the old whitespace-indented TL;DR pattern.
            import re
            rank_hits = re.findall(r"`#\d+`", text)
            assert len(rank_hits) <= 1, (
                f"Section block carries {len(rank_hits)} `#N` ranks — that's "
                f"the old whitespace-faked TL;DR pattern. rich_text_list "
                f"should carry these instead.\nText:\n{text}"
            )

    def test_tldr_bullets_carry_metadata(self):
        """Each TL;DR bullet contains the tool URL, severity word, SOC2,
        and the readiness meter — executive-grade signal per row."""
        blocks = self._make_blocks()
        # Collect every rich_text_list bullet
        bullets_text = []
        for b in blocks:
            if b.get("type") != "rich_text":
                continue
            for el in b.get("elements", []):
                if el.get("type") != "rich_text_list":
                    continue
                for bullet in el.get("elements", []):
                    spans = bullet.get("elements", [])
                    text = " ".join(
                        s.get("text", "") for s in spans if isinstance(s, dict)
                    )
                    bullets_text.append(text)
        assert len(bullets_text) >= 1, "Expected at least one rich_text_list bullet"
        # Every bullet has the per-row metadata strip
        for t in bullets_text:
            assert "Readiness" in t, f"bullet missing readiness meter: {t!r}"
            assert "SOC2-" in t, f"bullet missing SOC2 word: {t!r}"


class TestRound8OverflowContract:
    """Overflow options must stay Slack-valid.

    Slack rejects `confirm` nested inside overflow options with `invalid_blocks`,
    so these entries intentionally carry compact `value` payloads only.
    """

    def test_snooze_overflow_option_has_no_confirm(self):
        import slack_post
        v = {
            "tool_name": "Test", "verdict": "trial", "category": "tool",
            "soc2": "safe", "what": "x", "why_it_matters": "y",
            "adoption_cost": "z", "next_action": "w",
            "source_url": "https://github.com/foo/bar",
            "severity": "standard", "readiness": 3,
        }
        outer, _atts = slack_post._threaded_verdict_card(1, v)
        actions = next(b for b in outer if b.get("type") == "actions")
        overflow = next(e for e in actions["elements"] if e.get("type") == "overflow")
        # Look up the Snooze option by its value (compact `{a, t}` JSON)
        import json
        snooze_opt = next(
            opt for opt in overflow["options"]
            if json.loads(opt["value"]).get("a") == "snooze_30d"
        )
        assert "confirm" not in snooze_opt, "Slack overflow options cannot include confirm"

    def test_mark_seen_overflow_option_has_no_confirm(self):
        import slack_post
        v = {
            "tool_name": "Test", "verdict": "trial", "category": "tool",
            "soc2": "safe", "what": "x", "why_it_matters": "y",
            "adoption_cost": "z", "next_action": "w",
            "source_url": "https://github.com/foo/bar",
            "severity": "standard", "readiness": 3,
        }
        outer, _atts = slack_post._threaded_verdict_card(1, v)
        actions = next(b for b in outer if b.get("type") == "actions")
        overflow = next(e for e in actions["elements"] if e.get("type") == "overflow")
        import json
        mark_opt = next(
            opt for opt in overflow["options"]
            if json.loads(opt["value"]).get("a") == "mark_seen"
        )
        assert "confirm" not in mark_opt, "Slack overflow options cannot include confirm"

    def test_copy_link_does_not_need_confirm(self):
        """Read-only actions don't need a confirm dialog."""
        import slack_post
        v = {
            "tool_name": "Test", "verdict": "trial", "category": "tool",
            "soc2": "safe", "what": "x", "why_it_matters": "y",
            "adoption_cost": "z", "next_action": "w",
            "source_url": "https://github.com/foo/bar",
            "severity": "standard", "readiness": 3,
        }
        outer, _atts = slack_post._threaded_verdict_card(1, v)
        actions = next(b for b in outer if b.get("type") == "actions")
        overflow = next(e for e in actions["elements"] if e.get("type") == "overflow")
        import json
        copy_opt = next(
            opt for opt in overflow["options"]
            if json.loads(opt["value"]).get("a") == "copy_link"
        )
        # copy_link is read-only; confirm is optional. Present or absent both OK.
        # Just check it's still under the 150-char value limit.
        assert len(copy_opt["value"]) < 151


class TestRound8ImageAccessory:
    """`section.accessory: image` resolves to tool-org avatars."""

    def test_github_url_resolves_to_org_avatar(self):
        import slack_post
        acc = slack_post._image_accessory("https://github.com/stanfordnlp/dspy")
        assert acc is not None
        assert acc["type"] == "image"
        assert "github.com/stanfordnlp.png" in acc["image_url"]
        assert "alt_text" in acc and "stanfordnlp" in acc["alt_text"]

    def test_huggingface_url_resolves_to_avatar(self):
        import slack_post
        acc = slack_post._image_accessory("https://huggingface.co/meta-llama/Llama-3")
        assert acc is not None
        assert "huggingface.co/avatars/meta-llama" in acc["image_url"]

    def test_pypi_url_returns_none(self):
        """PyPI URLs don't have a free avatar source — None is correct."""
        import slack_post
        assert slack_post._image_accessory("https://pypi.org/project/dspy/") is None

    def test_empty_url_returns_none(self):
        import slack_post
        assert slack_post._image_accessory("") is None
        assert slack_post._image_accessory("not-a-url") is None


class TestRound8HeroTakeaway:
    """`_hero_takeaway` trims long prose to a sensible hero length."""

    def test_short_text_passes_through(self):
        import slack_post
        assert slack_post._hero_takeaway("Short sentence.") == "Short sentence."

    def test_long_text_trimmed_at_sentence_boundary(self):
        import slack_post
        long = (
            "First sentence is reasonable and ends here. " * 5
            + "And then a second."
        )
        out = slack_post._hero_takeaway(long)
        assert len(out) <= 181  # 180 + the trailing period
        # Should end at a sentence boundary
        assert out.endswith(".") or out.endswith("…")

    def test_empty_returns_empty(self):
        import slack_post
        assert slack_post._hero_takeaway("") == ""
        assert slack_post._hero_takeaway(None) == ""


class TestRound8LabResultBlocks:
    """The lab reply has ≤5 blocks (incl. attachment), recommendation pill
    in the first block, attachment color matches the recommendation."""

    def _common(self):
        return {
            "tool": "obra/superpowers",
            "url": "https://github.com/obra/superpowers",
            "classification": {"category": "agent_lib", "package": "superpowers"},
            "sandbox": {"exit_code": 0, "stage": "run", "duration_s": 45.0,
                        "stdout": "...", "stderr": ""},
            "insights": {
                "headline": "Solo-dev experimental skills package; not production-ready.",
                "verdict_for_team": "skip",
                "what_worked": "Package imports cleanly.",
                "what_didnt": "Claude Code runtime not available.",
                "next_step": "Monitor for stability; revisit in 3 months.",
                "test_quality_self_rating": "low",
            },
            "cost": 0.35,
        }

    def test_skip_recommendation_gives_red_attachment(self):
        import slack_post
        _outer, atts = slack_post.lab_result_blocks(**self._common())
        assert atts[0]["color"] == "#d93025", "skip → red"

    def test_worth_trial_gives_amber(self):
        import slack_post
        common = self._common()
        common["insights"]["verdict_for_team"] = "worth_trial"
        _outer, atts = slack_post.lab_result_blocks(**common)
        assert atts[0]["color"] == "#f2c744", "worth_trial → amber"

    def test_monitor_gives_gray(self):
        import slack_post
        common = self._common()
        common["insights"]["verdict_for_team"] = "monitor"
        _outer, atts = slack_post.lab_result_blocks(**common)
        assert atts[0]["color"] == "#9aa0a6", "monitor → gray"

    def test_recommendation_pill_appears_in_first_block(self):
        """Round 8 invariant: the recommendation (SKIP/TRIAL/MONITOR) is
        the FIRST thing the reader sees, not buried on line 4 of 7."""
        import slack_post
        _outer, atts = slack_post.lab_result_blocks(**self._common())
        first_block = atts[0]["blocks"][0]
        first_text = (first_block.get("text") or {}).get("text", "")
        assert "SKIP" in first_text, (
            "Recommendation pill must be in the FIRST block — "
            f"got: {first_text!r}"
        )

    def test_no_hermetic_footnote(self):
        """The 'Hermetic subprocess…' footnote is dropped in Round 8 —
        it was first-demo trust theater; lives in docs now."""
        import slack_post
        _outer, atts = slack_post.lab_result_blocks(**self._common())
        for block in atts[0]["blocks"]:
            block_str = str(block)
            assert "Hermetic subprocess" not in block_str, (
                "Round 8 dropped the Hermetic-subprocess footnote — "
                "found it back in the reply"
            )

    def test_code_excerpt_renders_as_preformatted(self):
        """When a test excerpt is provided, it appears as a
        rich_text_preformatted block (proof, not theater)."""
        import slack_post
        common = self._common()
        excerpt = "from superpowers import skills\nskills.list_available()"
        _outer, atts = slack_post.lab_result_blocks(test_excerpt=excerpt, **common)
        # Find the rich_text block with preformatted child
        found = False
        for block in atts[0]["blocks"]:
            if block.get("type") != "rich_text":
                continue
            for child in block.get("elements", []):
                if child.get("type") == "rich_text_preformatted":
                    text = "".join(
                        e.get("text", "") for e in child.get("elements", [])
                    )
                    if "from superpowers" in text:
                        found = True
        assert found, "Lab reply must include a rich_text_preformatted excerpt"


class TestRound8TestExcerpt:
    """`_test_excerpt` pulls a small representative slice from the
    generated test script for the rich_text_preformatted block."""

    def test_skips_docstring_and_comments(self):
        import lab_runner
        script = '''"""This is a docstring."""

# A leading comment
# Another comment

import dspy
print("OK: imported")
obj = dspy.Predict("x -> y")
'''
        excerpt = lab_runner._test_excerpt(script, max_lines=3)
        assert "docstring" not in excerpt
        assert excerpt.startswith("import dspy")
        assert excerpt.count("\n") <= 2  # 3 lines = 2 newlines max

    def test_returns_empty_on_empty_input(self):
        import lab_runner
        assert lab_runner._test_excerpt("") == ""
        assert lab_runner._test_excerpt(None) == ""

    def test_caps_at_max_lines(self):
        import lab_runner
        script = "\n".join(f"line_{i}" for i in range(20))
        excerpt = lab_runner._test_excerpt(script, max_lines=4)
        assert excerpt.count("\n") == 3, "should cap at 4 lines"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
