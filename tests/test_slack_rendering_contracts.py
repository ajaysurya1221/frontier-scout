import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import slack_post  # noqa: E402


FIXTURES = REPO_ROOT / "tests" / "fixtures" / "slack"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_threaded_parent_snapshot_polished():
    payload = _load("regression_wall_of_text_input.json")
    actual = slack_post._threaded_parent_blocks(
        date=payload["date"],
        scanned=payload["scanned"],
        cost=payload["cost"],
        verdicts=payload["verdicts"],
        judge_rating=payload["judge_rating"],
        judge_summary=payload["judge_summary"],
        dedup_drops=payload["dedup_drops"],
        prior_drops=payload["prior_drops"],
        duration_s=payload["duration_s"],
    )
    expected = _load("threaded_parent_polished.json")
    assert actual == expected


def test_threaded_verdict_card_snapshot_polished():
    payload = _load("regression_wall_of_text_input.json")
    blocks, attachments = slack_post._threaded_verdict_card(1, payload["verdicts"][0])
    expected = _load("threaded_verdict_card_polished.json")
    assert {"blocks": blocks, "attachments": attachments} == expected


def test_parent_layout_contracts_against_wall_of_text_regression():
    payload = _load("regression_wall_of_text_input.json")
    blocks = slack_post._threaded_parent_blocks(
        date=payload["date"],
        scanned=payload["scanned"],
        cost=payload["cost"],
        verdicts=payload["verdicts"],
        judge_rating=payload["judge_rating"],
        judge_summary=payload["judge_summary"],
        dedup_drops=payload["dedup_drops"],
        prior_drops=payload["prior_drops"],
        duration_s=payload["duration_s"],
    )

    assert len(blocks) <= 10, "parent message should stay within a concise first screen"

    # Must include explicit IA labels instead of a dense context-only header.
    section_texts = [
        (b.get("text") or {}).get("text", "")
        for b in blocks
        if b.get("type") == "section"
    ]
    joined = "\n".join(section_texts)
    assert "*What happened*" in joined
    assert "*Why it matters*" in joined
    assert "*What to do next*" in joined

    # No wall-of-text context strip.
    for block in blocks:
        if block.get("type") != "context":
            continue
        text = " ".join(e.get("text", "") for e in block.get("elements", []))
        assert len(text) <= 220, f"context line too long: {len(text)} chars"


def test_overflow_options_are_slack_valid_no_confirm():
    payload = _load("regression_wall_of_text_input.json")
    blocks, _atts = slack_post._threaded_verdict_card(1, payload["verdicts"][0])
    actions = next(b for b in blocks if b.get("type") == "actions")
    overflow = next(e for e in actions["elements"] if e.get("type") == "overflow")

    for option in overflow.get("options", []):
        assert "confirm" not in option, "Slack rejects confirm inside overflow options"
        assert len(option.get("value", "")) < 151


def test_actions_have_accessibility_labels_under_limit():
    payload = _load("regression_wall_of_text_input.json")
    blocks, _atts = slack_post._threaded_verdict_card(1, payload["verdicts"][0])
    actions = next(b for b in blocks if b.get("type") == "actions")
    for el in actions.get("elements", []):
        if el.get("type") in {"button"}:
            label = el.get("accessibility_label", "")
            assert label, "interactive buttons should include accessibility labels"
            assert len(label) <= 75


def test_escape_mrkdwn_neutralizes_mass_mentions():
    raw = "@channel <!here> <!everyone> plain"
    out = slack_post._escape_mrkdwn(raw)
    assert "@\u200bchannel" in out
    assert "&lt;!\u200bhere&gt;" in out
    assert "&lt;!\u200beveryone&gt;" in out


def test_sanitize_sensitive_text_redacts_slack_secrets():
    raw = (
        "url=https://hooks.slack.com/services/T/B/SECRET "
        "action=https://hooks.slack.com/actions/T/B/ABC "
        "token=xoxb-12345-abcd"
    )
    out = slack_post._sanitize_sensitive_text(raw)
    assert "SECRET" not in out
    assert "ABC" not in out
    assert "xoxb-12345-abcd" not in out
    assert "REDACTED" in out or "****" in out
