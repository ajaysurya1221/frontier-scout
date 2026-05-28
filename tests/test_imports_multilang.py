"""Tests for Go / Rust / Ruby import-evidence extraction."""

from __future__ import annotations

from pathlib import Path

from frontier_scout.imports import scan_imports


def test_go_imports_extracted(tmp_path):
    (tmp_path / "main.go").write_text(
        'package main\n'
        'import (\n'
        '  "fmt"\n'
        '  "github.com/gin-gonic/gin"\n'
        '  "github.com/google/uuid"\n'
        ')\n'
        'import "os"\n'
    )
    ev = scan_imports(tmp_path)
    # fmt and os are stdlib and must be filtered.
    assert "fmt" not in ev.go_imports
    assert "os" not in ev.go_imports
    assert ev.go_imports.get("github.com/gin-gonic/gin") == 1
    assert ev.go_imports.get("github.com/google/uuid") == 1


def test_rust_imports_extracted(tmp_path):
    (tmp_path / "lib.rs").write_text(
        'use std::io;\n'
        'use tokio::net::TcpStream;\n'
        'use serde::Serialize;\n'
        'use anyhow::Result;\n'
    )
    ev = scan_imports(tmp_path)
    assert "std" not in ev.rust_imports
    assert ev.rust_imports.get("tokio") == 1
    assert ev.rust_imports.get("serde") == 1
    assert ev.rust_imports.get("anyhow") == 1


def test_ruby_imports_extracted(tmp_path):
    (tmp_path / "app.rb").write_text(
        'require "sinatra"\n'
        'require "langchainrb"\n'
        'require_relative "./helpers"\n'
        'require "json"\n'
    )
    ev = scan_imports(tmp_path)
    # json is stdlib (filtered); require_relative is skipped entirely.
    assert "json" not in ev.ruby_imports
    assert "./helpers" not in ev.ruby_imports
    assert ev.ruby_imports.get("sinatra") == 1
    assert ev.ruby_imports.get("langchainrb") == 1


def test_profile_rules_apply_for_multilang(tmp_path):
    """End-to-end: a polyglot repo gets framework/ai_tooling tags from each language."""

    from frontier_scout.profile import build_scout_profile

    (tmp_path / "main.go").write_text(
        'package main\nimport "github.com/gin-gonic/gin"\n'
    )
    (tmp_path / "lib.rs").write_text('use tokio::net::TcpStream;\n')
    (tmp_path / "app.rb").write_text('require "rails"\n')
    profile = build_scout_profile(tmp_path)
    assert "gin" in profile.frameworks
    assert "tokio" in profile.frameworks
    assert "rails" in profile.frameworks
