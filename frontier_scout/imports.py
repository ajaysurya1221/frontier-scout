"""Local-only import-evidence scanner.

Uses tree-sitter to parse Python and JavaScript/TypeScript source files
and count how many files import each top-level package. Deterministic,
read-only, no LLM, no network. Bounded for predictable latency on large
repositories.

The scanner reads source *structure*, never source *meaning*; it produces
counts of import statements, nothing else. If tree-sitter is unavailable
on the host, ``scan_imports`` returns an empty ``ImportEvidence(available=False)``
so callers can degrade gracefully without raising.
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Stdlib modules at import time. ``sys.stdlib_module_names`` is exhaustive and
# accurate for the running interpreter. Adoption signals come from third-party
# imports, so we drop these before counting.
_PY_STDLIB: frozenset[str] = frozenset(sys.stdlib_module_names) | frozenset(
    {"__future__", "builtins"}
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

_PY_EXTS = frozenset({".py"})
_TS_EXTS = frozenset({".ts"})
_TSX_EXTS = frozenset({".tsx"})
_JS_EXTS = frozenset({".js", ".jsx", ".mjs", ".cjs"})

_MAX_FILE_BYTES = 1_000_000  # 1 MB per source file


class ImportEvidence(BaseModel):
    """Per-package import counts gathered from local source files."""

    python_imports: dict[str, int] = Field(default_factory=dict)
    js_imports: dict[str, int] = Field(default_factory=dict)
    files_scanned: int = 0
    files_skipped: int = 0
    errors: int = 0
    partial: bool = False
    available: bool = True


def scan_imports(
    repo: Path,
    *,
    max_files: int = 800,
    max_depth: int = 6,
    time_budget_s: float = 5.0,
) -> ImportEvidence:
    """Walk the repo and return per-package import counts.

    Returns ``ImportEvidence(available=False)`` if tree-sitter or the
    language pack is missing on the host. Never raises.
    """

    try:
        from tree_sitter_language_pack import get_parser
    except Exception:
        return ImportEvidence(available=False)

    try:
        py_parser = get_parser("python")
        ts_parser = get_parser("typescript")
        tsx_parser = get_parser("tsx")
        js_parser = get_parser("javascript")
    except Exception:
        return ImportEvidence(available=False)

    py_counts: Counter[str] = Counter()
    js_counts: Counter[str] = Counter()
    files_scanned = 0
    files_skipped = 0
    errors = 0
    partial = False

    candidates = _collect_source_files(repo, max_depth=max_depth)
    # Most recently modified first — bias the budget toward fresh code.
    candidates.sort(key=lambda item: item[1], reverse=True)
    candidates = candidates[:max_files]

    start = time.monotonic()
    for path, _mtime in candidates:
        if time.monotonic() - start > time_budget_s:
            partial = True
            break
        try:
            size = path.stat().st_size
        except OSError:
            files_skipped += 1
            continue
        if size > _MAX_FILE_BYTES:
            files_skipped += 1
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            files_skipped += 1
            continue
        ext = path.suffix.lower()
        try:
            if ext in _PY_EXTS:
                for pkg in _extract_python(py_parser, text):
                    if pkg in _PY_STDLIB:
                        continue
                    py_counts[pkg] += 1
            elif ext in _TS_EXTS:
                for pkg in _extract_js(ts_parser, text):
                    js_counts[pkg] += 1
            elif ext in _TSX_EXTS:
                for pkg in _extract_js(tsx_parser, text):
                    js_counts[pkg] += 1
            elif ext in _JS_EXTS:
                for pkg in _extract_js(js_parser, text):
                    js_counts[pkg] += 1
            files_scanned += 1
        except Exception:
            errors += 1

    return ImportEvidence(
        python_imports=dict(py_counts),
        js_imports=dict(js_counts),
        files_scanned=files_scanned,
        files_skipped=files_skipped,
        errors=errors,
        partial=partial,
        available=True,
    )


def _collect_source_files(repo: Path, *, max_depth: int) -> list[tuple[Path, float]]:
    """Return ``[(path, mtime)]`` for source files within ``max_depth`` of repo,
    skipping caches, VCS directories, and nested dot-directories."""

    results: list[tuple[Path, float]] = []

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(current))
        except (OSError, PermissionError):
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
                # Skip dot-directories except at the repo root itself.
                if name.startswith("."):
                    continue
                walk(Path(entry.path), depth + 1)
                continue
            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if not is_file:
                continue
            p = Path(entry.path)
            ext = p.suffix.lower()
            if ext in _PY_EXTS or ext in _JS_EXTS or ext in _TS_EXTS or ext in _TSX_EXTS:
                try:
                    st = entry.stat(follow_symlinks=False)
                    results.append((p, st.st_mtime))
                except OSError:
                    continue

    walk(repo, 0)
    return results


def _extract_python(parser: Any, text: str) -> set[str]:
    """Return the set of top-level packages imported by this Python source."""

    pkgs: set[str] = set()
    try:
        tree = parser.parse(text)
    except Exception:
        return pkgs
    src_bytes = text.encode("utf-8", errors="replace")
    root = tree.root_node()

    for node in _walk(root):
        kind = node.kind()
        if kind == "import_statement":
            for i in range(node.child_count()):
                child = node.child(i)
                child_kind = child.kind()
                if child_kind == "dotted_name":
                    name = src_bytes[child.start_byte() : child.end_byte()].decode(errors="replace")
                    top = name.split(".")[0].strip()
                    if top:
                        pkgs.add(top)
                elif child_kind == "aliased_import":
                    # `import foo as bar` - first dotted_name is the real module
                    for j in range(child.child_count()):
                        grand = child.child(j)
                        if grand.kind() == "dotted_name":
                            name = src_bytes[grand.start_byte() : grand.end_byte()].decode(
                                errors="replace"
                            )
                            top = name.split(".")[0].strip()
                            if top:
                                pkgs.add(top)
                            break
        elif kind == "import_from_statement":
            # `from foo.bar import baz` — take 'foo'. Skip relative `from . import x`.
            for i in range(node.child_count()):
                child = node.child(i)
                child_kind = child.kind()
                if child_kind == "dotted_name":
                    name = src_bytes[child.start_byte() : child.end_byte()].decode(errors="replace")
                    top = name.split(".")[0].strip()
                    if top:
                        pkgs.add(top)
                    break
                if child_kind in ("relative_import", "import_prefix"):
                    # `from . import x` — no top-level package to record.
                    break
    return pkgs


def _extract_js(parser: Any, text: str) -> set[str]:
    """Return the set of packages imported by this JS/TS source.

    Captures ES module ``import ... from "pkg"`` and CommonJS ``require("pkg")``.
    Strips relative imports (``./foo``, ``../bar``, ``/abs``) and preserves
    scoped package names (``@scope/name``).
    """

    pkgs: set[str] = set()
    try:
        tree = parser.parse(text)
    except Exception:
        return pkgs
    src_bytes = text.encode("utf-8", errors="replace")
    root = tree.root_node()

    for node in _walk(root):
        kind = node.kind()
        if kind == "import_statement":
            for i in range(node.child_count()):
                child = node.child(i)
                if child.kind() == "string":
                    raw = src_bytes[child.start_byte() : child.end_byte()].decode(errors="replace")
                    pkg = _js_package_from_source(raw)
                    if pkg:
                        pkgs.add(pkg)
        elif kind == "call_expression" and node.child_count() >= 2:
            fn = node.child(0)
            args = node.child(1)
            fn_text = src_bytes[fn.start_byte() : fn.end_byte()].decode(errors="replace")
            if fn_text in ("require", "import"):
                for j in range(args.child_count()):
                    arg_child = args.child(j)
                    if arg_child.kind() == "string":
                        raw = src_bytes[arg_child.start_byte() : arg_child.end_byte()].decode(
                            errors="replace"
                        )
                        pkg = _js_package_from_source(raw)
                        if pkg:
                            pkgs.add(pkg)
    return pkgs


def _js_package_from_source(quoted: str) -> str | None:
    """Strip quotes; reject relative paths; return package name (scoped or unscoped)."""

    src = quoted.strip().strip("'\"`")
    if not src or src.startswith(("./", "../", "/")):
        return None
    if src.startswith("@"):
        parts = src.split("/", 2)
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return src
    return src.split("/", 1)[0]


def _walk(node: Any):
    yield node
    for i in range(node.child_count()):
        yield from _walk(node.child(i))
