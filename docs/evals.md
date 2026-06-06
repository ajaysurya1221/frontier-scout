# Evals

Frontier Scout ships fixture-backed eval sets under `evals/`:

- `evals/release_classification/golden.json`
  - Goal: classify release notes as `security`, `hardening`, `breaking`,
    `feature`, or `noise`.
  - Release gate: at least 80% exact-label match and at least 70% required
    evidence term overlap.
- `evals/pack_promotion/golden.json`
  - Goal: prove pack promotion/demotion rules are deterministic.
  - Release gate: 100% expected lifecycle outcome match.
- `evals/repo_fit/golden.json`
  - Goal: prove the same ecosystem item can receive different fit labels for
    different repo profiles.
  - Release gate: at least 5/6 label match and 80% reason-keyword overlap.

These evals are deliberately fixture-backed. Live discovery remains opt-in so CI
does not depend on the current state of GitHub, package registries, HN, or MCP
registry endpoints.
