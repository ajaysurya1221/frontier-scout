"""Local repo intelligence for personalized scouting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from pydantic import BaseModel, Field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


class DependencySpec(BaseModel):
    """One local manifest dependency used for repo-aware scouting."""

    name: str
    ecosystem: str
    specifier: str = ""
    resolved_version: str | None = None
    manifest_path: str


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
    dependencies: list[DependencySpec] = Field(default_factory=list)
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
    resolved = _read_node_lock_versions(path.parent)
    deps: dict[str, Any] = {
        **(data.get("dependencies") or {}),
        **(data.get("devDependencies") or {}),
    }
    for name, specifier in deps.items():
        _add_dependency(
            profile,
            DependencySpec(
                name=name,
                ecosystem="npm",
                specifier=str(specifier or ""),
                resolved_version=resolved.get(name),
                manifest_path=path.name,
            ),
        )
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
            raw = path.read_text(errors="ignore")[:20000]
            text += "\n" + raw
            if path.name == "requirements.txt":
                _parse_requirements_txt(raw, path.name, profile)
            elif path.name == "pyproject.toml":
                _parse_pyproject(raw, path.name, profile)
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


def _add_dependency(profile: ScoutProfile, dependency: DependencySpec) -> None:
    key = (dependency.ecosystem, dependency.name.lower(), dependency.manifest_path)
    existing = {(d.ecosystem, d.name.lower(), d.manifest_path) for d in profile.dependencies}
    if key not in existing:
        profile.dependencies.append(dependency)


def _parse_requirements_txt(text: str, manifest_path: str, profile: ScoutProfile) -> None:
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http://", "https://")):
            continue
        try:
            req = Requirement(line)
        except InvalidRequirement:
            continue
        specifier = str(req.specifier)
        _add_dependency(
            profile,
            DependencySpec(
                name=req.name,
                ecosystem="pypi",
                specifier=specifier,
                resolved_version=_exact_pin(specifier),
                manifest_path=manifest_path,
            ),
        )


def _parse_pyproject(text: str, manifest_path: str, profile: ScoutProfile) -> None:
    if tomllib is None:
        return
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    for raw_req in (data.get("project") or {}).get("dependencies") or []:
        _add_python_requirement(str(raw_req), manifest_path, profile)
    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        specifier = str(spec if isinstance(spec, str) else spec.get("version", ""))
        _add_dependency(
            profile,
            DependencySpec(
                name=name,
                ecosystem="pypi",
                specifier=specifier,
                resolved_version=_exact_pin(specifier),
                manifest_path=manifest_path,
            ),
        )


def _add_python_requirement(raw_req: str, manifest_path: str, profile: ScoutProfile) -> None:
    try:
        req = Requirement(raw_req)
    except InvalidRequirement:
        return
    specifier = str(req.specifier)
    _add_dependency(
        profile,
        DependencySpec(
            name=req.name,
            ecosystem="pypi",
            specifier=specifier,
            resolved_version=_exact_pin(specifier),
            manifest_path=manifest_path,
        ),
    )


def _read_node_lock_versions(repo: Path) -> dict[str, str]:
    package_lock = repo / "package-lock.json"
    if package_lock.exists():
        try:
            data = json.loads(package_lock.read_text(errors="ignore"))
        except (OSError, json.JSONDecodeError):
            data = {}
        versions = {}
        for path, payload in (data.get("packages") or {}).items():
            if not path.startswith("node_modules/") or not isinstance(payload, dict):
                continue
            name = path.removeprefix("node_modules/")
            if payload.get("version"):
                versions[name] = str(payload["version"])
        if versions:
            return versions
    pnpm_lock = repo / "pnpm-lock.yaml"
    if pnpm_lock.exists():
        return _parse_text_lock_versions(pnpm_lock)
    yarn_lock = repo / "yarn.lock"
    if yarn_lock.exists():
        return _parse_text_lock_versions(yarn_lock)
    return {}


def _parse_text_lock_versions(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return versions
    current: str | None = None
    for line in lines:
        stripped = line.strip().strip('"')
        if stripped.endswith(":") and "@" in stripped:
            current = stripped.rsplit("@", 1)[0].strip("'\"")
            if current.startswith("/"):
                current = current.strip("/").split("/", 1)[0]
        elif current and stripped.startswith("version:"):
            versions[current] = stripped.split(":", 1)[1].strip().strip('"')
            current = None
    return versions


def _exact_pin(specifier: str) -> str | None:
    return specifier.removeprefix("==").strip() if specifier.startswith("==") else None
