# Spike A — MCP behavioral-probe feasibility (Phase 0, P0-3)

**Question:** can Frontier Scout's existing sandbox produce *behavioral* evidence for an MCP
server (start it, list its tools, observe capabilities), or only install a package? What would
a real probe cost, and is it MVP or V1?

**Method:** read-only trace of `frontier_scout/trials.py`, `frontier_scout/lab.py`, and
`scripts/lab_runner.py`. Verified by an adversarial review subagent against the live code.

## Verdict: NOT supported today. Behavioral MCP trialing is net-new → **V1, gated.**

The MVP must **not** promise behavioral sandbox evidence. The MVP proof is a **static** safety
map (capability classification + policy read); see `frontier_scout/safety_summary.py`.

## Evidence (real code)

1. **The sandbox installs a *package*; it never speaks MCP.** A real (non-dry-run) trial runs
   `scripts/lab_runner.py::run` → `_resolve_tool` (README/PyPI/HF fetch, `lab_runner.py:361`) →
   `_classify` (1 LLM call picks `runtime ∈ {python,node,huggingface}`) → `_generate_test`
   (1 LLM call emits a synthetic script) → `_dispatch_subprocess` (`lab_runner.py:907`). The
   three runtimes are all installers: `_run_subprocess_python` (`pip install --target … && python lab_test.py`),
   `_run_subprocess_node` (`npm install --prefix … && node lab_test.js`), `_run_subprocess_hf`
   (load config + tokenizer only). The generator prompts cap behaviour at *import / instantiate*
   ("Focus on LOCAL behaviour: imports, class instantiation… NEVER run inference").

2. **No MCP-protocol client exists anywhere.** Grep across the repo for `stdio`, `jsonrpc`,
   `tools/list`, `list_tools`, `call_tool`, `ClientSession`, `StdioServerParameters`,
   `initialize`/`protocolVersion`, `sse_client` → **zero** matches. There is no `mcp` SDK
   dependency in `pyproject.toml` (the `"mcp"` token there is a `keywords=[…]` entry, not a dep).
   `frontier_scout/mcp_audit.py` is explicitly *static* ("classify capability words without
   executing any server or tool").

3. **A package-less / remote (HTTP) MCP server produces no trial at all.** `run()` gates on
   `OPEN_SOURCE_URL_RE` (`lab_runner.py:131`, github/pypi/hf/gitlab only); a hosted endpoint
   fails the gate and returns the "doesn't look like an open-source repo URL" refusal. Even if it
   passed, the classifier marks `runtime="unknown"` and the run is skipped.

4. **Behavioral insight is discarded at the process boundary.** `lab_runner._interpret`
   produces `verdict_for_team` / `what_worked` etc. and writes them to a `.scratch/labs/*.md`
   transcript, but `trials.run_trial` (`trials.py:66`) hardcodes the durable `lab_result` to
   `{duration_s: 0.0, cost_usd: 0.0, summary: "…inspect transcript for details."}`. So even the
   package smoke-test's richness is **not** persisted to the receipt.

## Cost of a real probe (V1, build only if Phase-3 validation shows pull)

Scope it to **high-risk servers only** (`dangerous_flags ∈ {write,shell,credential,network}`):

1. Add a real `mcp` SDK dependency (`mcp` Python package).
2. Add a transport client: **stdio** (spawn `uvx`/`npx`/`python -m <server>` from `server_meta`)
   and **http** (connect to the URL); speak `initialize` → `tools/list` → optionally a *sampled,
   read-only* `tools/call`.
3. Handle package-less / remote servers (today excluded by `OPEN_SOURCE_URL_RE`).
4. Plumb the structured result (`tools_count`, `capabilities_observed`, `errors`) back through
   `run_lab` → `run_trial` → `save_lab_result` so the **behavioral** summary is durable.

Estimated effort: ~1–2 focused tasks, plus a new dependency and hermetic-lab hardening for a
long-lived server process. **Deferred** behind the Phase-3 A/B/C gate (does sandbox evidence earn
pull?).

## Recommendation

Ship the **static** safety map in the MVP. Keep `trials.run_trial(dry_run=True)` available as a
"report-only" path for the demo. Build the behavioral probe in V1 only if validation confirms
demand, and only for high-risk servers.
