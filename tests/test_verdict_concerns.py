"""Stream K — verdict concern taxonomy.

Deterministic rules in ``frontier_scout.scout._concerns`` produce a
plain-English explanation for every push-back: "burns tokens",
"abandoned", "security surface", "vendor lock-in", "marketing-only",
"unproven", "weak fit". The Scout tab renders these under the verdict
detail so the user always knows *why* we'd hold a tool back.
"""

from __future__ import annotations

from frontier_scout.scout import _concerns, personalize_verdicts


def _base_verdict(**overrides):
    base = {
        "tool_name": "example/tool",
        "verdict": "trial",
        "category": "dev_tool",
        "fit": "medium",
        "risk": "low",
        "what": "A focused, well-documented utility for X. Does one thing well and ships docs.",
        "source_url": "https://github.com/example/tool",
        "fit_reasons": ["matches Python stack"],
    }
    base.update(overrides)
    return base


def _slugs(verdict_dict) -> set[str]:
    return {c["slug"] for c in _concerns(verdict_dict)}


# ---------------------------------------------------------------------------
# weak_fit
# ---------------------------------------------------------------------------


def test_weak_fit_fires_when_fit_is_low():
    assert "weak_fit" in _slugs(_base_verdict(fit="low"))


def test_weak_fit_fires_when_fit_reasons_is_the_no_match_sentinel():
    v = _base_verdict(fit_reasons=["no strong local stack match detected"])
    assert "weak_fit" in _slugs(v)


def test_weak_fit_silent_for_clean_high_fit():
    assert "weak_fit" not in _slugs(_base_verdict(fit="high"))


# ---------------------------------------------------------------------------
# token_burn
# ---------------------------------------------------------------------------


def test_token_burn_fires_for_model_drop():
    assert "token_burn" in _slugs(_base_verdict(category="model_drop"))


def test_token_burn_fires_when_cost_per_call_exceeds_5_cents():
    assert "token_burn" in _slugs(_base_verdict(cost_per_call_usd=0.06))


def test_token_burn_silent_for_cheap_local_tool():
    assert "token_burn" not in _slugs(_base_verdict(cost_per_call_usd=0.001))


def test_token_burn_silent_when_cost_unknown():
    """A None cost field must NOT inflate concern noise."""

    v = _base_verdict()
    v.pop("cost_per_call_usd", None)
    assert "token_burn" not in _slugs(v)


# ---------------------------------------------------------------------------
# abandoned
# ---------------------------------------------------------------------------


def test_abandoned_fires_when_last_release_older_than_9_months():
    assert "abandoned" in _slugs(_base_verdict(last_release_age_days=300))


def test_abandoned_silent_for_recent_release():
    assert "abandoned" not in _slugs(_base_verdict(last_release_age_days=14))


def test_abandoned_silent_when_age_unknown():
    v = _base_verdict()
    v.pop("last_release_age_days", None)
    assert "abandoned" not in _slugs(v)


# ---------------------------------------------------------------------------
# security_surface
# ---------------------------------------------------------------------------


def test_security_surface_fires_on_write_capability():
    v = _base_verdict(
        permission_manifest={"dangerous_flags": ["write"]},
    )
    assert "security_surface" in _slugs(v)


def test_security_surface_silent_for_network_only():
    """network alone is medium-severity not high-severity; rule fires
    only on write/shell/credential/unknown to match the existing
    policy.py severity floor."""

    v = _base_verdict(
        permission_manifest={"dangerous_flags": ["network"]},
    )
    assert "security_surface" not in _slugs(v)


# ---------------------------------------------------------------------------
# vendor_lock_in
# ---------------------------------------------------------------------------


def test_vendor_lock_in_fires_on_explicit_high_risk():
    assert "vendor_lock_in" in _slugs(_base_verdict(lock_in_risk="high"))


def test_vendor_lock_in_fires_on_vendor_domain_for_dev_tool():
    v = _base_verdict(
        source_url="https://platform.openai.com/some-sdk",
        category="dev_tool",
    )
    assert "vendor_lock_in" in _slugs(v)


def test_vendor_lock_in_silent_for_skill_on_vendor_domain():
    """We don't flag skill/mcp_server on a vendor domain — those are
    open-spec items, not a lock-in concern."""

    v = _base_verdict(
        source_url="https://anthropic.com/skills",
        category="skill",
    )
    assert "vendor_lock_in" not in _slugs(v)


# ---------------------------------------------------------------------------
# marketing_only
# ---------------------------------------------------------------------------


def test_marketing_only_fires_for_short_description_without_code_repo():
    v = _base_verdict(
        what="The best AI tool",  # 16 chars, under 40
        source_url="https://example-startup.com/",
    )
    assert "marketing_only" in _slugs(v)


def test_marketing_only_silent_when_source_is_github():
    """Even a short ``what`` is acceptable if a public code repo exists."""

    v = _base_verdict(
        what="MCP server",
        source_url="https://github.com/example/mcp-server",
    )
    assert "marketing_only" not in _slugs(v)


# ---------------------------------------------------------------------------
# unproven
# ---------------------------------------------------------------------------


def test_unproven_fires_for_agent_framework_without_local_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    v = _base_verdict(category="agent_framework")
    assert "unproven" in _slugs(v)


def test_unproven_silent_when_local_receipt_exists(tmp_path, monkeypatch):
    """If a previous trial wrote a receipt for this tool, no unproven flag."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    v = _base_verdict(category="mcp_server", tool_name="probed-tool")
    # Inject a fake "latest_trial_for_tool" hit at the import site.
    import frontier_scout.scout as scout_mod
    import frontier_scout.store as store_mod

    monkeypatch.setattr(
        store_mod,
        "latest_trial_for_tool",
        lambda name: {"trial_id": 1} if name == "probed-tool" else None,
    )
    # Force re-import inside scout_mod's local namespace by calling
    # _concerns again — it does a fresh ``from ... import latest_trial_for_tool``
    # inside the function each call.
    _ = scout_mod
    assert "unproven" not in _slugs(v)


# ---------------------------------------------------------------------------
# Integration: personalize_verdicts populates the field
# ---------------------------------------------------------------------------


def test_personalize_verdicts_attaches_concerns_field():
    verdicts = [_base_verdict(category="model_drop", fit="low")]
    profile = {"languages": ["python"]}
    out = personalize_verdicts(verdicts, profile)
    assert "concerns" in out[0]
    slugs = {c["slug"] for c in out[0]["concerns"]}
    # model_drop → token_burn; fit=low → weak_fit
    assert "token_burn" in slugs
    assert "weak_fit" in slugs


def test_personalize_verdicts_clean_high_fit_has_no_concerns(tmp_path, monkeypatch):
    """The happy path: high-fit, low-risk, recent, no danger → empty list."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    verdicts = [
        _base_verdict(
            fit="high",
            category="dev_tool",
            # ``what`` must mention python so _personal_fit attributes a
            # real reason; otherwise the verdict's pristine high-fit is
            # downgraded to "no strong local stack match" and weak_fit fires.
            what="A focused python utility for X. Ships docs and tests on pypi.",
            cost_per_call_usd=0.0,
            last_release_age_days=7,
            permission_manifest={"dangerous_flags": []},
            lock_in_risk="none",
        )
    ]
    profile = {"languages": ["python"]}
    out = personalize_verdicts(verdicts, profile)
    assert out[0]["concerns"] == []
