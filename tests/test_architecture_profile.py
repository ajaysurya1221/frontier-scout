"""Richer local architecture profile — deterministic, no source."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from frontier_scout.profile import ScoutProfile, derive_archetype


def _p(**kw) -> ScoutProfile:
    return ScoutProfile(repo="/x", repo_id="x", **kw)


def test_archetype_web_service():
    assert derive_archetype(_p(frameworks=["fastapi"])) == "web-service"
    assert derive_archetype(_p(frameworks=["next", "react"])) == "web-service"


def test_archetype_agent_app():
    assert derive_archetype(_p(ai_tooling=["langgraph"])) == "agent-app"
    assert derive_archetype(_p(agent_configs=["CLAUDE.md"])) == "agent-app"


def test_archetype_ml_data():
    assert derive_archetype(_p(ai_tooling=["transformers"])) == "ml-data"


def test_archetype_library_and_unknown():
    assert derive_archetype(_p(package_managers=["pip"])) == "library"
    assert derive_archetype(_p()) == "unknown"


def test_archetype_web_beats_agent():
    assert derive_archetype(_p(frameworks=["django"], agent_configs=["CLAUDE.md"])) == "web-service"
