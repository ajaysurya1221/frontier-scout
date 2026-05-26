"""Dependency-upgrade trial receipts that never mutate the working tree."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .store import (
    create_trial_run,
    finish_trial_run,
    home_dir,
    save_lab_result,
    upsert_tool,
)


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
        mutated.append(str(_rewrite_manifest(manifest, package, from_version, to_version).relative_to(temp_dir)))
    status = "skipped" if dry_run else "completed"
    result = {
        "runtime": "dependency-trial",
        "status": status,
        "exit_code": 0,
        "duration_s": 0,
        "cost_usd": 0,
        "transcript_path": None,
        "summary": (
            "Dry-run temp manifest trial; no subprocess executed and the working tree was not mutated."
            if dry_run
            else f"Prepared temp manifest trial for `{test_command or _default_test_command(repo)}`."
        ),
        "temp_dir": str(temp_dir),
        "mutated_manifests": mutated,
    }
    save_lab_result(trial_id, result)
    finish_trial_run(trial_id, status=status, decision="trial")
    receipt_path = _receipt_path(package, from_version, to_version)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(_render_receipt(package, from_version, to_version, repo, result))
    if not dry_run:
        shutil.rmtree(temp_dir, ignore_errors=True)
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
