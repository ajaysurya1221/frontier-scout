"""Regression: an OSV advisory-lookup FAILURE must never present a dependency
as benign (RLAIF quality loop).

Bug: ``_advisory_ids`` swallowed an OSV outage into ``[]``, indistinguishable
from "OSV answered: no advisories". The caller only promotes to "security" when
advisory_ids is non-empty and drops "noise + no advisory" findings entirely — so
during any OSV outage a genuinely-vulnerable upgrade was reported as a benign
"feature"/"assess" or silently dropped.

Fix: ``_advisory_ids`` raises ``AdvisoryLookupError`` on failure; the finding
carries ``advisory_lookup_failed=True``, is never dropped, and is held (not
presented clean) for a human re-run.

Each test is hermetic: a fresh ``FRONTIER_SCOUT_HOME`` per test (so the OSV disk
cache can't bleed across tests) and the OSV cache is stubbed to force the live
lookup path under test.
"""

from __future__ import annotations

import pytest

import frontier_scout.dependencies as deps
from frontier_scout.dependencies import AdvisoryLookupError, _finding_for_dependency
from frontier_scout.profile import DependencySpec


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    # Isolate the home dir so the OSV disk cache is empty for every test, and
    # force a cache MISS so `_advisory_ids` always exercises the live lookup
    # (which the tests stub via `_post_json`).
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(deps, "get_dep_cache", lambda *a, **k: None)
    monkeypatch.setattr(deps, "save_dep_cache", lambda *a, **k: None)


def _dep() -> DependencySpec:
    return DependencySpec(
        name="vulnerable-pkg",
        ecosystem="pypi",
        specifier="==1.0.0",
        resolved_version="1.0.0",
        manifest_path="requirements.txt",
    )


def _benign_meta(_dep, _metadata):
    # A newer version whose notes are a plain feature (no security keywords).
    return {"latest_version": "2.0.0", "release_notes": {"2.0.0": "Adds a nice feature."}}


def _silent_meta(_dep, _metadata):
    # A newer version with empty notes → classifies as "noise" (the path that
    # previously dropped the finding entirely).
    return {"latest_version": "2.0.0", "release_notes": {"2.0.0": ""}}


def _osv_down(*_a, **_k):
    raise RuntimeError("OSV unreachable (simulated 503)")


def test_advisory_lookup_failure_is_not_reported_benign(monkeypatch):
    monkeypatch.setattr(deps, "_package_metadata", _benign_meta)
    monkeypatch.setattr(deps, "_post_json", _osv_down)

    finding = _finding_for_dependency("repo-id", "/repo", _dep(), metadata=None)

    # The whole point: we get a finding (not None) explicitly flagged as
    # un-checked, NOT a benign-looking assess.
    assert finding is not None
    assert finding.advisory_lookup_failed is True
    assert finding.verdict == "hold"
    assert "OSV" in finding.next_safe_step


def test_advisory_lookup_failure_does_not_drop_noise_finding(monkeypatch):
    # Even when the notes would classify as "noise" (the path that returned
    # None), an un-completed advisory check must keep the finding visible.
    monkeypatch.setattr(deps, "_package_metadata", _silent_meta)
    monkeypatch.setattr(deps, "_post_json", _osv_down)

    finding = _finding_for_dependency("repo-id", "/repo", _dep(), metadata=None)

    assert finding is not None  # previously this was silently dropped
    assert finding.advisory_lookup_failed is True


def test_advisory_lookup_raises_not_swallows(monkeypatch):
    monkeypatch.setattr(deps, "_post_json", _osv_down)

    # Direct contract: the helper must raise, not return [].
    with pytest.raises(AdvisoryLookupError):
        deps._advisory_ids(_dep(), "1.0.0", metadata=None)


def test_osv_clean_result_still_drops_noise(monkeypatch):
    # Guard against over-correction: when OSV genuinely answers "no advisories"
    # and the upgrade is noise, the finding is still correctly dropped.
    monkeypatch.setattr(deps, "_package_metadata", _silent_meta)
    monkeypatch.setattr(deps, "_post_json", lambda url, payload: {"vulns": []})

    finding = _finding_for_dependency("repo-id", "/repo", _dep(), metadata=None)
    assert finding is None


def test_osv_real_advisory_still_security(monkeypatch):
    # Happy path: a real advisory on a feature upgrade is promoted to security
    # and is NOT flagged as a failed lookup.
    monkeypatch.setattr(deps, "_package_metadata", _benign_meta)
    monkeypatch.setattr(
        deps, "_post_json", lambda url, payload: {"vulns": [{"id": "GHSA-real-0001"}]}
    )

    finding = _finding_for_dependency("repo-id", "/repo", _dep(), metadata=None)
    assert finding is not None
    assert finding.classification == "security"
    assert finding.advisory_lookup_failed is False
    assert "GHSA-real-0001" in finding.advisory_ids
