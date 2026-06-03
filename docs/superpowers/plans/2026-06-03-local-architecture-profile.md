# Richer Local Architecture Profile — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed the scout/judge prompt the rich local profile we already compute (AI-tooling categories, dependency versions, import evidence, project archetype) instead of just `languages`+`frameworks` — deterministic, local, no source sent.

**Architecture:** The defect: `build_scout_profile` builds a rich `ScoutProfile`, but `stack_from_profile` ([profile.py:437](../../../frontier_scout/profile.py)) projects it to a thin dict and `render_stack_profile` ([prompts.py:287](../../../scripts/prompts.py)) renders *phantom keys* the producer never emits, so only `languages`+`frameworks` reach the prompt. We make producer and consumer agree on one richer (backward-compatible) shape, add resolved Python versions + a coarse archetype + AI category grouping, render an "architecture brief", and secret-scan it.

**Tech Stack:** Python 3.11+, Pydantic, `tomllib`, tree-sitter (existing). Run tests with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q` (bare `python` not on PATH; 3 `tests/test_implement.py` failures are pre-existing env-only). Spec: [docs/superpowers/specs/2026-06-03-local-architecture-profile-design.md](../specs/2026-06-03-local-architecture-profile-design.md).

---

## Ground rules

1. **No source bodies sent** — only derived metadata (names, versions, counts, categories, archetype).
2. **Backward-compatible** — `stack_from_profile` keeps every existing key; `render_stack_profile` keeps its `None`/empty stubs and its existing key rows. New work is additive.
3. **Deterministic & bounded** — cap dependencies (15) and imports (8/lang); no new runtime dependency.
4. Commit after each task once its tests pass.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `frontier_scout/profile.py` | Modify | `archetype` field + `derive_archetype`; Python lockfile versions; extra AI rules + `_AI_CATEGORY`/`ai_categories`; enrich `stack_from_profile`. |
| `scripts/prompts.py` | Modify | Rewrite `render_stack_profile` into the architecture brief + `_redact_secrets`. |
| `frontier_scout/tui3/panes.py` | Modify | Update the Settings security-posture wording line. |
| `tests/test_architecture_profile.py` | Create | All new tests (profile + render). |
| `demo/` | Regenerate | Keep CI release-preflight `git diff -- demo/` green. |
| `CHANGELOG.md` | Modify | Unreleased entry (no version bump). |

---

## Task 1: Project archetype

**Files:** Modify `frontier_scout/profile.py`; Test `tests/test_architecture_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_architecture_profile.py
"""Richer local architecture profile — deterministic, no source."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from frontier_scout.profile import ScoutProfile, derive_archetype


def _p(**kw) -> ScoutProfile:
    return ScoutProfile(repo="/x", repo_id="x", **kw)


def test_archetype_web_service():
    assert derive_archetype(_p(frameworks=["fastapi"])) == "web-service"
    assert derive_archetype(_p(frameworks=["next", "react"])) == "web-service"


def test_archetype_agent_app():
    assert derive_archetype(_p(ai_tooling=["langgraph"])) == "agent-app"
    assert derive_archetype(_p(agent_configs=["CLAUDE.md"])) == "agent-app"


def test_archetype_ml_data():
    assert derive_archetype(_p(ai_tooling=["transformers"])) == "ml-data"


def test_archetype_library_and_unknown():
    assert derive_archetype(_p(package_managers=["pip"])) == "library"
    assert derive_archetype(_p()) == "unknown"


def test_archetype_web_beats_agent():
    # a web service that also has a CLAUDE.md is still a web service
    assert derive_archetype(_p(frameworks=["django"], agent_configs=["CLAUDE.md"])) == "web-service"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -q`
Expected: FAIL — `ImportError: cannot import name 'derive_archetype'`.

- [ ] **Step 3: Add the field + function**

In `frontier_scout/profile.py`, add a field to `ScoutProfile` (after `import_evidence`, ~line 63):

```python
    archetype: str = "unknown"
```

Add these module-level tables + function (place after the `_PYPI_IMPORT_ALIAS` block, before `# --- Build profile ---` ~line 308):

```python
_WEB_FRAMEWORKS: frozenset[str] = frozenset({
    "fastapi", "django", "flask", "starlette", "express", "fastify", "nestjs",
    "next", "vue", "svelte", "rails", "sinatra", "rack", "gin", "echo", "fiber",
    "actix-web", "axum", "rocket",
})
_AGENT_TOOLING: frozenset[str] = frozenset({
    "langgraph", "crewai", "autogen", "mcp", "mastra", "langchain", "instructor", "dspy",
})
_ML_TOOLING: frozenset[str] = frozenset({
    "transformers", "sentence-transformers", "vllm", "candle", "rust-bert",
})


def derive_archetype(profile: ScoutProfile) -> str:
    """Coarse, deterministic project archetype from already-collected signals.

    Pure function over the built profile — no extra scanning, no source. Order
    is a precedence: a web service that also ships an agent config is still a
    web service.
    """
    fw = {f.lower() for f in profile.frameworks}
    ai = {a.lower() for a in profile.ai_tooling}
    if fw & _WEB_FRAMEWORKS:
        return "web-service"
    if (ai & _AGENT_TOOLING) or profile.agent_configs:
        return "agent-app"
    if ai & _ML_TOOLING:
        return "ml-data"
    if profile.package_managers:
        return "library"
    return "unknown"
```

Wire it into `build_scout_profile` — set it just before `return profile` (~line 434):

```python
    profile.archetype = derive_archetype(profile)
    return profile
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/profile.py tests/test_architecture_profile.py
git commit -m "feat(profile): deterministic project archetype"
```

---

## Task 2: Python resolved versions from lockfiles

**Files:** Modify `frontier_scout/profile.py`; Test `tests/test_architecture_profile.py`

Node lockfile versions are already read (`_read_node_lock_versions`); Python lockfiles are not. Add a `uv.lock`/`poetry.lock` parser and apply it to PyPI deps.

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_architecture_profile.py
from frontier_scout.profile import build_scout_profile

UV_LOCK = '''
version = 1
[[package]]
name = "fastapi"
version = "0.110.1"
[[package]]
name = "anthropic"
version = "0.39.0"
'''

PYPROJECT = '''
[project]
name = "demo"
dependencies = ["fastapi", "anthropic>=0.3"]
'''


def test_python_lock_versions_resolved(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "uv.lock").write_text(UV_LOCK)
    profile = build_scout_profile(tmp_path, scan_imports=False)
    by_name = {d.name.lower(): d for d in profile.dependencies}
    assert by_name["fastapi"].resolved_version == "0.110.1"
    assert by_name["anthropic"].resolved_version == "0.39.0"


def test_python_lock_absent_is_safe(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    profile = build_scout_profile(tmp_path, scan_imports=False)
    # no lock → resolved_version stays None for non-pinned deps; never raises
    assert {d.name.lower() for d in profile.dependencies} >= {"fastapi", "anthropic"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -k lock -q`
Expected: FAIL — `resolved_version` is `None` (no Python lock parsing yet).

- [ ] **Step 3: Add the parser + apply it**

In `frontier_scout/profile.py`, add this function next to `_read_node_lock_versions` (~line 604):

```python
def _read_python_lock_versions(manifest_dir: Path) -> dict[str, str]:
    """Resolved ``{name(lower): version}`` from uv.lock or poetry.lock.

    Both use a TOML ``[[package]]`` array with ``name``/``version``. Returns
    the first lockfile found; ``{}`` if none / unparseable / no tomllib.
    """
    if tomllib is None:
        return {}
    for lockname in ("uv.lock", "poetry.lock"):
        path = manifest_dir / lockname
        if not path.exists():
            continue
        try:
            data = tomllib.loads(path.read_text(errors="ignore"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        versions: dict[str, str] = {}
        for pkg in data.get("package") or []:
            if isinstance(pkg, dict) and pkg.get("name") and pkg.get("version"):
                versions[str(pkg["name"]).lower()] = str(pkg["version"])
        if versions:
            return versions
    return {}
```

At the end of `_read_python_manifest` (after the weak-signal `for marker ...` loops, ~line 519), apply resolved versions:

```python
    resolved = _read_python_lock_versions(manifest_dir)
    if resolved:
        for dep in profile.dependencies:
            if dep.ecosystem == "pypi" and not dep.resolved_version:
                version = resolved.get(dep.name.lower())
                if version:
                    dep.resolved_version = version
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/profile.py tests/test_architecture_profile.py
git commit -m "feat(profile): resolve Python dependency versions from uv.lock/poetry.lock"
```

---

## Task 3: AI category grouping + extra rules

**Files:** Modify `frontier_scout/profile.py`; Test `tests/test_architecture_profile.py`

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_architecture_profile.py
from frontier_scout.profile import ai_categories


def test_ai_categories_grouping():
    p = _p(ai_tooling=["anthropic", "langgraph", "qdrant", "ragas", "litellm", "weirdthing"])
    cats = ai_categories(p)
    assert cats["llm-sdk"] == ["anthropic"]
    assert cats["agent-framework"] == ["langgraph"]
    assert cats["vector-store"] == ["qdrant"]
    assert cats["eval"] == ["ragas"]
    assert cats["gateway"] == ["litellm"]
    assert cats["other"] == ["weirdthing"]  # unknown tag → "other", never dropped
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -k categories -q`
Expected: FAIL — `cannot import name 'ai_categories'`.

- [ ] **Step 3: Extend the rule table + add the grouping**

In `frontier_scout/profile.py`, add these entries inside `_PY_AI_RULES` (the dict at ~line 187, before its closing `}`):

```python
    "ragas": ("ai_tooling", "ragas"),
    "deepeval": ("ai_tooling", "deepeval"),
    "braintrust": ("ai_tooling", "braintrust"),
    "langsmith": ("ai_tooling", "langsmith"),
    "phoenix": ("ai_tooling", "phoenix"),
    "openrouter": ("ai_tooling", "openrouter"),
```

Add the category map + helper (place right after `_PYPI_IMPORT_ALIAS`, near `derive_archetype` from Task 1):

```python
_AI_CATEGORY: dict[str, str] = {
    "openai": "llm-sdk", "anthropic": "llm-sdk", "google-genai": "llm-sdk",
    "vertex-ai": "llm-sdk", "bedrock-or-aws": "llm-sdk", "vercel-ai-sdk": "llm-sdk",
    "langchain": "orchestration", "llamaindex": "orchestration", "haystack": "orchestration",
    "langgraph": "agent-framework", "crewai": "agent-framework", "autogen": "agent-framework",
    "mastra": "agent-framework", "dspy": "agent-framework", "mcp": "agent-framework",
    "qdrant": "vector-store", "pinecone": "vector-store", "weaviate": "vector-store",
    "chromadb": "vector-store", "neo4j": "vector-store",
    "ragas": "eval", "deepeval": "eval", "braintrust": "eval", "langsmith": "eval",
    "phoenix": "eval",
    "litellm": "gateway", "openrouter": "gateway",
    "vllm": "inference", "ollama": "inference", "candle": "inference",
    "transformers": "ml", "sentence-transformers": "embeddings",
    "instructor": "structured-output",
}


def ai_categories(profile: ScoutProfile) -> dict[str, list[str]]:
    """Group ``ai_tooling`` tags into decision buckets for the scout brief.

    Unknown tags fall into ``"other"`` — never silently dropped.
    """
    buckets: dict[str, list[str]] = {}
    for tag in profile.ai_tooling:
        bucket = _AI_CATEGORY.get(tag.lower(), "other")
        names = buckets.setdefault(bucket, [])
        if tag not in names:
            names.append(tag)
    return buckets
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/profile.py tests/test_architecture_profile.py
git commit -m "feat(profile): group AI tooling into decision categories"
```

---

## Task 4: Enrich `stack_from_profile` (close the gap, producer side)

**Files:** Modify `frontier_scout/profile.py`; Test `tests/test_architecture_profile.py`

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_architecture_profile.py
from frontier_scout.profile import DependencySpec, ImportEvidenceSummary, stack_from_profile


def test_stack_from_profile_carries_rich_signal():
    p = _p(
        languages=["python"],
        frameworks=["fastapi"],
        package_managers=["uv"],
        ai_tooling=["anthropic", "qdrant"],
        agent_configs=["CLAUDE.md"],
    )
    p.archetype = "web-service"
    p.dependencies = [
        DependencySpec(name="fastapi", ecosystem="pypi", resolved_version="0.110.1",
                       manifest_path="pyproject.toml", evidence_imports=12),
        DependencySpec(name="anthropic", ecosystem="pypi", specifier=">=0.3",
                       manifest_path="pyproject.toml", evidence_imports=5),
    ]
    p.import_evidence = ImportEvidenceSummary(top_python=[("anthropic", 5), ("fastapi", 12)])
    stack = stack_from_profile(p)
    # backward-compatible keys still present
    assert stack["languages"] == ["python"]
    assert "fastapi" in stack["frameworks"]
    assert stack["ai_tooling"] == ["anthropic", "qdrant"]
    # new rich keys
    assert stack["archetype"] == "web-service"
    assert stack["ai_categories"]["vector-store"] == ["qdrant"]
    assert {"name": "fastapi", "ecosystem": "pypi", "version": "0.110.1"} in stack["dependencies"]
    assert stack["top_imports"]["python"][:2] == ["fastapi", "anthropic"]  # sorted by count desc


def test_stack_from_profile_bounds_dependencies():
    p = _p()
    p.dependencies = [
        DependencySpec(name=f"dep{i}", ecosystem="pypi", manifest_path="r.txt", evidence_imports=i)
        for i in range(40)
    ]
    assert len(stack_from_profile(p)["dependencies"]) == 15  # capped
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -k stack_from -q`
Expected: FAIL — `KeyError: 'archetype'` (current `stack_from_profile` has no rich keys).

- [ ] **Step 3: Enrich `stack_from_profile`**

Replace `stack_from_profile` (`profile.py:437-448`) with:

```python
def stack_from_profile(profile: ScoutProfile) -> dict[str, Any]:
    """Stack shape used by the prompt (prompts.render_stack_profile) + payload['stack'].

    Backward-compatible: every previously-emitted key is unchanged; richer keys
    are added so the scout prompt can render the architecture brief.
    """
    top_deps = sorted(
        profile.dependencies,
        key=lambda d: (-d.evidence_imports, d.name.lower()),
    )[:15]
    return {
        "repo": profile.repo,
        "languages": profile.languages,
        "frameworks": profile.frameworks + profile.containers + profile.ci,
        "package_managers": profile.package_managers,
        "agent_configs": profile.agent_configs,
        "ai_tooling": profile.ai_tooling,
        "risk_flags": profile.risk_flags,
        # --- richer signal (additive) ---
        "ai_categories": ai_categories(profile),
        "archetype": profile.archetype,
        "dependencies": [
            {
                "name": d.name,
                "ecosystem": d.ecosystem,
                "version": d.resolved_version or d.specifier or "",
            }
            for d in top_deps
        ],
        "top_imports": _top_imports_for_stack(profile.import_evidence),
    }


def _top_imports_for_stack(ev: ImportEvidenceSummary, n: int = 8) -> dict[str, list[str]]:
    """Compact per-language top import names (already sorted by count)."""
    out: dict[str, list[str]] = {}
    for lang, items in (
        ("python", ev.top_python),
        ("javascript", ev.top_javascript),
        ("go", ev.top_go),
        ("rust", ev.top_rust),
        ("ruby", ev.top_ruby),
    ):
        names = [name for name, _count in items[:n]]
        if names:
            out[lang] = names
    return out
```

- [ ] **Step 4: Run the new test + the broader profile suite (backward-compat check)**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py tests/test_profile_dossier.py tests/test_profile_monorepo.py tests/test_packs_dependencies.py -q`
Expected: PASS (existing tests still green — new keys are additive).

- [ ] **Step 5: Commit**

```bash
git add frontier_scout/profile.py tests/test_architecture_profile.py
git commit -m "feat(profile): stack_from_profile carries categories, versions, imports, archetype"
```

---

## Task 5: Render the architecture brief (close the gap, consumer side)

**Files:** Modify `scripts/prompts.py`; Test `tests/test_architecture_profile.py`

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_architecture_profile.py
from prompts import render_stack_profile  # scripts/ is on sys.path (top of file)


def test_render_brief_includes_rich_signal():
    stack = {
        "languages": ["python"],
        "frameworks": ["fastapi"],
        "package_managers": ["uv"],
        "agent_configs": ["CLAUDE.md"],
        "archetype": "web-service",
        "ai_categories": {"llm-sdk": ["anthropic"], "vector-store": ["qdrant"]},
        "dependencies": [{"name": "fastapi", "ecosystem": "pypi", "version": "0.110.1"}],
        "top_imports": {"python": ["fastapi", "anthropic"]},
    }
    out = render_stack_profile(stack)
    assert out.startswith("STACK_PROFILE:")
    assert "Archetype: web-service" in out
    assert "vector-store: qdrant" in out
    assert "fastapi 0.110.1" in out
    assert "Top python imports: fastapi, anthropic" in out


def test_render_none_and_empty_stubs_unchanged():
    assert "STACK_PROFILE: (none)" in render_stack_profile(None)
    assert "STACK_PROFILE: (empty)" in render_stack_profile({})


def test_render_redacts_secret_shaped_value():
    # a dependency name that happens to look like a key must be scrubbed
    stack = {"dependencies": [{"name": "sk-ant-" + "A" * 30, "ecosystem": "pypi", "version": "1"}]}
    out = render_stack_profile(stack)
    assert "sk-ant-" not in out
    assert "‹redacted›" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py -k render -q`
Expected: FAIL — current `render_stack_profile` renders neither archetype/categories/deps nor redacts.

- [ ] **Step 3: Rewrite `render_stack_profile` + add `_redact_secrets`**

Replace `render_stack_profile` (`prompts.py:287-337`) with the version below. Keep the module docstring's `None`/empty stubs **verbatim** (same strings the existing tests/stubs expect):

```python
def render_stack_profile(profile: dict[str, Any] | None) -> str:
    """Render the local architecture profile into a prompt-ready brief.

    ``profile`` is the dict from ``profile.stack_from_profile`` — languages,
    frameworks, package managers, agent surfaces, AI tooling grouped by
    category, key dependencies (name + resolved version), top imports, and a
    coarse archetype. Derived metadata only — never source. ``None``/empty
    produce a clearly-flagged stub so the judge frames verdicts universally.
    """
    if not profile:
        return (
            "STACK_PROFILE: (none)\n"
            "The user has not configured a stack profile. Frame verdicts on "
            "universal merit only — do not invent stack-specific reasoning."
        )

    lines: list[str] = ["STACK_PROFILE:"]

    def _row(label: str, key: str) -> None:
        values = profile.get(key)
        if values:
            lines.append(f"  {label}: {', '.join(str(v) for v in values)}")

    # Backward-compatible rows (older callers may still pass these) + new rows.
    _row("Languages", "languages")
    _row("Frameworks", "frameworks")
    _row("Package managers", "package_managers")
    _row("Model providers", "model_providers")
    _row("Stores", "stores")
    _row("Agent runtimes", "agent_runtimes")
    _row("MCP servers", "mcp_servers")
    _row("Agent surfaces", "agent_configs")

    archetype = profile.get("archetype")
    if archetype and archetype != "unknown":
        lines.append(f"  Archetype: {archetype}")

    cats = profile.get("ai_categories") or {}
    if cats:
        lines.append("  AI tooling already in use:")
        for bucket in sorted(cats):
            names = cats[bucket]
            if names:
                lines.append(f"    - {bucket}: {', '.join(str(n) for n in names)}")

    deps = profile.get("dependencies") or []
    rendered_deps = ", ".join(
        f"{d.get('name')} {d.get('version', '')}".strip()
        for d in deps
        if isinstance(d, dict) and d.get("name")
    )
    if rendered_deps:
        lines.append(f"  Key dependencies: {rendered_deps}")

    imports = profile.get("top_imports") or {}
    for lang in sorted(imports):
        names = imports[lang]
        if names:
            lines.append(f"  Top {lang} imports: {', '.join(str(n) for n in names)}")

    if len(lines) == 1:
        return (
            "STACK_PROFILE: (empty)\n"
            "Profile was configured but contained no entries. Frame verdicts "
            "on universal merit only."
        )
    return _redact_secrets("\n".join(lines))


def _redact_secrets(text: str) -> str:
    """Defense-in-depth: scrub anything secret-shaped from the rendered brief.

    The brief only contains package metadata, so this should never fire — but a
    dependency/path that embeds a token-shaped string must never reach the LLM.
    Reuses the lab's secret pattern; degrades to no-op if unavailable.
    """
    try:
        from lab_runner import SECRET_LEAK_RE
    except Exception:  # noqa: BLE001 — redaction is best-effort defense-in-depth
        return text
    return SECRET_LEAK_RE.sub("‹redacted›", text)
```

- [ ] **Step 4: Run the new test + the prompt-touching suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_architecture_profile.py tests/test_imports_multilang.py tests/test_packs_dependencies.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/prompts.py tests/test_architecture_profile.py
git commit -m "feat(prompts): render the architecture brief (categories, versions, imports, archetype)"
```

---

## Task 6: Honest privacy wording (Settings pane)

**Files:** Modify `frontier_scout/tui3/panes.py`

The README is already accurate ("without reading your source" / "never sends source content"). Only the Settings security pane overstates the narrowness.

- [ ] **Step 1: Update the wording**

In `frontier_scout/tui3/panes.py`, replace the security-posture row (lines 285-286):

```python
        ("Repo source is never sent to an LLM",
         "Only filenames + AST import names ever leave your machine."),
```

with:

```python
        ("Repo source is never sent to an LLM",
         "Only filenames, dependency manifests/versions, import names, and "
         "derived structure ever leave your machine — never your source."),
```

- [ ] **Step 2: Verify the app still imports**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -c "import frontier_scout.tui3.panes; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add frontier_scout/tui3/panes.py
git commit -m "docs(tui): update privacy wording to match the richer (still no-source) profile"
```

---

## Task 7: Finalize — demo artifacts, lint, full suite, changelog

**Files:** Regenerate `demo/`; Modify `CHANGELOG.md`

- [ ] **Step 1: Regenerate the deterministic demo artifacts**

The demo payload carries `profile.model_dump()` + the enriched `stack`, so the committed artifacts drift. Regenerate:

Run: `/opt/miniconda3/bin/frontier-scout demo --no-serve`
Then: `git status --short demo/` — stage and commit whatever changed (expected: `demo/cost-breakdown.md` and/or `demo/briefing.html`/`demo/verdicts.json`). If nothing changed, skip.

- [ ] **Step 2: Lint the changed files**

Run `ruff check` and `black` on the branch's changed Python files (`git diff --name-only main...HEAD | grep '\.py$'`); fix any findings. Restrict `black` to those files (don't reformat files this branch didn't touch).

- [ ] **Step 3: Full suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q`
Expected: green except the 3 known env-only `tests/test_implement.py` failures (they shell out to bare `python`). The `test_tabs.py::test_scout_detail_panel_populates_after_run` test is timing-flaky in the full suite — if it fails, re-run it alone to confirm it passes (`-k test_scout_detail_panel_populates_after_run`); it is unrelated to this change. If anything else fails, STOP and fix.

- [ ] **Step 4: CHANGELOG (no version bump)**

Add an entry under an `## [Unreleased]` heading (create it above the latest version heading if absent): "Richer local architecture profile — the scout/judge prompt now receives AI-tooling categories, resolved dependency versions, top imports, and a project archetype (previously only languages + frameworks reached the prompt due to a producer/consumer schema drift). Deterministic, local, no source sent." Do **not** bump `pyproject.toml`/`__init__.py` (a v1.7.0 bump is already in flight on PR #29; version is reconciled at merge).

- [ ] **Step 5: Commit**

```bash
git add demo/ CHANGELOG.md
git commit -m "chore: regenerate demo + changelog for the architecture profile"
```

---

## Self-review

**Spec coverage:** Stream 1 (close the gap) → Tasks 4+5. Stream 2 (resolved versions) → Task 2. Stream 3 (archetype) → Task 1. Stream 4 (rules + grouping) → Task 3. Stream 5 (render + secret-scan) → Task 5. Stream 6 (wording) → Task 6 (README already accurate — noted). Stream 7 (demo/docs/tests) → Task 7 + tests throughout.

**Type consistency:** `derive_archetype(ScoutProfile)->str`, `ai_categories(ScoutProfile)->dict[str,list[str]]`, `_read_python_lock_versions(Path)->dict[str,str]`, `_top_imports_for_stack(ImportEvidenceSummary,int)->dict[str,list[str]]`, `_redact_secrets(str)->str`, and the `stack_from_profile` keys (`ai_categories/archetype/dependencies/top_imports`) used in Task 4 match what Task 5's renderer reads. `ImportEvidenceSummary.top_python` is `list[tuple[str,int]]` (per [profile.py:37](../../../frontier_scout/profile.py)) — `_top_imports_for_stack` unpacks `(name, _count)` accordingly. `DependencySpec.evidence_imports` exists ([profile.py:31](../../../frontier_scout/profile.py)).

**No placeholders:** every step has complete code + exact commands. The "stage whatever changed" in Task 7 Step 1 is a deterministic regen (no guessing — the engineer commits the regenerated bytes).

**Backward-compat guard:** `stack_from_profile` keeps all prior keys; `render_stack_profile` keeps the `None`/empty stubs verbatim and the old key rows. Task 4 Step 4 and Task 5 Step 4 run the existing profile/prompt suites to catch any regression.
