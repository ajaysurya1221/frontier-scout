# Security & Honesty Review — Agent Adoption Firewall MVP (Phase 6)

**Date:** 2026-06-06 · **Scope:** the new `frontier_scout/agent_firewall/` package,
`exporters/policy_snippets.py`, the `agent` CLI block, and the doctor checks. **Method:** an adversarial
multi-agent review across five dimensions (secret leakage · unsafe execution / destructive ops · overclaim /
honesty · untrusted input · policy-loader / fail-closed), each finding independently verified against the
real code (and several reproduced end-to-end). **Result:** **6 findings confirmed, 3 refuted; all 6 fixed
and pinned by regression tests** in `tests/test_agent_security.py`. Full suite after fixes: **718 passed, 0
failed.**

## Findings & dispositions

| # | Severity | Dimension | Finding | Fix | Test |
|---|---|---|---|---|---|
| 1 | **HIGH** | policy loader | **Fail-OPEN default.** `load_policy` returned a bare empty `AgentPolicy()` on missing/malformed/oversized files; combined with `evaluate_task` only escalating gated flags, a malformed/attacker-supplied `policy.json` made every dangerous task resolve to **allow**. | `load_policy` now returns `conservative_default_policy()` (deny-by-default: blocked shell, protected globs, all approval gates) on any failure; `evaluate_task` now escalates **every** dangerous capability to `needs_approval` regardless of gate membership (fail-closed). | `test_empty_policy_dangerous_task_fails_closed`, `test_malformed_policy_falls_back_to_conservative_not_empty` |
| 2 | **HIGH** | untrusted input | **Path traversal in `show_receipt`.** `receipt_id` (a CLI positional) was joined into a path unsanitized — `../../secret` and absolute paths read arbitrary `.json` files off disk and printed them. | `show_receipt` rejects any id with a separator / `..` / absolute path, plus a resolve-and-contain check that the target stays inside the receipts dir. | `test_show_receipt_rejects_relative_traversal`, `test_show_receipt_rejects_absolute_path`, `test_show_receipt_still_finds_a_legit_receipt` |
| 3 | MEDIUM | secret leakage | **Receipt redaction asymmetry.** Only `task_summary` was redacted; `files_considered`, reason messages (which echo paths), `warnings`, and `git_branch` were persisted **unredacted** and re-emitted by `receipts show` / `check --json`. | `write_receipt` now redacts **every** persisted string field via the shared `scrub_secrets`. | `test_receipt_redacts_secret_in_changed_files_and_reasons` |
| 4 | LOW | secret leakage | **Exporter lacked the short-token backstop.** `export_policy_snippets` used bare `sanitize_sensitive_text` (20-char floor), so a short secret-shaped token in a policy glob leaked into emitted snippets. | Factored the key-shape backstop into a shared `outputs/_text.scrub_secrets`; both receipts and the exporter use it. | `test_export_snippet_redacts_short_secret_in_glob` |
| 5 | LOW | untrusted input | **Unbounded policy read.** `load_policy` read the `--policy` file with no size cap (a 50 MB file loaded fully — memory amplification). | 1 MB `MAX_POLICY_BYTES` guard → conservative default + warning. | `test_oversized_policy_file_is_rejected` |
| 6 | LOW | policy loader | **"Fail-closed" claim over-scoped.** The fail-closed branch only fired for *unclassifiable* tasks, not classified-dangerous ones. | Closed by #1 (dangerous flags always escalate); docstring corrected. | covered by #1 tests |

## Refuted (checked, not real)

The verifier refuted 3 candidate findings (e.g. "scan reads secret contents" — it does not; `_find_secret_paths`
matches names only and never opens files; "the git subprocess is injectable" — args are fixed and not
user-controlled, `check=False`, `timeout=5`). The secret scanner is correctly bounded (`_SECRET_SCAN_DEPTH=2`,
`follow_symlinks=False`, `_SKIP_DIRS` + dot-dir pruning) and `evaluate_task`/`scan_repo` spawn nothing.

## Dimension posture (what was verified sound)

- **Secret leakage:** scan matches secret-likely files by **name/path only** — contents are never opened
  (`scan.py` has no read of a secret path); all persisted/emitted strings now route through `scrub_secrets`.
- **Unsafe execution / destructive ops:** the only subprocess in the entire package is the guarded read-only
  `git rev-parse` in `receipts.py` (fixed args, `check=False`, `timeout=5`, errors swallowed). `scan_repo`
  and `evaluate_task` execute nothing — no subprocess, network, or LLM. The proposed agent task is **never**
  run.
- **Overclaim / honesty:** every user-facing string is advisory; `block` is labeled advisory output, not
  enforcement; receipts are `kind="static-policy-assessment"` and never imply the task ran; copy avoids
  "enterprise-grade / compliance / SOC2 / signed-by / complete protection" (pinned by
  `tests/test_agent_honesty.py`).
- **Fail-closed:** the loader and the decision engine now both fail closed — a missing/broken policy denies
  by default, and any dangerous capability requires approval unless the task is plainly read-only.

## Residual limitations (honest)

- `agent check --json` / `check` text prints the live decision (the user's own just-typed input) to **stdout**;
  the durable, shareable artifact (the on-disk receipt) is redacted, but the ephemeral terminal echo carries
  whatever the user typed. This is acceptable (the user already holds that input) but worth noting for anyone
  piping `--json` into a shared log.
- `block` / `needs_approval` are **advisory**. Frontier Scout emits a decision and a receipt; it does **not**
  prevent an agent from doing anything. Enforcement is out of scope by design.
- Capability classification is deterministic regex over task text (`mcp_audit`) — it can miss an obfuscated
  intent or over-flag a benign mention. It fails closed (unknown → approval), but it is a heuristic, not a
  proof.
- This is a **research preview**: not validated with real users, not a compliance control, not complete
  protection.
