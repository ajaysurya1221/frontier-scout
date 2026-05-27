"""Integration test for monorepo profile detection.

Exercises the v0.4 walker + import-evidence pipeline against a fixture
shaped like a typical FastAPI service repo (backend/, lambda/, root-level
docker-compose). Asserts the holes that motivated this release are closed.
"""

from __future__ import annotations

from pathlib import Path

from frontier_scout.profile import build_scout_profile


def _seed_genai_core_shape(root: Path) -> None:
    backend = root / "backend"
    (backend / "app").mkdir(parents=True)
    (backend / "requirements.txt").write_text(
        "fastapi==0.115.0\n"
        "pydantic==2.9.2\n"
        "langchain-core==0.3.1\n"
        "python-dotenv==1.0.0\n"
    )
    (backend / "Dockerfile").write_text("FROM python:3.12-slim\n")
    (backend / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "import pydantic\n"
        "from langchain_core.messages import HumanMessage\n"
    )
    (backend / "app" / "settings.py").write_text(
        "import dotenv\n"
    )
    (root / "lambda").mkdir()
    (root / "lambda" / "requirements.txt").write_text("boto3==1.34.0\n")
    (root / "docker-compose.yml").write_text("services:\n  api: {image: x}\n")


def test_monorepo_python_languages_and_frameworks(tmp_path):
    _seed_genai_core_shape(tmp_path)
    profile = build_scout_profile(tmp_path)
    assert "python" in profile.languages
    assert "pip" in profile.package_managers
    assert "fastapi" in profile.frameworks
    assert "pydantic" in profile.frameworks
    assert "langchain" in profile.ai_tooling


def test_monorepo_containers_include_subdir_dockerfile(tmp_path):
    _seed_genai_core_shape(tmp_path)
    profile = build_scout_profile(tmp_path)
    assert "backend/Dockerfile" in profile.containers
    assert "docker-compose.yml" in profile.containers
    # docker auto-tagged on frameworks.
    assert "docker" in profile.frameworks


def test_monorepo_dependencies_have_distinct_manifest_paths(tmp_path):
    _seed_genai_core_shape(tmp_path)
    profile = build_scout_profile(tmp_path)
    by_name = {dep.name.lower(): dep for dep in profile.dependencies}
    assert by_name["fastapi"].manifest_path == "backend/requirements.txt"
    assert by_name["boto3"].manifest_path == "lambda/requirements.txt"
    # Two distinct manifest paths represented.
    paths = {dep.manifest_path for dep in profile.dependencies}
    assert "backend/requirements.txt" in paths
    assert "lambda/requirements.txt" in paths


def test_monorepo_evidence_counts_attach_to_dependencies(tmp_path):
    _seed_genai_core_shape(tmp_path)
    profile = build_scout_profile(tmp_path)
    fastapi = next(d for d in profile.dependencies if d.name.lower() == "fastapi")
    pydantic = next(d for d in profile.dependencies if d.name.lower() == "pydantic")
    boto3 = next(d for d in profile.dependencies if d.name.lower() == "boto3")
    dotenv = next(d for d in profile.dependencies if d.name.lower() == "python-dotenv")
    assert fastapi.evidence_imports >= 1
    assert pydantic.evidence_imports >= 1
    # boto3 is in the manifest but never imported in the fixture.
    assert boto3.evidence_imports == 0
    # python-dotenv import name is `dotenv` — verify the alias resolves.
    assert dotenv.evidence_imports >= 1


def test_monorepo_import_evidence_summary_populated(tmp_path):
    _seed_genai_core_shape(tmp_path)
    profile = build_scout_profile(tmp_path)
    summary = profile.import_evidence
    assert summary.available is True
    assert summary.files_scanned >= 2
    top_modules = {name for name, _count in summary.top_python}
    assert "fastapi" in top_modules
    assert "pydantic" in top_modules


def test_no_imports_mode_skips_evidence(tmp_path):
    _seed_genai_core_shape(tmp_path)
    profile = build_scout_profile(tmp_path, scan_imports=False)
    # Manifest-substring weak signals still classify fastapi/pydantic as frameworks.
    assert "fastapi" in profile.frameworks
    # But no import-evidence counts.
    assert profile.import_evidence.files_scanned == 0
    assert profile.import_evidence.top_python == []
    fastapi = next(d for d in profile.dependencies if d.name.lower() == "fastapi")
    assert fastapi.evidence_imports == 0


def test_walker_ignores_node_modules_at_root(tmp_path):
    """A manifest inside node_modules must not contribute to dependencies."""
    (tmp_path / "node_modules" / "evil").mkdir(parents=True)
    (tmp_path / "node_modules" / "evil" / "package.json").write_text(
        '{"name":"evil","dependencies":{"langchain":"0.0.1"}}\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "package.json").write_text('{"name":"real","dependencies":{"react":"19"}}\n')
    profile = build_scout_profile(tmp_path)
    names = {d.name.lower() for d in profile.dependencies}
    assert "react" in names
    assert "langchain" not in names


def test_understand_anything_directory_detected(tmp_path):
    """Detect .understand-anything as an agent-config signal."""
    (tmp_path / ".understand-anything").mkdir()
    (tmp_path / ".understand-anything" / "knowledge-graph.json").write_text("{}\n")
    profile = build_scout_profile(tmp_path)
    assert ".understand-anything" in profile.agent_configs
