# Richer Local Architecture Profile for Scout

Status: draft 2026-06-03 — autonomous (owner away; decisions delegated). Proposed branch: `feat/local-architecture-profile`. Target: next minor (coordinate vs the in-flight v1.7.0 PR #29 at merge time).

## Goal

Make the scout score/verdict/judge passes **more accurate** by feeding the LLM a far richer — but still 100% local, deterministic, **no-source** — picture of the user's repo. The win is mostly *not* new scanning: we already compute a rich profile and then throw most of it away before it reaches the prompt. We close that gap, add resolved dependency versions and a project archetype, and keep the "never sends your source" promise (updated honestly).

This is the design picked after a deep head-to-head between **codegraph** (local/static/deterministic — the right pattern) and **Understand-Anything** (LLM-reads-source — rejected: it breaks the privacy invariant *and* the lean economics, and its semantic value is reproduced for free by Scout's own scoring LLM). We implement codegraph's *pattern* in our existing Python tree-sitter; we do **not** take a TS/Node dependency.

## Problem

The scout prompt's `STACK_PROFILE` block is far thinner than the data we already collect, because of a producer/consumer schema drift:

1. `build_scout_profile` ([profile.py:312](../../../frontier_scout/profile.py)) builds a rich `ScoutProfile`: `languages, frameworks, package_managers, ci, containers, agent_configs, ai_tooling, dependencies` (with an **unused** `resolved_version` field), `risk_flags, adoption_constraints, import_evidence`. AI tooling is already categorised by curated rule tables (`_PY_AI_RULES` etc., [profile.py:187](../../../frontier_scout/profile.py)) into names like `langchain`, `langgraph`, `qdrant`, `pinecone`, `litellm`.
2. `stack_from_profile` ([profile.py:437](../../../frontier_scout/profile.py)) projects that down to `{repo, languages, frameworks(+containers+ci), package_managers, agent_configs, ai_tooling, risk_flags}` — dropping `dependencies` and `import_evidence`.
3. `render_stack_profile` ([prompts.py:287](../../../scripts/prompts.py)) renders only the keys `languages, frameworks, model_providers, stores, agent_runtimes, mcp_servers`. **The last four are phantom keys `stack_from_profile` never produces.** The only keys shared by producer and consumer are `languages` and `frameworks`.

**Net effect:** the live scout/judge prompt currently sees only the user's **languages** and **frameworks**. The AI-tooling categories, package managers, agent configs, dependency versions, and import evidence we already compute never reach the model. That is the accuracy gap.

Also true today (verified):
- `DependencySpec.resolved_version` exists but is populated only for Node (`_read_package_json` → `_read_node_lock_versions`, [profile.py:466](../../../frontier_scout/profile.py)); Python lockfiles (`uv.lock`/`poetry.lock`) are not parsed for resolved versions, and versions are never rendered anyway.
- There is no project **archetype** signal.
- `personalize_verdicts` ([scout.py:92](../../../frontier_scout/scout.py)) *does* read the full `profile.model_dump()` (so local fit-reason annotation already uses `ai_tooling`); the gap is specifically the **prompt** path, not personalization.

## Design

All deterministic, local, read-only. No source bodies leave the machine; the new signals are derived metadata (names, versions, counts, categories, archetype).

### Stream 1 — Close the profile→prompt gap (the core win)

Make the producer (`stack_from_profile`) and consumer (`render_stack_profile`) agree on **one richer schema** that carries what we already compute. `stack_from_profile` keeps its existing keys (backward-compatible for `payload["stack"]` consumers) and gains:
- `ai_categories`: `ai_tooling` grouped into decision-relevant buckets — `llm-sdk`, `agent-framework`, `orchestration`, `vector-store`, `eval`, `gateway`, `inference`, `embeddings`, `other` (grouping map in Stream 4).
- `dependencies`: top-N (by import evidence, then name) as `{name, ecosystem, version}` using `resolved_version or specifier`.
- `top_imports`: a compact per-language top-N from `import_evidence`.
- `archetype` (Stream 3).

`render_stack_profile` is rewritten to render this shared shape (dropping the phantom `model_providers/stores/agent_runtimes/mcp_servers` keys, mapping the real ones): an "ARCHITECTURE BRIEF" sub-section with languages, package managers, frameworks, **AI tooling by category**, **key dependencies with versions**, top imports, agent surfaces, and archetype. Keep the existing `None`/empty stubs verbatim. **Bounded**: cap dependencies (~15) and imports (~8/lang) so the cached block stays small.

### Stream 2 — Resolved dependency versions (Python)

Populate `DependencySpec.resolved_version` for Python from lockfiles, mirroring the Node path. Parse `uv.lock` / `poetry.lock` (TOML `[[package]] name/version`) into a `{name: version}` map and attach to the matching `DependencySpec`. Degrade silently if absent/unparseable. Rendered as "fastapi 0.110.0" (Stream 1).

### Stream 3 — Project archetype (deterministic)

Add `archetype: str = "unknown"` to `ScoutProfile` and a pure function deriving it from frameworks + ai_tooling + manifests + structure into one of: `web-service`, `cli`, `library`, `ml-data`, `agent-app`, `notebook`, `unknown`. Conservative precedence (e.g. web framework present → web-service; `[project.scripts]`/`bin` → cli; packaged lib w/ no app entry → library; notebooks present → notebook; heavy ML/agent imports → ml-data/agent-app). Rendered in the brief.

### Stream 4 — A few more category rules + the grouping map

The rule tables already exist; extend `_PY_AI_RULES` with eval libs (`ragas`, `deepeval`, `braintrust`, `langsmith`, `phoenix`) and gateways (`openrouter`), and add the `_AI_CATEGORY` map from tool-name → bucket used by Stream 1. Small, additive, table-driven.

### Stream 5 — Render into the cached system prompt, secret-scanned

The richer brief lives inside the existing single ephemeral cache block ([prompts.py:358](../../../scripts/prompts.py)) — ~free per scan, cached 5 min. As defense-in-depth, run the existing `SECRET_LEAK_RE` ([lab_runner.py](../../../scripts/lab_runner.py)) over the rendered brief and redact any match (a dependency specifier or path that embeds a token-shaped string gets `‹redacted›`). The block must never carry a secret even by accident.

### Stream 6 — Honest privacy wording

Update the advertised promise to stay accurate: Settings security pane ([panes.py](../../../frontier_scout/tui3/panes.py)) and README. From "Only filenames + AST import names ever leave your machine" → **"Only filenames, dependency manifests/versions, import names, and derived structure ever leave your machine — never your source."** Still a strong, true promise; changed transparently, not silently.

### Stream 7 — Demo artifacts, docs, tests

- Regenerate the deterministic demo artifacts (`frontier-scout demo --no-serve`) so the CI release-preflight `git diff --exit-code -- demo/` stays green (the demo payload carries `profile.model_dump()`).
- Tests: producer/consumer schema agreement (no phantom keys; rich keys present); `render_stack_profile` renders AI categories + versions + archetype and stays bounded; the `None`/empty stubs unchanged; Python lockfile version resolution; archetype heuristic table; secret redaction of the brief; `stack_from_profile` remains backward-compatible (existing keys intact).
- Run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `/opt/miniconda3/bin/python`.

## Non-negotiables

- **No source bodies sent.** Only derived metadata (names, versions, counts, categories, archetype). The tree-sitter pass keeps reading structure, never meaning.
- `.env`/`.env.local`/`.git` and `_SKIP_DIRS` stay excluded; the new lockfile reads touch only manifest/lock files.
- The rendered brief is secret-scanned (`SECRET_LEAK_RE`) and bounded in size.
- The advertised privacy wording is updated to remain literally accurate.
- `stack_from_profile`'s existing keys stay backward-compatible (`payload["stack"]` consumers unaffected).
- `render_stack_profile(None)` / empty-profile stubs are preserved exactly.
- Suite green; demo artifacts regenerated; no new runtime dependency (pure Python, existing tree-sitter).

## Out of scope (YAGNI)

- No LLM-summarised "understanding" pass (Understand-Anything style) — sends source, breaks the invariant and the economics; Scout's own LLM infers semantics from the structural brief for free.
- No bundling of codegraph / any TS/Node tool ("nothing auto-installs"). *Optional future:* opportunistically read a pre-existing local `.codegraph/codegraph.db` (Python `sqlite3`, no Node) if present — noted, not built.
- No function-level call graph — architecture-level signal is the sweet spot for fit-scoring.
- No version bump here unless merge-order with PR #29 requires it (decide at merge).
