"""Static repo risk scanner for the agent adoption firewall.

Enumerates agent-relevant risk surfaces (agent configs, MCP config, CI, deploy
config, secret-likely files, protected paths, build manifests) and detected
test/lint/build checks. Strictly static and read-only:

- Surfaces are detected by **root-level existence checks** (the profiler's walker
  skips dot-dirs, so ``.github``/``.cursor``/``.windsurf`` need explicit checks).
  The secret-file walk reuses the profiler's ``_SKIP_DIRS`` prune set so it never
  descends ``node_modules``/``.venv``/``.git``.
- Secret-likely files are enumerated **by name/path only** — their contents are
  **never opened or read**.

Nothing is executed: no subprocess, no network, no LLM.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from frontier_scout.profile import _SKIP_DIRS

from .models import RiskSurface, ScanResult

__all__ = ["scan_repo"]


# --- Surface tables ----------------------------------------------------------
# Each entry: a repo-relative name that, if it exists, becomes a RiskSurface of
# the given kind. A path is reported under its single most-specific kind only.

_AGENT_CONFIGS: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    ".cursorrules",
    ".cursor",
    ".windsurf",
    ".claude",
    ".codex",
    ".gemini",
    ".github/copilot-instructions.md",
)

_MCP_CONFIGS: tuple[str, ...] = (
    ".mcp.json",
    "mcp.json",
    ".vscode/mcp.json",
)

_CI_PATHS: tuple[str, ...] = (
    ".github/workflows",
    ".gitlab-ci.yml",
    "bitbucket-pipelines.yml",
    "Jenkinsfile",
    "circle.yml",
    ".circleci",
    "buildspec.yml",
    "azure-pipelines.yml",
)

_DEPLOY_CONFIGS: tuple[str, ...] = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "serverless.yml",
    "fly.toml",
    "vercel.json",
    "Procfile",
    "k8s",
    "helm",
    "charts",
    "infra",
    "deploy",
)

# Protected directories beyond the CI/deploy/secret surfaces (which are also
# protected). These are sensitive enough that an agent touching them warrants a
# human gate.
_PROTECTED_DIRS: tuple[str, ...] = (
    "migrations",
    "alembic",
    "auth",
    "billing",
    "security",
    "secrets",
    "terraform",
)

_BUILD_MANIFESTS: tuple[str, ...] = (
    "pyproject.toml",
    "package.json",
    "Makefile",
    "requirements.txt",
)

# Secret-likely files matched by NAME/PATH only — contents are never opened.
# fnmatch globs evaluated against each entry's bare name during a bounded scan.
_SECRET_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_dsa",
    "credentials*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "*.p12",
    "service-account*.json",
)

_SECRET_SCAN_DEPTH = 2


# --- Helpers -----------------------------------------------------------------


def _matches_secret(name: str) -> bool:
    """True if ``name`` looks like a secret-bearing file (by name only)."""

    return any(fnmatch.fnmatch(name, pat) for pat in _SECRET_GLOBS)


def _find_secret_paths(repo: Path) -> list[str]:
    """Enumerate secret-likely files by name within ``repo`` to depth 2.

    Uses ``os.scandir`` and prunes ``_SKIP_DIRS`` and dot-directories below the
    root. **Never opens or reads file contents.** Tolerant of ``OSError``.
    """

    found: list[str] = []

    def walk(current: Path, depth: int) -> None:
        try:
            entries = list(os.scandir(current))
        except OSError:
            return
        for entry in entries:
            name = entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if name in _SKIP_DIRS:
                    continue
                if depth + 1 > _SECRET_SCAN_DEPTH:
                    continue
                # Below the root we mirror the profiler and skip dot-dirs.
                if depth > 0 and name.startswith("."):
                    continue
                walk(Path(entry.path), depth + 1)
                continue
            if _matches_secret(name):
                try:
                    rel = os.path.relpath(entry.path, repo)
                except OSError:
                    rel = name
                found.append(rel.replace(os.sep, "/"))

    walk(repo, 0)
    # Stable, de-duplicated ordering.
    return sorted(set(found))


def _read_text(path: Path) -> str:
    """Best-effort read of a NON-secret manifest. Returns ``""`` on any error."""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _detect_checks(repo: Path) -> list[str]:
    """Derive test/lint/build checks from manifests (non-secret files only)."""

    checks: list[str] = []

    pyproject = repo / "pyproject.toml"
    pyproject_text = _read_text(pyproject) if pyproject.is_file() else ""

    if (
        pyproject.is_file()
        or (repo / "pytest.ini").is_file()
        or (repo / "tox.ini").is_file()
    ):
        checks.append("pytest")

    if "ruff" in pyproject_text.lower() or (repo / "ruff.toml").is_file():
        checks.append("ruff check .")

    package_json = repo / "package.json"
    if package_json.is_file():
        text = _read_text(package_json).lower()
        # Cheap, dependency-free heuristic: a "test" script key under "scripts".
        if '"scripts"' in text and '"test"' in text:
            checks.append("npm test")

    makefile = repo / "Makefile"
    if makefile.is_file():
        for line in _read_text(makefile).splitlines():
            if line.startswith("test:"):
                checks.append("make test")
                break

    # Preserve first-seen order, drop duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for check in checks:
        if check not in seen:
            seen.add(check)
            ordered.append(check)
    return ordered


def _exists(repo: Path, name: str) -> bool:
    """True if a repo-relative ``name`` exists (file or dir). Tolerant."""

    try:
        return (repo / name).exists()
    except OSError:
        return False


# --- Scanner -----------------------------------------------------------------


def scan_repo(repo: str) -> ScanResult:
    """Statically scan ``repo`` for agent-relevant risk surfaces.

    Read-only and offline. Returns a :class:`ScanResult`. Never raises on a
    single bad path (``OSError`` is swallowed per surface).
    """

    repo_path = Path(repo)

    surfaces: list[RiskSurface] = []
    claimed: set[str] = set()  # paths already reported (most-specific kind wins)

    def add(
        path: str,
        kind: str,
        risk: str,
        reason: str,
        policy_implication: str,
        suggested_checks: list[str] | None = None,
    ) -> None:
        if path in claimed:
            return
        claimed.add(path)
        surfaces.append(
            RiskSurface(
                path=path,
                kind=kind,
                risk=risk,  # type: ignore[arg-type]
                reason=reason,
                policy_implication=policy_implication,
                suggested_checks=list(suggested_checks or []),
            )
        )

    # 1. Secret-likely files (name/path only — never read). Reported first so
    #    they claim their paths under the most sensitive kind.
    for rel in _find_secret_paths(repo_path):
        add(
            rel,
            "secret-likely",
            "high",
            "Secret-bearing file detected by name (contents never read).",
            "Never allow agents to read or modify; add to protected_file_globs "
            "and blocked surfaces.",
        )

    # 2. CI configuration.
    for name in _CI_PATHS:
        if _exists(repo_path, name):
            add(
                name,
                "ci",
                "high",
                "CI/CD configuration controls builds, releases, and secrets.",
                "Gate agent changes to CI behind human approval; "
                "add to protected_file_globs.",
                ["pytest"],
            )

    # 3. Deploy / infrastructure configuration.
    for name in _DEPLOY_CONFIGS:
        if _exists(repo_path, name):
            add(
                name,
                "deploy-config",
                "high",
                "Deploy/infra config can ship code or change running systems.",
                "Gate agent changes behind human approval; "
                "add to protected_file_globs.",
            )

    # 4. Protected directories (migrations, auth, billing, security, ...).
    for name in _PROTECTED_DIRS:
        if _exists(repo_path, name):
            add(
                name,
                "protected-path",
                "high",
                "Sensitive area (data migrations, auth, billing, or secrets).",
                "Require human approval for agent edits; "
                "add to protected_file_globs.",
            )

    # 5. MCP configuration.
    for name in _MCP_CONFIGS:
        if _exists(repo_path, name):
            add(
                name,
                "mcp-config",
                "medium",
                "Declares MCP servers an agent may connect to.",
                "Review server capabilities; keep mcp_server_allowlist "
                "deny-by-default.",
            )

    # 6. Agent configuration / instruction files.
    for name in _AGENT_CONFIGS:
        if _exists(repo_path, name):
            add(
                name,
                "agent-config",
                "info",
                "Agent instruction/config file shapes assistant behavior.",
                "Document the policy here; review for over-broad instructions.",
            )

    # 7. Build manifests.
    for name in _BUILD_MANIFESTS:
        if _exists(repo_path, name):
            add(
                name,
                "build-manifest",
                "info",
                "Build/dependency manifest defines tooling and checks.",
                "Source detected checks (tests/lint) into required_checks.",
            )

    detected_checks = _detect_checks(repo_path)

    counts: dict[str, int] = {}
    for surface in surfaces:
        counts[surface.risk] = counts.get(surface.risk, 0) + 1

    return ScanResult(
        repo=repo,
        surfaces=surfaces,
        detected_checks=detected_checks,
        counts=counts,
        static_only=True,
    )
