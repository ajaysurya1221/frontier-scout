# Security Posture

Frontier Scout is a local-first CLI. It scans public AI-tooling sources,
asks an LLM to rank and judge candidates, writes a local SQLite database, and
renders static reports. There is no hosted service, no multi-tenant backend,
and no required webhook surface.

## Threat model

| Threat | Vector | Mitigation |
|---|---|---|
| Prompt injection from public content | A hostile README, blog post, HN item, or model card says "ignore previous instructions" | Prompts treat source text as untrusted data. `scripts/validators.py` rejects known injection signatures in generated prose. |
| Source poisoning | A low-quality or malicious project trends briefly and gets promoted | The funnel uses source quotas, an optional Opus judge, readiness scoring, and deterministic policy gates before anything is stored. |
| Hallucinated tools or fake URLs | The model emits a verdict for a tool that was not in the source pool | `validate_verdicts()` fuzzy-matches `tool_name` against source titles and checks `source_url` against an explicit domain allowlist. |
| Incident-as-tool confusion | A breach, CVE, outage, or leaked-key story is labeled as ADOPT | Incident-like tool names are rejected by policy regexes. ADOPT verdicts with low readiness are automatically demoted. |
| Secret leakage through logs or artifacts | API keys appear in caught exceptions, lab output, or generated reports | `.env` is ignored, CI runs `detect-secrets`, and shared text helpers redact common Anthropic, OpenAI, GitHub, Slack, AWS, npm, and bearer token shapes. |
| Untrusted package execution in the lab | `frontier-scout lab` installs and imports third-party packages | The lab only accepts open-source URLs, strips the child process environment to a tiny allowlist, enforces wall-clock timeouts, caps daily cost/runs, scans generated scripts for secret-shaped strings, and writes local transcripts only. |
| Oversized model downloads | A Hugging Face candidate pulls huge weights | The HF lab path reads the model manifest and refuses weight files above `LAB_HF_SIZE_CAP_GB` before download. |
| Cost runaway | Repeated scans or lab runs consume too much LLM spend | The lab has daily run and USD caps. The Scout judge is optional via `JUDGE_ENABLED=false`; every call is logged to `costs.jsonl`. |

## Secrets

Required for live scans:

| Secret | Purpose | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sonnet scoring/verdicts and optional Opus judge | Keep in `.env` or shell env. Never commit. |
| `GITHUB_TOKEN` | Optional higher GitHub REST rate limit | Use a read-only fine-grained token where possible. |

Optional lab/scan settings:

| Env var | Purpose |
|---|---|
| `JUDGE_ENABLED=false` | Skip Opus judge to lower cost. |
| `FRONTIER_SCOUT_HOME` | Override `~/.frontier-scout`. |
| `LAB_RUNS_PER_DAY` | Cap local lab runs per UTC day. |
| `LAB_DAILY_USD_CAP` | Cap daily lab LLM spend. |
| `LAB_SUBPROCESS_TIMEOUT` | Cap each install/run subprocess step. |
| `LAB_HF_SIZE_CAP_GB` | Cap Hugging Face model weight downloads. |

If a secret is pasted into chat, logs, a GitHub issue, or a public branch,
rotate it immediately.

## Local data

Frontier Scout stores runtime data under `~/.frontier-scout/` by default:

- `db.sqlite` — scan and verdict history.
- `costs.jsonl` — API usage and estimated spend.
- `quality-log.jsonl` — scan quality metrics.
- `.scratch/labs/` — local lab transcripts when run from a checkout.

These files are local operator state, not source-controlled project assets.

## Reporting a security issue

Do not file public issues for vulnerabilities. Email the repository owner
with reproduction steps, affected version/commit, and impact assessment.
