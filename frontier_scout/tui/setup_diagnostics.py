"""Read-only setup diagnostics for the Frontier Scout terminal UI."""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from frontier_scout.packs import default_packs
from frontier_scout.profile import ScoutProfile, build_scout_profile
from frontier_scout.store import home_dir, init_home, save_builtin_packs_if_empty

ProviderStatusValue = Literal["found", "present", "missing", "unavailable", "error"]


class ProviderStatus(BaseModel):
    """One read-only provider/backend status card shown during setup."""

    name: str
    kind: str
    status: ProviderStatusValue
    detail: str
    models: list[str] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    """One safe next action offered by setup."""

    id: str
    label: str
    command: str
    description: str
    requires_input: bool = False


class SetupDiagnostics(BaseModel):
    """Data contract shared by plain, JSON, and Textual setup renderers."""

    repo: str
    home: str
    profile: ScoutProfile
    providers: list[ProviderStatus]
    scout_packs: list[str]
    scout_packs_selected: list[str] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction]
    safety_notes: list[str]


def setup_diagnostics(
    repo: Path,
    *,
    ollama_url: str = "http://localhost:11434",
    ollama_timeout_s: float = 0.4,
    selected_packs: list[str] | None = None,
    scan_imports: bool = True,
) -> SetupDiagnostics:
    """Collect local-only setup diagnostics without sending repo content anywhere."""

    resolved_repo = repo.expanduser().resolve()
    init_home()
    save_builtin_packs_if_empty()
    profile = build_scout_profile(resolved_repo, scan_imports=scan_imports)
    packs = sorted(default_packs().keys())
    providers = detect_providers(ollama_url=ollama_url, ollama_timeout_s=ollama_timeout_s)
    valid_selected = [slug for slug in (selected_packs or []) if slug in packs]
    return SetupDiagnostics(
        repo=str(resolved_repo),
        home=str(home_dir()),
        profile=profile,
        providers=providers,
        scout_packs=packs,
        scout_packs_selected=valid_selected,
        recommended_actions=_recommended_actions(resolved_repo, providers),
        safety_notes=[
            "repo profile stays local",
            "setup never writes secrets",
            "setup never installs tools",
            "repo exports are explicit and default off",
        ],
    )


def detect_providers(
    *,
    ollama_url: str = "http://localhost:11434",
    ollama_timeout_s: float = 0.4,
) -> list[ProviderStatus]:
    """Detect available execution/model providers without reading credentials."""

    return [
        ProviderStatus(
            name="Local deterministic",
            kind="stub",
            status="found",
            detail="always available for demos, evals, and safe setup",
        ),
        _detect_ollama(ollama_url, ollama_timeout_s),
        _detect_executable("Claude CLI", "claude"),
        _detect_executable("Codex CLI", "codex"),
        _detect_env_key("Anthropic API", "ANTHROPIC_API_KEY"),
        _detect_env_key("OpenAI API", "OPENAI_API_KEY"),
        _detect_env_key("GitHub token", "GITHUB_TOKEN"),
    ]


def diagnostics_to_plain(diagnostics: SetupDiagnostics) -> str:
    """Render setup diagnostics as stable plain text for non-animated terminals."""

    profile = diagnostics.profile
    lines = [
        "Frontier Scout Mission Control",
        "Try AI tools before you trust them.",
        "",
        f"Repo: {diagnostics.repo}",
        f"Home: {diagnostics.home}",
        "",
        "Repo fingerprint",
        f"- languages: {_join_or(profile.languages, 'unknown')}",
        f"- package managers: {_join_or(profile.package_managers, 'none detected')}",
        f"- frameworks: {_join_or(profile.frameworks, 'none detected')}",
        f"- containers: {_join_or(profile.containers, 'none detected')}",
        f"- ci: {_join_or(profile.ci, 'none detected')}",
        f"- agent configs: {_join_or(profile.agent_configs, 'none detected')}",
        f"- dependencies: {len(profile.dependencies)} detected",
        "",
        "Providers",
    ]
    for provider in diagnostics.providers:
        suffix = f" ({', '.join(provider.models[:4])})" if provider.models else ""
        lines.append(f"- {provider.name}: {provider.status} - {provider.detail}{suffix}")
    evidence = profile.import_evidence
    if evidence.available and (evidence.top_python or evidence.top_javascript):
        lines.extend(["", "Active imports (deterministic, local)"])
        if evidence.top_python:
            top = ", ".join(f"{name}×{count}" for name, count in evidence.top_python[:5])
            lines.append(f"- python: {top}")
        if evidence.top_javascript:
            top = ", ".join(f"{name}×{count}" for name, count in evidence.top_javascript[:5])
            lines.append(f"- javascript: {top}")
        suffix = " (partial)" if evidence.partial else ""
        lines.append(f"- files scanned: {evidence.files_scanned}{suffix}")
    elif not evidence.available:
        lines.extend(["", "Active imports", "- scanner unavailable (tree-sitter not installed)"])
    selected = set(diagnostics.scout_packs_selected)
    lines.extend(["", "Scout packs"])
    for pack in diagnostics.scout_packs:
        marker = "[x]" if pack in selected else "[ ]"
        lines.append(f"- {marker} {pack}")
    lines.extend(["", "Recommended next runs"])
    lines.extend(f"- {action.command} # {action.description}" for action in diagnostics.recommended_actions)
    lines.extend(["", "Safety"])
    lines.extend(f"- {note}" for note in diagnostics.safety_notes)
    return "\n".join(lines) + "\n"


def _detect_ollama(base_url: str, timeout_s: float) -> ProviderStatus:
    tags_url = base_url.rstrip("/") + "/api/tags"
    request = urllib.request.Request(tags_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - localhost/user URL probe.
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        models = [str(item.get("name")) for item in payload.get("models", []) if item.get("name")]
    except (TimeoutError, OSError, urllib.error.URLError):
        return ProviderStatus(
            name="Ollama",
            kind="local-model-runtime",
            status="unavailable",
            detail="not reachable at setup probe URL",
        )
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ProviderStatus(
            name="Ollama",
            kind="local-model-runtime",
            status="error",
            detail="responded, but /api/tags was malformed",
        )
    if not models:
        return ProviderStatus(
            name="Ollama",
            kind="local-model-runtime",
            status="found",
            detail="running with no models listed",
        )
    return ProviderStatus(
        name="Ollama",
        kind="local-model-runtime",
        status="found",
        detail=f"{len(models)} model(s) detected",
        models=models[:8],
    )


def _detect_executable(name: str, executable: str) -> ProviderStatus:
    path = shutil.which(executable)
    if path:
        return ProviderStatus(
            name=name,
            kind="cli",
            status="found",
            detail=f"executable found at {path}",
        )
    return ProviderStatus(name=name, kind="cli", status="missing", detail="not found on PATH")


def _detect_env_key(name: str, env_var: str) -> ProviderStatus:
    if os.environ.get(env_var):
        return ProviderStatus(name=name, kind="api-key", status="present", detail=f"{env_var} is set")
    return ProviderStatus(name=name, kind="api-key", status="missing", detail=f"{env_var} is not set")


def _recommended_actions(repo: Path, providers: list[ProviderStatus]) -> list[RecommendedAction]:
    by_name = {provider.name: provider for provider in providers}
    ollama = by_name.get("Ollama")
    has_ollama = ollama is not None and ollama.status == "found"
    has_api_key = any(
        by_name.get(name) is not None and by_name[name].status == "present"
        for name in ("Anthropic API", "OpenAI API")
    )
    ollama_models = ollama.models if ollama else []

    dry_scan_desc = "Scout seeded AI tools against this repo without live APIs."
    if has_ollama and ollama_models:
        dry_scan_desc += f" Local model available: {ollama_models[0]}."
    evaluate_desc = "Create a first adoption dossier for one tool link."
    if has_api_key:
        evaluate_desc += " API key detected; a live judge pass is available."

    dry_scan = RecommendedAction(
        id="dry_scan",
        label="Dry-run personalized scan",
        command=f"frontier-scout scan --dry-run --repo {repo}",
        description=dry_scan_desc,
    )
    profile = RecommendedAction(
        id="profile",
        label="Profile repo",
        command=f"frontier-scout profile --repo {repo}",
        description="Build the local repo fingerprint used for fit scoring.",
    )
    deps_scan = RecommendedAction(
        id="deps_scan",
        label="Dependency intelligence scan",
        command=f"frontier-scout deps scan --repo {repo}",
        description="Find meaningful hardening/security/compatibility upgrades.",
    )
    evaluate_url = RecommendedAction(
        id="evaluate_url",
        label="Evaluate pasted tool URL",
        command="frontier-scout evaluate <tool-url>",
        description=evaluate_desc,
        requires_input=True,
    )
    if not has_ollama and not has_api_key:
        return [dry_scan, profile, deps_scan, evaluate_url]
    if has_api_key:
        return [dry_scan, evaluate_url, profile, deps_scan]
    return [dry_scan, profile, deps_scan, evaluate_url]


def _join_or(items: list[str], fallback: str) -> str:
    return ", ".join(items) if items else fallback

