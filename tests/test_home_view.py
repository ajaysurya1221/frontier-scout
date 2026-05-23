"""Unit tests for scripts/home_view.py — the App Home dashboard view.

The dashboard is the bot's persistent surface. Pin the invariants that
matter:
  • Cold-start (empty state) still renders a complete view
  • Sparkline helpers handle every edge case (empty / flat / partial)
  • No image blocks anywhere (Round 9 design rule)
  • Every `section` block has non-empty text
  • Taste-model section shows the right shape in cold start vs warm
  • Recent-labs section is omitted (not blank-rendered) when no labs
  • View always contains exactly one `header` and ends in a footer

All tests run offline with no I/O — `build_view` accepts a state dict
that the Lambda dispatcher assembles separately.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Sparkline + bar-row helpers ──────────────────────────────────────────────

class TestSparkline:
    def test_empty_renders_baseline(self):
        import home_view
        assert home_view._sparkline([]) == "▁" * 8
        assert home_view._sparkline(None) == "▁" * 8

    def test_flat_renders_uniform_mid_bars(self):
        """Flat input → uniform mid-level bars (not all-zeros)."""
        import home_view
        out = home_view._sparkline([3, 3, 3, 3])
        # 4 mid-bars on the right, padded with empty bars on the left
        assert out.endswith("▄▄▄▄"), f"flat series should end in ▄▄▄▄: {out!r}"
        assert len(out) == 8

    def test_rising_series_is_strictly_increasing(self):
        import home_view
        out = home_view._sparkline([1, 2, 3, 4, 5, 6, 7, 8])
        # Each successive char should be >= the previous in the bar levels
        bars = " ▁▂▃▄▅▆▇█"
        levels = [bars.index(c) for c in out]
        assert levels == sorted(levels), f"rising series broken: {out!r}"
        assert out[0] != out[-1], "should span the bar range"

    def test_partial_series_left_pads(self):
        """Series shorter than width left-pads so newest data is on right."""
        import home_view
        out = home_view._sparkline([5, 6, 7], width=8)
        assert len(out) == 8
        # First 5 chars should be the empty pad
        assert out[:5] == "▁" * 5
        # Last 3 chars carry the actual data
        assert out[-3:] != "▁" * 3

    def test_tails_to_width(self):
        """Series longer than width should be truncated to the last N values."""
        import home_view
        out = home_view._sparkline(list(range(20)), width=8)
        assert len(out) == 8

    def test_handles_negative_values(self):
        """Negative-positive ranges still produce 8 chars without crash."""
        import home_view
        out = home_view._sparkline([-3, -1, 0, 1, 3])
        assert len(out) == 8


class TestBarRow:
    def test_zero_value_is_all_empty(self):
        import home_view
        assert home_view._bar_row(0, 10) == "▱▱▱▱▱"

    def test_full_value_is_all_filled(self):
        import home_view
        assert home_view._bar_row(10, 10) == "▰▰▰▰▰"

    def test_half_value_is_half_filled(self):
        import home_view
        assert home_view._bar_row(5, 10) == "▰▰▰▱▱" or home_view._bar_row(5, 10) == "▰▰▱▱▱"

    def test_zero_max_returns_empty(self):
        """Avoid divide-by-zero on degenerate inputs."""
        import home_view
        assert home_view._bar_row(5, 0) == "▱▱▱▱▱"

    def test_value_above_max_caps_at_full(self):
        """Don't render 6/5 ▰ — clip at full."""
        import home_view
        assert home_view._bar_row(20, 10) == "▰▰▰▰▰"


class TestRelativeTime:
    def test_unknown_input_returns_unknown(self):
        import home_view
        assert home_view._humanise_relative_time(None) == "unknown"
        assert home_view._humanise_relative_time("not-a-date") == "unknown"
        assert home_view._humanise_relative_time("") == "unknown"

    def test_recent_renders_minutes(self):
        import home_view
        from datetime import datetime, timezone, timedelta
        t = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        out = home_view._humanise_relative_time(t)
        assert "min ago" in out, out

    def test_yesterday_renders_days(self):
        import home_view
        from datetime import datetime, timezone, timedelta
        t = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        out = home_view._humanise_relative_time(t)
        assert "days ago" in out, out

    def test_future_timestamp_renders_shortly(self):
        """Don't show negative 'days ago' for clock-skew inputs."""
        import home_view
        from datetime import datetime, timezone, timedelta
        t = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        assert home_view._humanise_relative_time(t) == "shortly"


# ── build_view — full integration tests ──────────────────────────────────────

class TestBuildView:
    def test_cold_start_renders_complete_view(self):
        """With empty state, every section still produces a placeholder
        block — no blank panels, no crash."""
        import home_view
        view = home_view.build_view({})
        assert view["type"] == "home"
        assert isinstance(view["blocks"], list)
        assert len(view["blocks"]) >= 6, "even cold start should have 6+ blocks"
        # Every section block has non-empty text
        for b in view["blocks"]:
            if b.get("type") != "section":
                continue
            text = (b.get("text") or {}).get("text", "")
            assert text and text.strip(), f"empty section: {b}"

    def test_no_image_blocks_anywhere(self):
        """Round 9 design rule: text sparklines only, no image blocks."""
        import home_view
        view = home_view.build_view({"preferences": {"signal_count_14d": 50}})
        for b in view["blocks"]:
            assert b.get("type") != "image", \
                f"Image block found in App Home view; design says text-only: {b}"
            # Section blocks also can't have an image accessory
            if b.get("type") == "section":
                acc = b.get("accessory")
                if acc:
                    assert acc.get("type") != "image", \
                        f"Image accessory found in App Home section: {b}"

    def test_exactly_one_header_block(self):
        """Dashboard hierarchy: ONE top-level header. Subsections use
        bold-text titles inside section blocks."""
        import home_view
        view = home_view.build_view({})
        headers = [b for b in view["blocks"] if b.get("type") == "header"]
        assert len(headers) == 1, f"expected exactly 1 header; got {len(headers)}"

    def test_last_block_is_footer_context(self):
        """The final block should be the meta-info context strip."""
        import home_view
        view = home_view.build_view({})
        last = view["blocks"][-1]
        assert last.get("type") == "context"

    def test_cold_start_taste_model_section_shows_helpful_message(self):
        """Below the 10-signal threshold, the taste-model section should
        be informative, not blank or vague."""
        import home_view
        view = home_view.build_view({
            "preferences": {"signal_count_14d": 3, "tags": {}},
        })
        # Find the taste-model section by its bold header
        found = False
        for b in view["blocks"]:
            if b.get("type") == "section":
                text = (b.get("text") or {}).get("text", "")
                if "Channel taste model" in text:
                    found = True
                    assert "Cold start" in text
                    assert "react" in text.lower(), \
                        "Cold start message should tell users how to train it"
                    break
        assert found, "Taste model section not rendered"

    def test_warm_taste_model_section_shows_top_tags(self):
        """Above the threshold, top positive + negative tags appear with bars."""
        import home_view
        state = {
            "preferences": {
                "signal_count_14d": 47,
                "reaction_count_14d": 42,
                "lab_count_14d": 5,
                "tags": {
                    "mcp": 0.91, "agentic-coding": 0.74, "evals": 0.45,
                    "no-code": -0.63, "image-gen": -0.81,
                },
            },
        }
        view = home_view.build_view(state)
        body = "\n".join(
            (b.get("text") or {}).get("text", "")
            for b in view["blocks"] if b.get("type") == "section"
        )
        # Tuned-by line renders the individual reaction + lab counts.
        assert "42" in body and "reactions" in body
        assert "5" in body and "lab queues" in body
        assert "mcp" in body
        assert "no-code" in body or "image-gen" in body
        # Bar rows appear next to tags
        assert "▰" in body

    def test_recent_labs_section_omitted_when_no_labs(self):
        """No labs run yet → that section is skipped entirely, not blank."""
        import home_view
        view = home_view.build_view({})
        body = "\n".join(
            (b.get("text") or {}).get("text", "")
            for b in view["blocks"] if b.get("type") == "section"
        )
        assert "Recent labs" not in body, \
            "Recent labs section should be omitted when no labs"

    def test_recent_labs_section_renders_with_labs(self):
        import home_view
        state = {
            "recent_labs": [
                {"tool": "dspy", "verdict_for_team": "worth_trial",
                 "ran_at": "2026-05-19T12:00:00Z"},
                {"tool": "ragas", "verdict_for_team": "monitor",
                 "ran_at": "2026-05-15T12:00:00Z"},
            ],
        }
        view = home_view.build_view(state)
        body = "\n".join(
            (b.get("text") or {}).get("text", "")
            for b in view["blocks"] if b.get("type") == "section"
        )
        assert "Recent labs" in body
        assert "dspy" in body and "ragas" in body
        # Recommendation pills present
        assert "worth a TRIAL" in body or "TRIAL" in body
        assert "MONITOR" in body

    def test_this_week_section_shows_count_and_cost(self):
        import home_view
        state = {
            "verdicts_this_week": 7,
            "verdicts_per_week": [3, 5, 7, 6, 5, 4, 6, 7],
            "mtd_cost": 1.42,
            "cost_per_day_mtd": [0.0, 0.0, 0.31, 0.0, 0.0, 0.0, 0.5, 0.0,
                                 0.0, 0.0, 0.31, 0.0, 0.0, 0.3],
        }
        view = home_view.build_view(state)
        body = "\n".join(
            (b.get("text") or {}).get("text", "")
            for b in view["blocks"] if b.get("type") == "section"
        )
        assert "*7*" in body, "verdict count should be bold-rendered"
        assert "$1.42" in body, "MTD cost should be rendered"
        # Sparklines present (Unicode bars)
        bar_chars = "▁▂▃▄▅▆▇█"
        assert any(c in body for c in bar_chars), \
            "sparkline chars not found in 'This week' section"

    def test_latest_briefing_section_with_data(self):
        import home_view
        state = {
            "latest_briefing": {
                "date": "2026-05-21",
                "verdicts_count": 7,
                "judge_rating": "high",
                "judge_summary": "Strong upstream pass; one veto.",
            },
        }
        view = home_view.build_view(state)
        body = "\n".join(
            (b.get("text") or {}).get("text", "")
            for b in view["blocks"] if b.get("type") == "section"
        )
        assert "2026-05-21" in body
        assert "*7*" in body
        assert "HIGH" in body
        assert "Strong upstream pass" in body

    def test_latest_briefing_placeholder_when_missing(self):
        """No briefings yet → placeholder explaining when the first one ships."""
        import home_view
        view = home_view.build_view({"latest_briefing": None})
        body = "\n".join(
            (b.get("text") or {}).get("text", "")
            for b in view["blocks"] if b.get("type") == "section"
        )
        assert "Latest briefing" in body
        assert "No briefings yet" in body or "first one ships" in body.lower()

    def test_view_total_block_count_is_reasonable(self):
        """Slack views have a hard cap of 100 blocks. Our dashboard
        should be well under it for any reasonable input."""
        import home_view
        # Plug in a "fully populated" state to test the max case
        state = {
            "preferences": {
                "signal_count_14d": 50,
                "reaction_count_14d": 45,
                "lab_count_14d": 5,
                "tags": {f"tag{i}": 0.5 - i * 0.05 for i in range(20)},
            },
            "verdicts_this_week": 7,
            "verdicts_per_week": list(range(8)),
            "mtd_cost": 5.0,
            "cost_per_day_mtd": list(range(14)),
            "recent_labs": [
                {"tool": f"t{i}", "verdict_for_team": "worth_trial",
                 "ran_at": "2026-05-19T12:00:00Z"}
                for i in range(5)
            ],
            "latest_briefing": {
                "date": "2026-05-21", "verdicts_count": 7,
                "judge_rating": "high", "judge_summary": "x",
            },
        }
        view = home_view.build_view(state)
        assert len(view["blocks"]) <= 30, \
            f"App Home view has {len(view['blocks'])} blocks; aim for tightness"


# ── preferences.top_tags helper (new in Round 9) ─────────────────────────────

class TestPreferencesTopTags:
    def test_positive_top_k(self):
        import preferences
        prefs = {
            "tags": {
                "mcp": 0.91, "evals": 0.45, "agentic": 0.74,
                "no-code": -0.63, "rag": 0.30,
            },
        }
        out = preferences.top_tags(prefs, k=3, side="positive")
        assert len(out) == 3
        # Sorted descending by weight
        assert out[0][0] == "mcp"
        assert out[1][0] == "agentic"
        assert out[2][0] == "evals"

    def test_negative_top_k(self):
        import preferences
        prefs = {"tags": {"a": 1.0, "no-code": -0.6, "image-gen": -0.9}}
        out = preferences.top_tags(prefs, k=2, side="negative")
        assert len(out) == 2
        assert out[0][0] == "image-gen"  # most negative first
        assert out[1][0] == "no-code"

    def test_empty_tags_returns_empty_list(self):
        import preferences
        assert preferences.top_tags({"tags": {}}, k=3) == []
        assert preferences.top_tags({}, k=3) == []

    def test_invalid_side_raises(self):
        import preferences
        with pytest.raises(ValueError):
            preferences.top_tags({"tags": {"a": 1}}, side="elsewhere")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
