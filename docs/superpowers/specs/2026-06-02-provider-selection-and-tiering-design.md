# Provider Selection, Two-Tier Models & Gateway Interop

Status: draft 2026-06-02 — pending review. Proposed branch: `feat/provider-selection-tiering`. Target: v1.7.0.

Revisits the provider portions of
[2026-05-29 v1.4.0 Universal Provider](2026-05-29-v1.4.0-universal-provider-design.md).
That spec introduced the four-backend abstraction (Anthropic key → OpenAI key →
Claude Code CLI → Codex CLI, `tier` ∈ `fast|deep`). This one fixes where it
drifted, makes the active provider transparent and switchable, and lets advanced
users point at any gateway — **without making anything more complicated for the
people who just want it to work.**

## North star

The audience spans interns, college students, AI engineers, Principal AI
Engineers/Directors, and CTOs (roughly age 20–55). **Simplicity for the many is
the priority; power for the few must be invisible until opted into.** Every
decision below is filtered through that.

## Problem

Opening `frontier-scout` in a repo with no `.env` (both `claude` and `codex`
CLIs installed) auto-selected `claude-cli`, and pressing `s` failed after
~3 min with `scout failed: claude CLI timed out after 180s`. Investigating that
surfaced four real issues:

1. **CLI scout times out / is fragile.** `claude -p` is invoked with no
   isolation ([cli_provider.py:172-173](../../../frontier_scout/providers/cli_provider.py)),
   so every subprocess boots the user's entire Claude Code environment —
   `CLAUDE.md` auto-discovery, plugin sync, hooks, auto-memory, **and all
   configured MCP servers**. On a heavily-configured machine that cold-start
   alone exceeds the 180s `_TIMEOUT`
   ([cli_provider.py:26](../../../frontier_scout/providers/cli_provider.py)).
   `is_retryable` returns `False`
   ([cli_provider.py:163-164](../../../frontier_scout/providers/cli_provider.py)),
   so one timeout kills the scan. Output is scraped from prose stdout via
   `extract_json_object` — fragile. This also violates the repo's
   "scout subprocesses stay hermetic" invariant.

2. **The two-tier design is dead on the CLI backends.** `model(tier)` ignores
   `tier` and returns a fixed id
   ([cli_provider.py:118-119](../../../frontier_scout/providers/cli_provider.py));
   the subprocess passes no `--model`. So the high-volume scout pass *and* the
   optional judge pass both run on whatever single model the CLI defaults to —
   the cheap-fast-scout / strong-judge economics are lost, and the bulk pass may
   run on a heavy default model. **And the judge's defining *extended thinking***
   ([judge.py:131](../../../scripts/judge.py)) **is silently dropped on the CLI**
   — `create()` accepts but ignores the `thinking` arg
   ([cli_provider.py:133](../../../frontier_scout/providers/cli_provider.py)). So
   "Opus judges with extended thinking" is honored only on the Anthropic API path.
   (API backends still honor the model tier:
   anthropic = `claude-sonnet-4-6`/`claude-opus-4-7`, openai =
   `gpt-4o-mini`/`gpt-4o`,
   [anthropic_provider.py:20-21](../../../frontier_scout/providers/anthropic_provider.py),
   [openai_provider.py:24-25](../../../frontier_scout/providers/openai_provider.py).)

3. **Detection is duplicated, divergent, invisible, and unswitchable.** The TUI
   detects a provider for *display* in
   [tui3/data.py `_detect_provider`:146-158](../../../frontier_scout/tui3/data.py)
   (stored in `AppState.provider`), while the scan independently resolves the
   *actual* provider in
   [scripts/scout.py `_provider`:560-564](../../../scripts/scout.py)
   via `resolve_provider()`
   ([providers/__init__.py:100-129](../../../frontier_scout/providers/__init__.py)).
   The two can disagree → the header can lie about what a scan used. There is no
   way to see *why* a provider was chosen, and no way to switch without editing
   the environment and restarting.

4. **No path for gateway / self-host users.** Principal engineers and CTOs
   commonly run a gateway (LiteLLM, Bifrost) or self-host (vLLM, Ollama,
   OpenLLM). All of those expose an **OpenAI-compatible** API, but our OpenAI
   provider hardcodes the default endpoint —
   `openai.OpenAI(api_key=...)` with no `base_url`
   ([openai_provider.py:102-114](../../../frontier_scout/providers/openai_provider.py))
   — so those users cannot point Frontier Scout at their own stack.

### Decisions taken during brainstorming

- **Architecture:** one selection module (single source of truth), not scattered
  per-call-site detection.
- **Precedence default:** when multiple providers are available and nothing is
  pinned, **ask once in the TUI and remember**; never silently surprise.
- **Gateways:** **interoperate, don't embed.** Add a custom OpenAI-compatible
  `base_url` provider; do **not** take a LiteLLM/Bifrost/OpenLLM dependency
  (they are API-key gateways that cannot model our CLI-subscription path, and
  bundling LiteLLM adds ~12 transitive deps, ~1.5s import cost, weekly-release
  churn, and inherited supply-chain risk — incl. the Mar-2026 compromise — for
  breadth the user can get for free by running their own gateway behind a
  `base_url`).

## Design

### Stream 1 — One selection module (`frontier_scout/providers/select.py`)

A single source of truth for "which provider, and why," consumed by **both** the
TUI and the headless CLI — collapsing the two divergent detection paths
(Problem 3).

```
select_provider(cli_override: str | None = None, *, interactive: bool = False)
    -> Selection(provider, name, reason)
# reason ∈ {"flag", "preference", "auto", "must_ask"}
```

Precedence ladder (matches the field — Goose `env→config→default`, opencode
`flag→config→last-used→default`, aider `CLI>env>file`):

1. **Explicit** — `--provider` flag / `FRONTIER_SCOUT_PROVIDER` env → `flag`.
2. **Saved preference** — `~/.frontier-scout/preferences.json` (Stream 2) →
   `preference`.
3. **Auto-detect** — existing deterministic order: ANTHROPIC key → OPENAI key
   *(→ `openai-compatible` when `OPENAI_BASE_URL` is set, else `openai`)* →
   claude CLI → codex CLI — first available wins → `auto`.
4. **Ambiguity** — if >1 provider available **and** `interactive` **and** no
   saved preference → return `must_ask` (the TUI prompts; Stream 6). Headless is
   never `must_ask`: it uses the deterministic auto pick silently. **None
   available** → headless raises the existing `ProviderUnavailable` + `--demo`
   hint
   ([providers/__init__.py:125-129](../../../frontier_scout/providers/__init__.py));
   the TUI instead opens in offline demo mode with a nudge (Stream 6), never a
   dead-end.

`resolve_provider()` keeps its current signature but delegates the ladder to this
module so existing callers are unchanged. `_detect_provider` in
[tui3/data.py](../../../frontier_scout/tui3/data.py) is replaced by a call into
`select_provider(interactive=True)`; `AppState` stores both `provider` (name) and
`provider_reason`. The global `_PROVIDER` cache in
[scripts/scout.py:560-564](../../../scripts/scout.py) gains an
invalidation hook so a runtime switch (Stream 6) takes effect on the next scan
without a restart.

### Stream 2 — Persisted preference + "ask once"

New tiny module (`frontier_scout/preferences.py`) reading/writing
`~/.frontier-scout/preferences.json`, reusing the existing home dir
(`FRONTIER_SCOUT_HOME`, [store.py:14](../../../frontier_scout/store.py);
`init_home()` at [store.py:21](../../../frontier_scout/store.py)).

```json
{ "schema": 1, "provider": "claude-cli" }
```

**Only the provider name is persisted — never API keys or secrets.** (Keys stay
in the environment / CLI login.) Missing/corrupt file → treated as "no
preference" (fall through to auto/ask). This honors the repo's "never persist
credentials" invariant and matches how Goose/Zed/opencode store *selection* in
plain config while keeping secrets out of it.

### Stream 3 — CLI reliability: the timeout fix (make the subprocess hermetic)

Isolate the CLI invocation so it stops booting the user's whole environment
(fixes Problem 1 **and** satisfies the hermetic-subprocess invariant).

**claude-cli** — `create()`
([cli_provider.py:124-161](../../../frontier_scout/providers/cli_provider.py))
builds:

```
claude -p
  --model <tier-model>            # Stream 4 (scout=sonnet, judge=opus)
  --effort <tier-effort>          # judge=high|max (restores the judge's thinking); scout omits
  --output-format json            # structured envelope, not scraped prose
  --strict-mcp-config --mcp-config '{}'   # do NOT autoload the user's MCP servers
  # + restrict tool use (no agentic tools for a scoring call) — exact flag verified in plan
```

prompt via stdin. Parse the JSON envelope's `result` field, then run the existing
`extract_json_object`
([cli_provider.py:29-79](../../../frontier_scout/providers/cli_provider.py)) on
that. **Explicitly NOT `--bare`** — `--bare` forces API-key-only auth (OAuth and
keychain are never read), which would break subscription-logged-in users, who are
the entire reason the CLI backend exists.

**codex-cli** — `codex exec -m <tier-model> -c model_reasoning_effort=<tier-effort>
-s read-only --output-last-message <tmp>` (optionally `--output-schema <tmp>` with
the tool's JSON Schema; exact reasoning-effort config key verified in plan), prompt
via stdin; read the clean final message from the temp file instead of scraping
JSONL events.

**Timeout & errors** — keep `FRONTIER_SCOUT_CLI_TIMEOUT` (default stays 180s;
isolated calls land well under it). Make CLI timeouts **retryable once**
(`is_retryable` returns `True` for `TimeoutExpired`-derived errors). On final
failure, the `ProviderError` carries the likely cause + the
`FRONTIER_SCOUT_CLI_TIMEOUT` detail (for headless/logs); the TUI compass surfaces
it with **recovery actions** rather than raw env-var advice (Stream 6), via the
existing `WorkFailed` → compass path
([tui3/app.py:1238-1240](../../../frontier_scout/tui3/app.py)).

**Confidence note (carried into the plan):** `--strict-mcp-config`, `--model`,
and `--output-format json` are certain wins and auth-safe. Any *further*
isolation (e.g. skipping `CLAUDE.md` via `--setting-sources`) must be validated
by a **timed probe** in the implementation plan to confirm it does not disturb
OAuth before being committed to.

### Stream 4 — Two-tier models on every provider (restore intent)

`model(tier)` honors `tier` everywhere, env-overridable, mirroring the existing
API-provider pattern
([anthropic_provider.py:60-63](../../../frontier_scout/providers/anthropic_provider.py)).

| Provider | FAST (scout) | DEEP (judge) | Override env |
|---|---|---|---|
| anthropic | `claude-sonnet-4-6` | `claude-opus-4-7` | existing `FRONTIER_SCOUT_ANTHROPIC_FAST/DEEP_MODEL` |
| openai | `gpt-4o-mini` | `gpt-4o` | existing `FRONTIER_SCOUT_OPENAI_FAST/DEEP_MODEL` |
| claude-cli | `sonnet` | `opus` | `FRONTIER_SCOUT_CLAUDE_CLI_FAST/DEEP_MODEL` |
| codex-cli | codex default *(verified in plan)* | same-or-stronger | `FRONTIER_SCOUT_CODEX_CLI_FAST/DEEP_MODEL` |
| openai-compatible | from env *(Stream 5)* | from env, else = FAST | `FRONTIER_SCOUT_OPENAI_COMPAT_FAST/DEEP_MODEL` |

CLI backends pass the tier model through `--model`/`-m`. The fixed `_model_id`
([cli_provider.py:109,170,179](../../../frontier_scout/providers/cli_provider.py))
stays only as the cost-ledger label.

**Judge reasoning (DEEP), not just a bigger model.** The judge *reasons* —
`thinking={"type": "adaptive"}` ([judge.py:131](../../../scripts/judge.py)). We
carry that depth across backends, not only the model name: anthropic forwards
`thinking` (already); **claude-cli maps it to `--effort high|max`**; codex-cli to
`-c model_reasoning_effort=high`; openai/openai-compatible have no Anthropic-style
thinking on `gpt-4o`, so reasoning depth there would mean choosing an o-series DEEP
model (out of scope unless adopted separately). The scout (FAST) pass requests no
thinking / low effort.

**Overriding the CLI's own defaults — both directions.** Each CLI already selects
a default model + reasoning from its own config/plan; we override **per
invocation** via flags (`--model`/`--effort` for claude; `-m` +
`-c model_reasoning_effort=` for codex), and the override touches **only our
subprocess**, never the user's global CLI config (preserving hermeticity). The env
knobs above are three-state: **unset** → we pass our tier choice (restoring
tiering: fast model + low effort to the scout, strong model + high effort to the
judge); **set to a model/effort** → we pass yours; **set to `default` or empty** →
we pass nothing and inherit whatever your `claude`/`codex` is configured to use. So
you can let Frontier Scout drive, pin exact models, or hand control back to your
CLI.

**Graceful single-tier fallback** (aider's rule): if the DEEP model errors
because it is not on the user's plan (e.g. no Opus), fall back to the FAST model
and surface a one-time note rather than failing the scan. If a backend has no
meaningful cheaper tier (possible for codex), FAST == DEEP — **consciously
documented, not silently flattened.**

### Stream 5 — Gateway interop: the `openai-compatible` provider

One new backend that reuses the OpenAI translation layer and simply passes
`base_url=` to the client — the smallest possible change that unlocks the entire
gateway/serving ecosystem (LiteLLM, Bifrost, OpenLLM, Ollama, vLLM, OpenRouter,
…) with **zero added dependencies**.

- Likely a thin `OpenAICompatibleProvider(OpenAIProvider)` (name
  `openai-compatible`) that injects `base_url` into the client constructor
  ([openai_provider.py:107-114](../../../frontier_scout/providers/openai_provider.py))
  and uses its own model env (Stream 4) + key.
- **Progressive disclosure (the simplicity mechanism):** the provider only
  *exists* when a base URL is set. It reads the universal `OPENAI_BASE_URL` (and
  a namespaced `FRONTIER_SCOUT_OPENAI_BASE_URL`). No base URL set → it never
  appears, is never auto-detected, is never asked about. The intern never
  encounters it; a CTO who already exports `OPENAI_BASE_URL` gets it
  auto-detected with nothing new to learn.
- **Disambiguation (mutually exclusive on `OPENAI_BASE_URL`):** when the base URL
  is set, `openai-compatible` is used and the stock `openai` provider yields, so
  they never both claim the slot; when unset, `openai-compatible` does not exist
  and stock `openai` handles `OPENAI_API_KEY`. Key via env
  (`FRONTIER_SCOUT_OPENAI_COMPAT_API_KEY`, else reuse `OPENAI_API_KEY`); some
  local servers accept any key.
- Added to `PROVIDER_NAMES`
  ([providers/__init__.py:55](../../../frontier_scout/providers/__init__.py)) and
  slotted into auto-detect at the OPENAI position — used instead of the stock
  `openai` provider whenever `OPENAI_BASE_URL` is set.

### Stream 6 — TUI: surface + switch (`frontier_scout/tui3/`)

- **Indicator with reason.** The header already shows the provider name
  ([tui3/app.py:237-240](../../../frontier_scout/tui3/app.py)); add a short reason
  badge from `provider_reason` — e.g. `anthropic · API key`,
  `claude-cli · pinned`, `claude-cli · auto`. The Settings provider section
  ([tui3/panes.py:267-279](../../../frontier_scout/tui3/panes.py)) also shows the
  active FAST/DEEP models so tiering is visible.
- **Switcher.** A `ProviderSwitcherScreen` mirroring `RepoSwitcherScreen`
  ([tui3/overlays.py:603-659](../../../frontier_scout/tui3/overlays.py)) using the
  same `LineClickStatic` + j/k/enter/click pattern
  ([tui3/widgets.py:50-80](../../../frontier_scout/tui3/widgets.py)), opened three
  ways: a keybinding, a clickable Settings row, **and by clicking the header
  provider badge itself** (tui3 already has mouse parity — the most discoverable
  affordance, nothing to learn). Mirrors `switch_repo`
  ([tui3/app.py:977-998](../../../frontier_scout/tui3/app.py)) as `switch_provider`:
  write preference (Stream 2) → invalidate the scout `_PROVIDER` cache → re-scout
  live, **no restart**. Unavailable providers render greyed with the fix-it
  reason ("set `OPENAI_API_KEY`", "log in to `codex`", "set `OPENAI_BASE_URL`").
- **Ask-once.** On launch, if `select_provider(interactive=True)` returns
  `must_ask` (>1 available, no saved preference, not `--demo`), open the switcher
  as a first-run picker with a **sensible default pre-highlighted** (so Enter
  accepts in one keypress); the choice is saved and never re-asked.
- **No-provider → demo, not dead-end.** If nothing is available (and not already
  `--demo`), the TUI opens in offline demo mode with a one-line *"no provider
  connected · press P to set one up"* nudge instead of erroring out — a working
  first screen for keyless students/interns. (Headless keeps the explicit
  `ProviderUnavailable` + `--demo` error.)
- **Actionable failure recovery.** A scout failure (e.g. a CLI timeout) renders in
  the compass with next steps, not just a cause: *"scout failed: … · press P to
  switch · r to retry · or run `--demo`"*, keeping env-var advice out of the
  primary message ([tui3/app.py:1238-1240](../../../frontier_scout/tui3/app.py)).
- **Human labels, not jargon:** "Claude (CLI subscription)", "OpenAI API",
  "Custom endpoint (your gateway)". Everything routes through `app._paint` (mono)
  and `glyphs(app.state.unicode)` (ascii) per the repo invariants.

### Stream 7 — Docs & tests

- **Kill the stale "Sonnet → Sonnet → Opus" narrative** wherever it is hardcoded
  (`report.py` cost table, `scripts/scout.py` pipeline docstring,
  `scripts/judge.py` header) — render tiers from the active provider instead.
- **Tests** extend
  [tests/test_providers.py](../../../tests/test_providers.py):
  - selection ladder: `flag` / `preference` / `auto` / `must_ask` / none.
  - `model(tier)` returns distinct per-tier ids for every provider; CLI
    graceful DEEP→FAST fallback.
  - CLI command builders include the isolation flags + `--model` + judge
    `--effort` / `-c model_reasoning_effort`; the three-state model/effort
    override (unset → our tier, set → yours, `default`/empty → inherit the CLI
    default); JSON-envelope parsing for both CLIs.
  - preferences read/write round-trip; corrupt-file tolerance.
  - `openai-compatible` only registers when a base URL is set;
    `OPENAI_BASE_URL` disambiguation vs the stock `openai` provider.
  - no-provider opens the TUI in demo mode (not an exception) while headless still
    raises; a failed scout's message and the header badge both expose the switcher.
  - Run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `/opt/miniconda3/bin/python`
    (bare `python` is not on PATH in this env; the 3 `test_implement.py`
    failures are pre-existing env-only).

## Simplicity guarantees (the north star, made concrete)

- The **default path is unchanged and invisible**: a logged-in CLI just works;
  nothing configured → `--demo`. No new concepts for students/interns.
- The **custom endpoint stays hidden until you set a base URL** (progressive
  disclosure). The majority never see it.
- **Advanced users learn nothing new** — it is the standard `OPENAI_BASE_URL`.
- The **switcher speaks human, not jargon.**
- **Nobody is forced to configure two tiers** — one model collapses to
  single-tier automatically.
- **The edges are dead-end-free:** no provider → a working demo + a one-key nudge;
  a failed scout → in-place recovery actions; switching is one click on the badge
  you already see.

## Non-negotiables

- Test suite green at every commit.
- One source of truth for provider selection; the TUI indicator can never
  disagree with what a scan actually used.
- Never spend on a user's key silently; the CLI subscription path keeps OAuth
  (never `--bare`).
- CLI subprocesses stay hermetic (no MCP autoload, no inherited agent
  environment) and never see real credentials beyond the CLI's own login.
- Persist **only** the provider name — never keys or secrets.
- `--demo` / offline still needs no provider and never prompts.
- Color↔mono and unicode↔ascii fallbacks preserved on every new renderable.

## Out of scope (YAGNI)

- No embedded gateway dependency (LiteLLM/Bifrost/OpenLLM) — interop via
  `base_url` only.
- No N-role model matrix — exactly two tiers (FAST/DEEP).
- No per-tier provider *mixing* (e.g. scout on OpenAI + judge on Anthropic) —
  one active provider, two tiers within it. Possible future work.
- No API-key storage / keychain — selection only.
- No change to the headless deterministic auto-detect order (no flip to
  CLI-first).
- Bumping the API model versions (`sonnet-4-6`/`opus-4-7`) is a separate
  decision.
