"""Tests for the deterministic, local-only import-evidence scanner."""

from __future__ import annotations

from pathlib import Path

from frontier_scout.imports import ImportEvidence, scan_imports


def _seed_python_monorepo(root: Path) -> None:
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "import langchain_core.messages\n"
        "from .helpers import x\n"
    )
    (root / "backend" / "app" / "util.py").write_text(
        "import pydantic\n"
        "from anthropic import Anthropic\n"
    )


def test_python_imports_top_level_packages(tmp_path):
    _seed_python_monorepo(tmp_path)
    ev = scan_imports(tmp_path)
    assert ev.available is True
    assert ev.python_imports.get("fastapi") == 1
    assert ev.python_imports.get("langchain_core") == 1
    assert ev.python_imports.get("pydantic") == 1
    assert ev.python_imports.get("anthropic") == 1
    # Relative `from .helpers` should not introduce a top-level package.
    assert "helpers" not in ev.python_imports


def test_python_stdlib_modules_are_filtered(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "noise.py").write_text(
        "import json\n"
        "import pathlib\n"
        "from typing import Any\n"
        "import requests\n"
    )
    ev = scan_imports(tmp_path)
    assert "json" not in ev.python_imports
    assert "pathlib" not in ev.python_imports
    assert "typing" not in ev.python_imports
    assert ev.python_imports.get("requests") == 1


def test_typescript_imports_keep_scoped_packages(tmp_path):
    (tmp_path / "web" / "src").mkdir(parents=True)
    (tmp_path / "web" / "src" / "index.ts").write_text(
        "import { Server } from \"@modelcontextprotocol/sdk\";\n"
        "import React from \"react\";\n"
        "import * as foo from \"./util\";\n"
    )
    (tmp_path / "web" / "src" / "service.ts").write_text(
        "const express = require(\"express\");\n"
        "const local = require(\"./helpers\");\n"
    )
    ev = scan_imports(tmp_path)
    assert ev.js_imports.get("@modelcontextprotocol/sdk") == 1
    assert ev.js_imports.get("react") == 1
    assert ev.js_imports.get("express") == 1
    # Relative paths must not produce package names.
    assert "./util" not in ev.js_imports
    assert "./helpers" not in ev.js_imports


def test_node_modules_is_skipped(tmp_path):
    (tmp_path / "node_modules" / "foo").mkdir(parents=True)
    (tmp_path / "node_modules" / "foo" / "bar.py").write_text("import langchain\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.py").write_text("import pydantic\n")
    ev = scan_imports(tmp_path)
    assert "langchain" not in ev.python_imports
    assert ev.python_imports.get("pydantic") == 1


def test_dot_directories_are_skipped_below_root(tmp_path):
    # .scratch at depth 1 must be skipped, src at depth 1 must be scanned.
    (tmp_path / ".scratch" / "x").mkdir(parents=True)
    (tmp_path / ".scratch" / "x" / "noise.py").write_text("import openai\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.py").write_text("import anthropic\n")
    ev = scan_imports(tmp_path)
    assert "openai" not in ev.python_imports
    assert ev.python_imports.get("anthropic") == 1


def test_scanner_gracefully_handles_missing_tree_sitter(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise ImportError("tree_sitter_language_pack not installed")

    monkeypatch.setattr(
        "frontier_scout.imports.scan_imports",
        scan_imports,
    )
    # We simulate the missing dep by patching the language pack import inside
    # the scanner's lazy block. The simplest way is to monkeypatch sys.modules.
    import sys as _sys

    original = _sys.modules.get("tree_sitter_language_pack")
    _sys.modules["tree_sitter_language_pack"] = None  # type: ignore[assignment]
    try:
        (tmp_path / "x.py").write_text("import openai\n")
        ev = scan_imports(tmp_path)
    finally:
        if original is not None:
            _sys.modules["tree_sitter_language_pack"] = original
        else:
            _sys.modules.pop("tree_sitter_language_pack", None)
    assert isinstance(ev, ImportEvidence)
    assert ev.available is False
    assert ev.python_imports == {}


def test_oversized_files_are_skipped(tmp_path, monkeypatch):
    (tmp_path / "huge.py").write_text("import openai\n" + ("# pad\n" * 10))
    monkeypatch.setattr("frontier_scout.imports._MAX_FILE_BYTES", 1)
    ev = scan_imports(tmp_path)
    assert ev.files_skipped >= 1
    assert "openai" not in ev.python_imports


def test_aliased_python_import_is_recorded(tmp_path):
    (tmp_path / "x.py").write_text("import numpy as np\n")
    ev = scan_imports(tmp_path)
    assert ev.python_imports.get("numpy") == 1
