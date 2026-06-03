"""Richer local architecture profile — deterministic, no source."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from frontier_scout.profile import (  # noqa: E402
    DependencySpec,
    ImportEvidenceSummary,
    ScoutProfile,
    ai_categories,
    build_scout_profile,
    derive_archetype,
    stack_from_profile,
)
from prompts import render_stack_profile  # noqa: E402  # scripts/ on sys.path  # fmt: skip


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
    assert (
        derive_archetype(_p(frameworks=["django"], agent_configs=["CLAUDE.md"]))
        == "web-service"
    )


UV_LOCK = """
version = 1
[[package]]
name = "fastapi"
version = "0.110.1"
[[package]]
name = "anthropic"
version = "0.39.0"
"""

PYPROJECT = """
[project]
name = "demo"
dependencies = ["fastapi", "anthropic>=0.3"]
"""


def test_python_lock_versions_resolved(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "uv.lock").write_text(UV_LOCK)
    profile = build_scout_profile(tmp_path, scan_imports=False)
    by_name = {d.name.lower(): d for d in profile.dependencies}
    assert by_name["fastapi"].resolved_version == "0.110.1"
    assert by_name["anthropic"].resolved_version == "0.39.0"


def test_python_lock_absent_is_safe(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    profile = build_scout_profile(tmp_path, scan_imports=False)
    assert {d.name.lower() for d in profile.dependencies} >= {"fastapi", "anthropic"}


def test_ai_categories_grouping():
    p = _p(
        ai_tooling=[
            "anthropic",
            "langgraph",
            "qdrant",
            "ragas",
            "litellm",
            "weirdthing",
        ]
    )
    cats = ai_categories(p)
    assert cats["llm-sdk"] == ["anthropic"]
    assert cats["agent-framework"] == ["langgraph"]
    assert cats["vector-store"] == ["qdrant"]
    assert cats["eval"] == ["ragas"]
    assert cats["gateway"] == ["litellm"]
    assert cats["other"] == ["weirdthing"]  # unknown tag → "other", never dropped


def test_stack_from_profile_carries_rich_signal():
    p = _p(
        languages=["python"],
        frameworks=["fastapi"],
        package_managers=["uv"],
        ai_tooling=["anthropic", "qdrant"],
        agent_configs=["CLAUDE.md"],
    )
    p.archetype = "web-service"
    p.dependencies = [
        DependencySpec(
            name="fastapi",
            ecosystem="pypi",
            resolved_version="0.110.1",
            manifest_path="pyproject.toml",
            evidence_imports=12,
        ),
        DependencySpec(
            name="anthropic",
            ecosystem="pypi",
            specifier=">=0.3",
            manifest_path="pyproject.toml",
            evidence_imports=5,
        ),
    ]
    p.import_evidence = ImportEvidenceSummary(
        top_python=[("anthropic", 5), ("fastapi", 12)]
    )
    stack = stack_from_profile(p)
    assert stack["languages"] == ["python"]
    assert "fastapi" in stack["frameworks"]
    assert stack["ai_tooling"] == ["anthropic", "qdrant"]
    assert stack["archetype"] == "web-service"
    assert stack["ai_categories"]["vector-store"] == ["qdrant"]
    assert {"name": "fastapi", "ecosystem": "pypi", "version": "0.110.1"} in stack[
        "dependencies"
    ]
    assert stack["top_imports"]["python"][:2] == ["fastapi", "anthropic"]


def test_stack_from_profile_bounds_dependencies():
    p = _p()
    p.dependencies = [
        DependencySpec(
            name=f"dep{i}", ecosystem="pypi", manifest_path="r.txt", evidence_imports=i
        )
        for i in range(40)
    ]
    assert len(stack_from_profile(p)["dependencies"]) == 15


def test_render_brief_includes_rich_signal():
    stack = {
        "languages": ["python"],
        "frameworks": ["fastapi"],
        "package_managers": ["uv"],
        "agent_configs": ["CLAUDE.md"],
        "archetype": "web-service",
        "ai_categories": {"llm-sdk": ["anthropic"], "vector-store": ["qdrant"]},
        "dependencies": [
            {"name": "fastapi", "ecosystem": "pypi", "version": "0.110.1"}
        ],
        "top_imports": {"python": ["fastapi", "anthropic"]},
    }
    out = render_stack_profile(stack)
    assert out.startswith("STACK_PROFILE:")
    assert "Archetype: web-service" in out
    assert "vector-store: qdrant" in out
    assert "fastapi 0.110.1" in out
    assert "Top python imports: fastapi, anthropic" in out


def test_render_none_and_empty_stubs_unchanged():
    assert "STACK_PROFILE: (none)" in render_stack_profile(None)
    assert "STACK_PROFILE: (empty)" in render_stack_profile({})


def test_render_redacts_secret_shaped_value():
    stack = {
        "dependencies": [
            {"name": "sk-ant-" + "A" * 30, "ecosystem": "pypi", "version": "1"}
        ]
    }
    out = render_stack_profile(stack)
    assert "sk-ant-" not in out
    assert "‹redacted›" in out


def test_stack_from_profile_dedups_dependencies_by_name():
    p = _p()
    # same package from two manifests (different manifest_path) + a version on one
    p.dependencies = [
        DependencySpec(
            name="pydantic",
            ecosystem="pypi",
            specifier=">=2.0",
            manifest_path="pyproject.toml",
            evidence_imports=3,
        ),
        DependencySpec(
            name="pydantic",
            ecosystem="pypi",
            resolved_version="2.6.4",
            manifest_path="requirements.txt",
            evidence_imports=0,
        ),
    ]
    deps = stack_from_profile(p)["dependencies"]
    names = [d["name"] for d in deps]
    assert names.count("pydantic") == 1  # deduped
    assert deps[0]["version"] == "2.6.4"  # kept the entry with a resolved version
