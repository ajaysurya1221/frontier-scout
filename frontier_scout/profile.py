"""Local repo intelligence for personalized scouting."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from pydantic import BaseModel, Field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


# --- Models ------------------------------------------------------------------


class DependencySpec(BaseModel):
    """One local manifest dependency used for repo-aware scouting."""

    name: str
    ecosystem: str
    specifier: str = ""
    resolved_version: str | None = None
    manifest_path: str
    evidence_imports: int = 0


class ImportEvidenceSummary(BaseModel):
    """Compact import-evidence rollup carried on the profile."""

    top_python: list[tuple[str, int]] = Field(default_factory=list)
    top_javascript: list[tuple[str, int]] = Field(default_factory=list)
    files_scanned: int = 0
    available: bool = True
    partial: bool = False


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
    import_evidence: ImportEvidenceSummary = Field(default_factory=ImportEvidenceSummary)


# --- Walker ------------------------------------------------------------------


_MANIFEST_FILENAMES = frozenset(
    {
        "package.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
        "Pipfile",
        "Pipfile.lock",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }
)

_SKIP_DIRS = frozenset(
    {
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        ".cache",
        "site-packages",
        ".git",
        ".gradle",
        ".idea",
        ".vscode",
        ".frontier-scout",
        ".scratch",
        "vendor",
        ".turbo",
        ".parcel-cache",
        ".svelte-kit",
    }
)


def _walk_manifests(repo: Path, *, max_depth: int = 3) -> dict[Path, set[str]]:
    """Return ``{directory: filenames-present}`` for any directory at depth
    ``<= max_depth`` that holds at least one known manifest.

    Skips dependency caches, VCS directories, and dot-directories below the
    repo root. The repo root itself is always included if it has manifests.
    """

    if not (repo.exists() and repo.is_dir()):
        return {}
    found: dict[Path, set[str]] = {}

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(current))
        except (OSError, PermissionError):
            return
        present: set[str] = set()
        for entry in entries:
            name = entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if name in _SKIP_DIRS:
                    continue
                if name.startswith("."):
                    continue
                walk(Path(entry.path), depth + 1)
                continue
            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if is_file and name in _MANIFEST_FILENAMES:
                present.add(name)
        if present:
            found[current] = present

    walk(repo, 0)
    return found


# --- Rule tables for import-evidence promotion -------------------------------


_PY_FRAMEWORK_RULES: dict[str, tuple[str, str]] = {
    "fastapi": ("frameworks", "fastapi"),
    "django": ("frameworks", "django"),
    "flask": ("frameworks", "flask"),
    "starlette": ("frameworks", "starlette"),
    "pydantic": ("frameworks", "pydantic"),
    "pytest": ("frameworks", "pytest"),
    "sqlalchemy": ("frameworks", "sqlalchemy"),
    "celery": ("frameworks", "celery"),
}

_PY_AI_RULES: dict[str, tuple[str, str]] = {
    "openai": ("ai_tooling", "openai"),
    "anthropic": ("ai_tooling", "anthropic"),
    "langchain": ("ai_tooling", "langchain"),
    "langchain_core": ("ai_tooling", "langchain"),
    "langchain_community": ("ai_tooling", "langchain"),
    "langchain_openai": ("ai_tooling", "langchain"),
    "langchain_anthropic": ("ai_tooling", "langchain"),
    "langgraph": ("ai_tooling", "langgraph"),
    "llama_index": ("ai_tooling", "llamaindex"),
    "llamaindex": ("ai_tooling", "llamaindex"),
    "mcp": ("ai_tooling", "mcp"),
    "crewai": ("ai_tooling", "crewai"),
    "autogen": ("ai_tooling", "autogen"),
    "instructor": ("ai_tooling", "instructor"),
    "dspy": ("ai_tooling", "dspy"),
    "haystack": ("ai_tooling", "haystack"),
    "transformers": ("ai_tooling", "transformers"),
    "sentence_transformers": ("ai_tooling", "sentence-transformers"),
    "litellm": ("ai_tooling", "litellm"),
    "vllm": ("ai_tooling", "vllm"),
    "google": ("ai_tooling", "google-genai"),  # google.generativeai, google.adk
    "vertexai": ("ai_tooling", "vertex-ai"),
    "boto3": ("ai_tooling", "bedrock-or-aws"),  # weak signal; bedrock usage often via boto3
    "neo4j": ("ai_tooling", "neo4j"),
    "pinecone": ("ai_tooling", "pinecone"),
    "weaviate": ("ai_tooling", "weaviate"),
    "qdrant_client": ("ai_tooling", "qdrant"),
    "chromadb": ("ai_tooling", "chromadb"),
}

_JS_RULES: dict[str, tuple[str, str]] = {
    "react": ("frameworks", "react"),
    "next": ("frameworks", "next"),
    "vue": ("frameworks", "vue"),
    "svelte": ("frameworks", "svelte"),
    "express": ("frameworks", "express"),
    "fastify": ("frameworks", "fastify"),
    "nestjs": ("frameworks", "nestjs"),
    "@modelcontextprotocol/sdk": ("ai_tooling", "mcp"),
    "@mastra/core": ("ai_tooling", "mastra"),
    "ai": ("ai_tooling", "vercel-ai-sdk"),
    "openai": ("ai_tooling", "openai"),
    "@anthropic-ai/sdk": ("ai_tooling", "anthropic"),
    "langchain": ("ai_tooling", "langchain"),
    "@langchain/core": ("ai_tooling", "langchain"),
    "@langchain/langgraph": ("ai_tooling", "langgraph"),
    "@google/generative-ai": ("ai_tooling", "google-genai"),
}

# PyPI distribution name -> import module name (when they differ).
_PYPI_IMPORT_ALIAS: dict[str, str] = {
    "pillow": "PIL",
    "beautifulsoup4": "bs4",
    "pyyaml": "yaml",
    "python-dateutil": "dateutil",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "python-dotenv": "dotenv",
    "python-multipart": "multipart",
    "python-json-logger": "pythonjsonlogger",
    "psycopg2-binary": "psycopg2",
    "discord.py": "discord",
    "msgpack-python": "msgpack",
    "protobuf": "google",
    "grpcio": "grpc",
    "google-generativeai": "google",
    "google-cloud-aiplatform": "google",
    "google-adk": "google",
}


# --- Build profile -----------------------------------------------------------


def build_scout_profile(repo: Path, *, scan_imports: bool = True) -> ScoutProfile:
    """Build a conservative profile from filenames, manifests, and import ASTs.

    Reads file *structure*, never source meaning. Avoids secret-bearing env
    paths. When ``scan_imports`` is False, the tree-sitter import pass is
    skipped (faster) and framework/ai_tooling promotion falls back to
    manifest-substring heuristics only.
    """

    repo = repo.resolve()
    profile = ScoutProfile(repo=str(repo), repo_id=_repo_id(repo))

    manifests_by_dir = _walk_manifests(repo)

    for manifest_dir, files in manifests_by_dir.items():
        rel_dir = "" if manifest_dir == repo else str(manifest_dir.relative_to(repo))

        if "package.json" in files:
            _add(profile.languages, "javascript/typescript")
            _add(profile.package_managers, "npm")
            _read_package_json(manifest_dir / "package.json", profile, repo=repo)
        if "pnpm-lock.yaml" in files:
            _add(profile.package_managers, "pnpm")
        if "yarn.lock" in files:
            _add(profile.package_managers, "yarn")
        if "bun.lock" in files or "bun.lockb" in files:
            _add(profile.package_managers, "bun")

        if "pyproject.toml" in files or "requirements.txt" in files:
            _add(profile.languages, "python")
            _add(profile.package_managers, "pip")
            _read_python_manifest(manifest_dir, profile, repo=repo)
        if "uv.lock" in files:
            _add(profile.package_managers, "uv")
            _add(profile.languages, "python")
        if "Pipfile" in files or "Pipfile.lock" in files:
            _add(profile.languages, "python")
            _add(profile.package_managers, "pipenv")

        if "Cargo.toml" in files:
            _add(profile.languages, "rust")
            _add(profile.package_managers, "cargo")
        if "go.mod" in files:
            _add(profile.languages, "go")
            _add(profile.package_managers, "go")
        if "Gemfile" in files:
            _add(profile.languages, "ruby")
            _add(profile.package_managers, "bundler")

        for candidate in (
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        ):
            if candidate in files:
                rel = candidate if rel_dir == "" else f"{rel_dir}/{candidate}"
                _add(profile.containers, rel)

    if profile.containers:
        _add(profile.frameworks, "docker")

    # CI detection stays root-level.
    if (repo / ".github" / "workflows").exists():
        _add(profile.ci, "github-actions")
    for candidate in (".gitlab-ci.yml", "circle.yml", "Jenkinsfile"):
        if (repo / candidate).exists():
            _add(profile.ci, candidate)

    # Agent configs / coding-agent surfaces stay root-level.
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
        ".understand-anything",
    ):
        if (repo / candidate).exists():
            _add(profile.agent_configs, candidate)

    # Import-evidence pass — deterministic, local, optional.
    if scan_imports:
        from frontier_scout.imports import scan_imports as _scan_imports

        evidence = _scan_imports(repo)
        profile.import_evidence = ImportEvidenceSummary(
            top_python=_top_items(evidence.python_imports, 10),
            top_javascript=_top_items(evidence.js_imports, 10),
            files_scanned=evidence.files_scanned,
            available=evidence.available,
            partial=evidence.partial,
        )
        if evidence.available:
            _apply_import_rules(profile, evidence.python_imports, evidence.js_imports)
            _annotate_dependency_evidence(profile, evidence.python_imports, evidence.js_imports)

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


# --- Manifest readers --------------------------------------------------------


def _read_package_json(path: Path, profile: ScoutProfile, *, repo: Path) -> None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    manifest_path = _relative_to(path, repo)
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
                manifest_path=manifest_path,
            ),
        )
        low = name.lower()
        # Weak signals from manifest-only mode (kept so --no-imports still tags something).
        if low in {"next", "react", "vue", "svelte", "express", "fastify"}:
            _add(profile.frameworks, low)
        if low in {"langchain", "llamaindex", "ai", "@modelcontextprotocol/sdk", "@mastra/core"}:
            _add(profile.frameworks, low)
            _add(profile.ai_tooling, low)
        if "mcp" in low or "agent" in low or "openai" in low or "anthropic" in low:
            _add(profile.ai_tooling, low)


def _read_python_manifest(manifest_dir: Path, profile: ScoutProfile, *, repo: Path) -> None:
    candidates = [
        manifest_dir / "pyproject.toml",
        manifest_dir / "requirements.txt",
    ]
    text = ""
    for path in candidates:
        if not path.exists():
            continue
        manifest_path = _relative_to(path, repo)
        try:
            raw = path.read_text(errors="ignore")[:200000]
            text += "\n" + raw
            if path.name == "requirements.txt":
                _parse_requirements_txt(raw, manifest_path, profile)
            elif path.name == "pyproject.toml":
                _parse_pyproject(raw, manifest_path, profile)
        except OSError:
            continue
    # Weak signals so --no-imports / no tree-sitter still tags something.
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


def _relative_to(path: Path, repo: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return path.name


def _top_items(counts: dict[str, int], n: int) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:n]


# --- Import-evidence wiring --------------------------------------------------


def _apply_import_rules(
    profile: ScoutProfile,
    python_imports: dict[str, int],
    js_imports: dict[str, int],
) -> None:
    for module, count in python_imports.items():
        if count < 1:
            continue
        key = module
        framework = _PY_FRAMEWORK_RULES.get(key)
        if framework is not None:
            list_name, tag = framework
            _add(getattr(profile, list_name), tag)
        ai = _PY_AI_RULES.get(key)
        if ai is not None:
            list_name, tag = ai
            _add(getattr(profile, list_name), tag)
    for module, count in js_imports.items():
        if count < 1:
            continue
        rule = _JS_RULES.get(module) or _JS_RULES.get(module.lower())
        if rule is not None:
            list_name, tag = rule
            _add(getattr(profile, list_name), tag)


def _annotate_dependency_evidence(
    profile: ScoutProfile,
    python_imports: dict[str, int],
    js_imports: dict[str, int],
) -> None:
    """Set ``DependencySpec.evidence_imports`` from import counts.

    Sums counts across all aliases of a distribution name (e.g. ``Pillow`` →
    ``PIL``, ``scikit-learn`` → ``sklearn``).
    """

    for dep in profile.dependencies:
        if dep.ecosystem == "pypi":
            candidates = _python_import_candidates(dep.name)
            total = sum(
                count
                for module, count in python_imports.items()
                if module in candidates or module.lower() in candidates
            )
            if total:
                dep.evidence_imports = total
        elif dep.ecosystem == "npm":
            count = js_imports.get(dep.name) or js_imports.get(dep.name.lower()) or 0
            if count:
                dep.evidence_imports = count


def _python_import_candidates(name: str) -> set[str]:
    """Return possible import module names for a PyPI distribution name."""

    norm = name.lower()
    candidates = {norm, norm.replace("-", "_")}
    alias = _PYPI_IMPORT_ALIAS.get(norm)
    if alias:
        candidates.add(alias)
        candidates.add(alias.split(".")[0])
    return candidates
