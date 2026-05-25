"""Local repo intelligence for personalized scouting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ScoutProfile(BaseModel):
    """A lightweight, local-only profile used to personalize Scout verdicts."""

    repo: str
    repo_id: str
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    ci: list[str] = Field(default_factory=list)
    containers: list[str] = Field(default_factory=list)
    agent_configs: list[str] = Field(default_factory=list)
    ai_tooling: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    adoption_constraints: list[str] = Field(default_factory=list)
    ignored_paths: list[str] = Field(default_factory=lambda: [".env.local", ".env", ".git"])


def build_scout_profile(repo: Path) -> ScoutProfile:
    """Build a conservative profile from filenames and manifests.

    This intentionally avoids reading source files and ignores secret-bearing
    env paths. The goal is stack fit, not code understanding.
    """

    repo = repo.resolve()
    files = {p.name for p in repo.iterdir()} if repo.exists() and repo.is_dir() else set()
    profile = ScoutProfile(repo=str(repo), repo_id=_repo_id(repo))

    if "package.json" in files:
        _add(profile.languages, "javascript/typescript")
        _add(profile.package_managers, "npm")
        _read_package_json(repo / "package.json", profile)
    if "pnpm-lock.yaml" in files:
        _add(profile.package_managers, "pnpm")
    if "yarn.lock" in files:
        _add(profile.package_managers, "yarn")
    if "bun.lock" in files or "bun.lockb" in files:
        _add(profile.package_managers, "bun")
    if "pyproject.toml" in files or "requirements.txt" in files:
        _add(profile.languages, "python")
        _add(profile.package_managers, "pip")
        _read_python_manifest(repo, profile)
    if "uv.lock" in files:
        _add(profile.package_managers, "uv")
    if "Cargo.toml" in files:
        _add(profile.languages, "rust")
        _add(profile.package_managers, "cargo")
    if "go.mod" in files:
        _add(profile.languages, "go")
        _add(profile.package_managers, "go")
    if "Gemfile" in files:
        _add(profile.languages, "ruby")
        _add(profile.package_managers, "bundler")

    for candidate in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        if candidate in files:
            _add(profile.containers, candidate)
    if profile.containers:
        _add(profile.frameworks, "docker")

    if (repo / ".github" / "workflows").exists():
        _add(profile.ci, "github-actions")
    for candidate in (".gitlab-ci.yml", "circle.yml", "Jenkinsfile"):
        if candidate in files:
            _add(profile.ci, candidate)

    for candidate in (
        ".mcp.json",
        "mcp.json",
        "CLAUDE.md",
        "AGENTS.md",
        ".cursor",
        ".codex",
        ".claude",
        ".gemini",
        ".opencode",
    ):
        if (repo / candidate).exists():
            _add(profile.agent_configs, candidate)

    if profile.agent_configs:
        _add(profile.risk_flags, "agent-config-present")
        profile.adoption_constraints.append(
            "Require receipts for new MCP, shell, browser, network, or write capabilities."
        )
    if profile.containers:
        profile.adoption_constraints.append("Prefer sandbox trials that run outside the working tree.")
    if not profile.adoption_constraints:
        profile.adoption_constraints.append("Start with report-only evaluation before installing AI tooling.")

    return profile


def stack_from_profile(profile: ScoutProfile) -> dict[str, Any]:
    """Return the legacy stack shape used by existing evaluation code."""

    return {
        "repo": profile.repo,
        "languages": profile.languages,
        "frameworks": profile.frameworks + profile.containers + profile.ci,
        "package_managers": profile.package_managers,
        "agent_configs": profile.agent_configs,
        "ai_tooling": profile.ai_tooling,
        "risk_flags": profile.risk_flags,
    }


def export_profile(profile: ScoutProfile, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.model_dump(), indent=2) + "\n")
    return path


def _read_package_json(path: Path, profile: ScoutProfile) -> None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    deps: dict[str, Any] = {
        **(data.get("dependencies") or {}),
        **(data.get("devDependencies") or {}),
    }
    for name in deps:
        low = name.lower()
        if low in {"next", "react", "vue", "svelte", "express", "fastify"}:
            _add(profile.frameworks, low)
        if low in {"langchain", "llamaindex", "ai", "@modelcontextprotocol/sdk", "@mastra/core"}:
            _add(profile.frameworks, low)
            _add(profile.ai_tooling, low)
        if "mcp" in low or "agent" in low or "openai" in low or "anthropic" in low:
            _add(profile.ai_tooling, low)


def _read_python_manifest(repo: Path, profile: ScoutProfile) -> None:
    candidates = [repo / "pyproject.toml", repo / "requirements.txt"]
    text = ""
    for path in candidates:
        try:
            text += "\n" + path.read_text(errors="ignore")[:20000]
        except OSError:
            continue
    low = text.lower()
    for marker in ("fastapi", "django", "flask", "pydantic", "pytest"):
        if marker in low:
            _add(profile.frameworks, marker)
    for marker in ("langchain", "llamaindex", "openai", "anthropic", "mcp", "browser-use"):
        if marker in low:
            _add(profile.ai_tooling, marker)


def _repo_id(repo: Path) -> str:
    return hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:16]


def _add(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)
