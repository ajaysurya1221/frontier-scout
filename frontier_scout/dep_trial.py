"""Dependency-upgrade trial receipts that never mutate the working tree.

v1.2.1 — Codex finding #6: before this change, every non-dry-run trial
reported ``status = "completed"`` and ``exit_code = 0`` even though no
test subprocess ever ran. That meant the receipts were lying: a
receipt could say "completed" for a trial that did literally nothing
beyond rewriting a temp file.

Now the status tells the truth:

- ``dry_run=True`` → ``status = "prepared"`` (no subprocess attempted).
- ``dry_run=False`` and ``test_command`` resolves to something → execute
  in the temp dir under a hermetic env; ``status`` is ``"passed"`` /
  ``"failed"`` based on exit code.
- ``dry_run=False`` and no command resolves → ``status = "prepared"``
  and the summary says so.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .store import (
    create_trial_run,
    finish_trial_run,
    home_dir,
    save_lab_result,
    upsert_tool,
)


def _trial_env(temp_dir: Path) -> dict[str, str]:
    """Hermetic env for the test subprocess.

    We mirror ``scripts/lab_runner._neutralised_env`` rather than
    import it (importing ``scripts.*`` from the installed package is
    fragile across editable/wheel installs). The shape is identical:
    real HOME hidden, pip/npm/HF user config neutralised, no secrets
    propagated.
    """

    env = {
        "HOME": str(temp_dir),
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "TMPDIR": str(temp_dir),
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_INDEX_URL": os.environ.get("LAB_PIP_INDEX_URL", ""),
        "PIP_EXTRA_INDEX_URL": "",
        "PIP_NO_INPUT": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "HF_HOME": str(temp_dir / "hf"),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "npm_config_userconfig": os.devnull,
        "npm_config_globalconfig": os.devnull,
        "npm_config_cache": str(temp_dir / "npm"),
        "NO_UPDATE_NOTIFIER": "1",
    }
    return env


def run_dependency_trial(
    package: str,
    *,
    from_version: str,
    to_version: str,
    repo: Path,
    dry_run: bool = False,
    test_command: str | None = None,
) -> dict[str, Any]:
    """Create a dependency-upgrade trial receipt in a temp copy of manifests."""

    repo = repo.resolve()
    tool_id = upsert_tool(package, category="dev_tool", package_name=package)
    trial_id = create_trial_run(
        tool_id,
        requested_action=f"dependency upgrade {package} {from_version} -> {to_version}",
    )
    temp_dir = Path(tempfile.mkdtemp(prefix="frontier-scout-dep-trial-"))
    copied = _copy_manifests(repo, temp_dir)
    mutated = []
    for manifest in copied:
        mutated.append(
            str(
                _rewrite_manifest(manifest, package, from_version, to_version).relative_to(
                    temp_dir
                )
            )
        )

    resolved_command = test_command or _default_test_command(repo)
    transcript_path: Path | None = None
    exit_code = 0
    duration_s = 0
    if dry_run:
        status = "prepared"
        summary = (
            "Dry-run temp manifest trial; no subprocess executed and the "
            "working tree was not mutated."
        )
    elif not resolved_command:
        status = "prepared"
        summary = (
            "No --test-command supplied and no default could be inferred "
            "for this repo. Manifests were rewritten in a temp copy; no "
            "subprocess ran."
        )
    else:
        # Execute the resolved command in the temp dir under hermetic env.
        # We do NOT propagate the user's real env — that would leak API
        # keys and pip/npm user config into the trial.
        transcript_path = temp_dir / "transcript.log"
        env = _trial_env(temp_dir)
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 — explicit command, hermetic env
                shlex.split(resolved_command),
                cwd=str(temp_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            exit_code = completed.returncode
            transcript_path.write_text(
                f"$ {resolved_command}\n\n"
                f"--- stdout ---\n{completed.stdout}\n"
                f"--- stderr ---\n{completed.stderr}\n"
            )
            status = "passed" if exit_code == 0 else "failed"
            summary = (
                f"Executed `{resolved_command}` in hermetic temp dir; "
                f"exit code {exit_code}."
            )
        except FileNotFoundError as exc:
            status = "failed"
            exit_code = 127
            summary = f"Test command not found: {exc}"
            transcript_path.write_text(f"$ {resolved_command}\n\nFileNotFoundError: {exc}\n")
        except subprocess.TimeoutExpired:
            status = "failed"
            exit_code = 124
            summary = f"`{resolved_command}` timed out after 600s."
            transcript_path.write_text(f"$ {resolved_command}\n\nTimeoutExpired (600s)\n")
        duration_s = int(time.monotonic() - started)

    result = {
        "runtime": "dependency-trial",
        "status": status,
        "exit_code": exit_code,
        "duration_s": duration_s,
        "cost_usd": 0,
        "transcript_path": str(transcript_path) if transcript_path else None,
        "summary": summary,
        "temp_dir": str(temp_dir),
        "mutated_manifests": mutated,
        "test_command": resolved_command,
    }
    save_lab_result(trial_id, result)
    finish_trial_run(trial_id, status=status, decision="trial")
    receipt_path = _receipt_path(package, from_version, to_version)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(_render_receipt(package, from_version, to_version, repo, result))
    # Keep the temp dir around for dry-runs (lets the user inspect the
    # diff) and for executed runs (transcript lives there). The caller
    # can clean it up after reading the receipt.
    return {
        "tool_name": package,
        "trial_id": trial_id,
        "from_version": from_version,
        "to_version": to_version,
        "lab_result": result,
        "receipt_path": str(receipt_path),
    }


def _copy_manifests(repo: Path, temp_dir: Path) -> list[Path]:
    manifests = [
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    ]
    copied: list[Path] = []
    for name in manifests:
        source = repo / name
        if not source.exists() or not source.is_file():
            continue
        target = temp_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(errors="ignore"))
        copied.append(target)
    return copied


def _rewrite_manifest(path: Path, package: str, from_version: str, to_version: str) -> Path:
    text = path.read_text(errors="ignore")
    escaped = re.escape(package)
    patterns = [
        (rf"({escaped}\s*==\s*){re.escape(from_version)}", rf"\g<1>{to_version}"),
        (rf'("{re.escape(package)}"\s*:\s*")[^"]+(")', rf"\g<1>{to_version}\2"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    path.write_text(text)
    return path


def _default_test_command(repo: Path) -> str:
    if (repo / "package.json").exists():
        return "npm test"
    return "pytest -q"


def _receipt_path(package: str, from_version: str, to_version: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", package).strip("-").lower() or "dependency"
    return home_dir() / "reports" / "dependency-trials" / f"{slug}-{from_version}-to-{to_version}.md"


def _render_receipt(package: str, from_version: str, to_version: str, repo: Path, result: dict[str, Any]) -> str:
    lines = [
        f"# Dependency trial: {package} {from_version} -> {to_version}",
        "",
        f"Repo: {repo}",
        "Working tree mutated: no",
        f"Status: {result['status']}",
        f"Summary: {result['summary']}",
        "",
        "## Temp artifacts",
        "",
        f"- Temp dir: {result['temp_dir']}",
    ]
    for manifest in result.get("mutated_manifests") or []:
        lines.append(f"- Manifest copy: {manifest}")
    return "\n".join(lines).rstrip() + "\n"
