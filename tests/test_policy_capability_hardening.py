"""Regression tests for two hardening fixes found by the RLAIF quality loop.

1. ``policy.load_policy`` must fall back to defaults on a malformed/unreadable
   ``policy.toml`` (its docstring promises "falling back to defaults"), not
   crash every caller with a TOMLDecodeError.
2. ``mcp_audit.classify_mcp_capabilities`` must flag the common real-world
   phrasings of dangerous capabilities (shell execution, file writes,
   credential handling). Previously the narrow single-stem regexes missed
   "run arbitrary commands", "writes/deletes", "authentication", etc., which
   silently dropped the danger flag on real tool descriptions.
"""

from __future__ import annotations

import pytest

from frontier_scout.mcp_audit import classify_mcp_capabilities
from frontier_scout.policy import DEFAULT_POLICY, Policy, load_policy

# ── 1. load_policy resilience ─────────────────────────────────────────────────


def test_load_policy_falls_back_on_malformed_toml(tmp_path, monkeypatch):
    # Neutralise the home (~) policy candidate so the fall-through lands on
    # DEFAULT_POLICY deterministically.
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    fs_dir = tmp_path / ".frontier-scout"
    fs_dir.mkdir(parents=True)
    (fs_dir / "policy.toml").write_text('[policy]\nbad = "unterminated string\n')

    # Must NOT raise; must hand back the default policy.
    policy = load_policy(tmp_path)
    assert policy is DEFAULT_POLICY


def test_load_policy_falls_back_on_wrong_field_type(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    fs_dir = tmp_path / ".frontier-scout"
    fs_dir.mkdir(parents=True)
    # Valid TOML, but a bool field given a string -> pydantic ValidationError,
    # which (like TOMLDecodeError) subclasses ValueError and must be caught.
    (fs_dir / "policy.toml").write_text('[policy]\nstrict = "definitely-not-a-bool"\n')

    policy = load_policy(tmp_path)
    assert policy is DEFAULT_POLICY


def test_load_policy_still_loads_valid_file(tmp_path, monkeypatch):
    # Happy path must keep working (guard against an over-broad except).
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    fs_dir = tmp_path / ".frontier-scout"
    fs_dir.mkdir(parents=True)
    (fs_dir / "policy.toml").write_text(
        "[policy]\nallow_adopt_without_lab_for_low_risk = true\n"
    )

    policy = load_policy(tmp_path)
    assert isinstance(policy, Policy)
    assert policy is not DEFAULT_POLICY
    assert policy.allow_adopt_without_lab_for_low_risk is True


# ── 2. capability danger detection ────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected_flag",
    [
        ("This server can run arbitrary commands.", "shell"),
        ("Runs arbitrary python on the host.", "shell"),
        ("Calls os.system to spawn a process.", "shell"),
        ("Writes files to your filesystem and deletes records.", "write"),
        ("Creates and modifies documents in place.", "write"),
        ("Requires authentication with your account.", "credential"),
        ("Sends an authorization header with every request.", "credential"),
    ],
)
def test_classify_flags_dangerous_phrasings(text, expected_flag):
    manifest = classify_mcp_capabilities(text)
    assert expected_flag in manifest.dangerous_flags, (
        f"{expected_flag!r} not flagged for {text!r}; got {manifest.dangerous_flags}"
    )


def test_classify_does_not_false_positive_credential_on_author():
    # "authored" / "author" must NOT trip the credential ("auth") pattern.
    manifest = classify_mcp_capabilities(
        "A read-only docs server authored by the community; browse the guides."
    )
    assert "credential" not in manifest.dangerous_flags


def test_classify_empty_text_fails_closed():
    # The fail-closed contract: no signal -> unknown danger flag.
    manifest = classify_mcp_capabilities("")
    assert manifest.dangerous_flags == ["unknown"]
