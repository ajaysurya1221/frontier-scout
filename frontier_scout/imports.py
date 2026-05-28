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
_GO_EXTS = frozenset({".go"})
_RUST_EXTS = frozenset({".rs"})
_RUBY_EXTS = frozenset({".rb"})

_MAX_FILE_BYTES = 1_000_000  # 1 MB per source file

# Curated stdlib skiplists for the new languages. Small on purpose — the goal
# is to drop the noisiest names, not be exhaustive.
_GO_STDLIB: frozenset[str] = frozenset(
    {
        "fmt", "os", "io", "net", "time", "strings", "strconv", "errors", "context",
        "bytes", "bufio", "encoding", "encoding/json", "encoding/xml", "encoding/base64",
        "log", "log/slog", "math", "math/rand", "path", "path/filepath",
        "regexp", "sort", "sync", "sync/atomic", "testing", "unicode", "unicode/utf8",
        "runtime", "reflect", "embed", "flag", "go", "internal", "plugin",
        "database/sql", "html", "html/template", "text/template", "net/http",
        "net/url", "crypto", "crypto/rand", "crypto/sha256", "crypto/tls",
    }
)
_RUST_STDLIB: frozenset[str] = frozenset({"std", "core", "alloc", "self", "super", "crate"})
_RUBY_STDLIB: frozenset[str] = frozenset(
    {
        "json", "yaml", "uri", "net/http", "openssl", "digest", "base64", "csv",
        "tempfile", "fileutils", "pathname", "logger", "set", "date", "time",
        "securerandom", "ostruct", "open3", "etc", "io", "stringio",
    }
)


class ImportEvidence(BaseModel):
    """Per-package import counts gathered from local source files."""

    python_imports: dict[str, int] = Field(default_factory=dict)
    js_imports: dict[str, int] = Field(default_factory=dict)
    go_imports: dict[str, int] = Field(default_factory=dict)
    rust_imports: dict[str, int] = Field(default_factory=dict)
    ruby_imports: dict[str, int] = Field(default_factory=dict)
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

    # Optional language parsers — degrade gracefully if a single grammar fails to load.
    go_parser = _try_parser("go")
    rust_parser = _try_parser("rust")
    ruby_parser = _try_parser("ruby")

    py_counts: Counter[str] = Counter()
    js_counts: Counter[str] = Counter()
    go_counts: Counter[str] = Counter()
    rust_counts: Counter[str] = Counter()
    ruby_counts: Counter[str] = Counter()
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
            elif ext in _GO_EXTS and go_parser is not None:
                for pkg in _extract_go(go_parser, text):
                    if pkg in _GO_STDLIB or pkg.split("/", 1)[0] in _GO_STDLIB:
                        continue
                    go_counts[pkg] += 1
            elif ext in _RUST_EXTS and rust_parser is not None:
                for pkg in _extract_rust(rust_parser, text):
                    if pkg in _RUST_STDLIB:
                        continue
                    rust_counts[pkg] += 1
            elif ext in _RUBY_EXTS and ruby_parser is not None:
                for pkg in _extract_ruby(ruby_parser, text):
                    if pkg in _RUBY_STDLIB:
                        continue
                    ruby_counts[pkg] += 1
            files_scanned += 1
        except Exception:
            errors += 1

    return ImportEvidence(
        python_imports=dict(py_counts),
        js_imports=dict(js_counts),
        go_imports=dict(go_counts),
        rust_imports=dict(rust_counts),
        ruby_imports=dict(ruby_counts),
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
            if (
                ext in _PY_EXTS
                or ext in _JS_EXTS
                or ext in _TS_EXTS
                or ext in _TSX_EXTS
                or ext in _GO_EXTS
                or ext in _RUST_EXTS
                or ext in _RUBY_EXTS
            ):
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


def _try_parser(language: str) -> Any | None:
    try:
        from tree_sitter_language_pack import get_parser  # type: ignore

        return get_parser(language)
    except Exception:
        return None


def _extract_go(parser: Any, text: str) -> set[str]:
    """Return imported Go package paths. Take the full module path; the
    caller filters stdlib via the top-level segment."""

    pkgs: set[str] = set()
    try:
        tree = parser.parse(text)
    except Exception:
        return pkgs
    src_bytes = text.encode("utf-8", errors="replace")
    root = tree.root_node()
    for node in _walk(root):
        kind = node.kind()
        if kind != "import_spec":
            continue
        for i in range(node.child_count()):
            child = node.child(i)
            if child.kind() == "interpreted_string_literal":
                raw = src_bytes[child.start_byte() : child.end_byte()].decode(errors="replace")
                path = raw.strip().strip('"').strip()
                if path:
                    pkgs.add(path)
                break
    return pkgs


def _extract_rust(parser: Any, text: str) -> set[str]:
    """Return crate roots from ``use`` declarations."""

    pkgs: set[str] = set()
    try:
        tree = parser.parse(text)
    except Exception:
        return pkgs
    src_bytes = text.encode("utf-8", errors="replace")
    root = tree.root_node()
    for node in _walk(root):
        if node.kind() != "use_declaration":
            continue
        crate = _rust_crate_root(node, src_bytes)
        if crate:
            pkgs.add(crate)
    return pkgs


def _rust_crate_root(use_node: Any, src_bytes: bytes) -> str | None:
    """Walk down a ``use_declaration`` to find the leftmost identifier."""

    cur = use_node
    while cur is not None and cur.child_count() > 0:
        argument = None
        for i in range(cur.child_count()):
            child = cur.child(i)
            if child.kind() in ("scoped_identifier", "scoped_use_list", "use_as_clause", "identifier"):
                argument = child
                break
        if argument is None:
            break
        if argument.kind() == "identifier":
            return src_bytes[argument.start_byte() : argument.end_byte()].decode(errors="replace")
        # Recurse: scoped_identifier/scoped_use_list have a 'path' child of the same family.
        cur = argument
    return None


def _extract_ruby(parser: Any, text: str) -> set[str]:
    """Return the string arg of ``require`` / ``require_relative`` calls."""

    pkgs: set[str] = set()
    try:
        tree = parser.parse(text)
    except Exception:
        return pkgs
    src_bytes = text.encode("utf-8", errors="replace")
    root = tree.root_node()
    for node in _walk(root):
        if node.kind() != "call":
            continue
        method_name = None
        args_node = None
        for i in range(node.child_count()):
            child = node.child(i)
            if child.kind() == "identifier" and method_name is None:
                method_name = src_bytes[child.start_byte() : child.end_byte()].decode(errors="replace")
            elif child.kind() == "argument_list":
                args_node = child
        if method_name not in ("require", "require_relative"):
            continue
        if method_name == "require_relative":
            continue  # local path, not a package
        if args_node is None:
            continue
        for j in range(args_node.child_count()):
            arg = args_node.child(j)
            if arg.kind() == "string":
                for k in range(arg.child_count()):
                    content = arg.child(k)
                    if content.kind() == "string_content":
                        raw = src_bytes[content.start_byte() : content.end_byte()].decode(errors="replace")
                        if raw:
                            pkgs.add(raw)
                        break
                break
    return pkgs
