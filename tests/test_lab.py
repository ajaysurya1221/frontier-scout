"""Lab-runner regression tests — polyglot dispatcher, hermetic env,
cost caps, secret-leak guard, URL classification, test excerpt.

These are the behavioural contracts every public release MUST hold for the
local polyglot lab runner.
"""

from __future__ import annotations

import json
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── URL classification ──────────────────────────────────────────────────────


class TestOpenSourceUrl:
    """``lab_runner.is_open_source_url`` is the bouncer at the door — the
    lab can only pull from github.com / pypi.org / huggingface.co /
    gitlab.com. Anything else gets a clean "lab can't exercise this"
    rather than a guaranteed-to-fail pull."""

    def test_github_url_passes(self):
        import lab_runner

        assert lab_runner.is_open_source_url("https://github.com/foo/bar") is True
        assert lab_runner.is_open_source_url("https://www.github.com/foo/bar") is True

    def test_pypi_url_passes(self):
        import lab_runner

        assert lab_runner.is_open_source_url("https://pypi.org/project/dspy/") is True

    def test_huggingface_url_passes(self):
        import lab_runner

        assert (
            lab_runner.is_open_source_url("https://huggingface.co/meta-llama/Llama-3")
            is True
        )

    def test_gitlab_url_passes(self):
        import lab_runner

        assert lab_runner.is_open_source_url("https://gitlab.com/foo/bar") is True

    def test_vendor_blog_blocked(self):
        import lab_runner

        assert lab_runner.is_open_source_url("https://anthropic.com/news/x") is False
        assert lab_runner.is_open_source_url("http://random-blog.com/post") is False

    def test_empty_or_none_returns_false(self):
        import lab_runner

        assert lab_runner.is_open_source_url("") is False
        assert lab_runner.is_open_source_url(None) is False


# ── Secret-leak pre-execution guard ─────────────────────────────────────────


class TestLabSecretLeakGuard:
    """Pre-execution regex check rejects scripts that look like they baked a
    real secret in. This is the safety net against prompt injection where
    the tool's README tries to coerce the generator into hard-coding a key."""

    def _matches(self, text):
        import lab_runner

        return lab_runner.SECRET_LEAK_RE.search(text)

    @staticmethod
    def _secret(*parts: str) -> str:
        """Build scanner fixtures at runtime so push protection sees no token."""
        return "".join(parts)

    def test_anthropic_key_pattern_caught(self):
        token = self._secret("sk-ant-api03-", "AbCdEfGhIjKlMnOpQrStUv")
        assert self._matches(f"client = Anthropic(api_key='{token}')")

    def test_openai_proj_key_pattern_caught(self):
        token = self._secret("sk-proj-", "AbCdEfGhIjKlMnOpQrStUv")
        assert self._matches(f"OPENAI_API_KEY = '{token}'")

    def test_slack_token_pattern_caught(self):
        token = self._secret("xox", "b-", "1234567890-", "abcdefghijklmn")
        assert self._matches(f"client = WebClient(token='{token}')")

    def test_github_pat_pattern_caught(self):
        token = self._secret("ghp_", "AbCdEfGhIjKlMnOpQrStUvWxYz1234")
        assert self._matches(f"headers = {{'Authorization': '{token}'}}")

    def test_aws_access_key_caught(self):
        assert self._matches(
            f"AWS_ACCESS_KEY_ID = '{self._secret('ASIA', 'Q6RZI4ENNQ35NVWL')}'"
        )
        assert self._matches(
            f"AWS_ACCESS_KEY_ID = '{self._secret('AKIA', 'Q6RZI4ENNQ35NVWL')}'"
        )

    def test_npm_token_caught(self):
        """Round 10 added npm_<36+> so a Node test script that bakes in an
        npm publish token is rejected before execution."""
        token = self._secret(
            "npm_", "abcdefghijklmnopqrstuvwxyz0123456789AB"
        )
        assert self._matches(f"const auth = '{token}';")

    def test_clean_synthetic_script_passes(self):
        clean = (
            "import dspy\n"
            "print('OK: imported')\n"
            "try:\n"
            "    obj = dspy.Predict('question -> answer')\n"
            "    print('OK: instantiated Predict')\n"
            "except Exception as e:\n"
            "    print(f'FAILED: {e}')\n"
        )
        assert self._matches(clean) is None

    def test_placeholder_key_not_caught(self):
        placeholder = "ANTHROPIC_API_KEY = 'PLACEHOLDER'"  # pragma: allowlist secret
        assert self._matches(placeholder) is None


# ── Runtime dispatch + pre-flight ───────────────────────────────────────────


class TestLabRuntimeDispatch:
    """Polyglot lab dispatcher. The classifier emits a ``runtime`` field
    (python / node / huggingface / unknown); ``_unsupported_runtime_reason``
    bails BEFORE spending generator + subprocess + interpreter cycles when:
      - the runtime isn't in the supported set
      - the HF model is gated / private / over the size cap
      - the README explicitly says the repo isn't a runnable library
      - python runtime was picked but PyPI returned nothing
    """

    def test_unknown_runtime_is_rejected(self):
        import lab_runner

        spec = {
            "name": "x",
            "url": "https://github.com/x/y",
            "readme": "",
            "pypi": {},
            "hf": {},
        }
        reason = lab_runner._unsupported_runtime_reason(
            spec,
            {"runtime": "cargo", "package": "x"},
            "https://github.com/x/y",
        )
        assert reason is not None
        assert "cargo" in reason or "supported" in reason

    def test_python_with_pypi_passes_gate(self):
        import lab_runner

        spec = {
            "name": "dspy",
            "url": "https://github.com/stanfordnlp/dspy",
            "readme": "DSPy: programming with foundation models",
            "pypi": {"version": "2.5.0", "summary": "DSPy"},
            "hf": {},
        }
        assert (
            lab_runner._unsupported_runtime_reason(
                spec,
                {"runtime": "python", "package": "dspy"},
                "https://github.com/stanfordnlp/dspy",
            )
            is None
        )

    def test_python_with_no_pypi_record_is_rejected(self):
        """anthropics/skills — runtime=python but PyPI returns nothing → bail."""
        import lab_runner

        spec = {
            "name": "anthropics/skills",
            "url": "https://github.com/anthropics/skills",
            "readme": "Anthropic skills — a collection of capabilities.",
            "pypi": {},
            "hf": {},
        }
        reason = lab_runner._unsupported_runtime_reason(
            spec,
            {"runtime": "python", "package": ""},
            "https://github.com/anthropics/skills",
        )
        assert reason is not None
        assert "PyPI" in reason

    def test_node_runtime_passes_gate(self):
        """Node tools don't need a PyPI record — npm install succeeds or
        fails naturally with a real npm error message in stderr."""
        import lab_runner

        spec = {
            "name": "@modelcontextprotocol/inspector",
            "url": "https://github.com/modelcontextprotocol/inspector",
            "readme": "Run with `npx @modelcontextprotocol/inspector`",
            "pypi": {},
            "hf": {},
        }
        assert (
            lab_runner._unsupported_runtime_reason(
                spec,
                {
                    "runtime": "node",
                    "package": "@modelcontextprotocol/inspector",
                },
                "https://github.com/modelcontextprotocol/inspector",
            )
            is None
        )

    def test_hf_runtime_passes_when_small_and_public(self):
        import lab_runner

        spec = {
            "name": "tiny-gpt2",
            "url": "https://huggingface.co/sshleifer/tiny-gpt2",
            "readme": "",
            "pypi": {},
            "hf": {
                "total_weight_bytes": 5_000_000,
                "gated": False,
                "private": False,
            },
        }
        assert (
            lab_runner._unsupported_runtime_reason(
                spec,
                {"runtime": "huggingface", "package": "sshleifer/tiny-gpt2"},
                "https://huggingface.co/sshleifer/tiny-gpt2",
            )
            is None
        )

    def test_hf_model_over_size_cap_is_rejected_without_download(self):
        import lab_runner

        spec = {
            "name": "DeepSeek-V4-Pro",
            "url": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
            "readme": "",
            "pypi": {},
            "hf": {
                "total_weight_bytes": 67 * 1024 ** 3,
                "gated": False,
                "private": False,
            },
        }
        reason = lab_runner._unsupported_runtime_reason(
            spec,
            {
                "runtime": "huggingface",
                "package": "deepseek-ai/DeepSeek-V4-Pro",
            },
            "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
        )
        assert reason is not None
        assert "GB" in reason and ("cap" in reason or "over" in reason)

    def test_hf_gated_model_is_rejected(self):
        import lab_runner

        spec = {
            "name": "Llama-3",
            "url": "https://huggingface.co/meta-llama/Llama-3",
            "readme": "",
            "pypi": {},
            "hf": {
                "total_weight_bytes": 100_000_000,
                "gated": True,
                "private": False,
            },
        }
        reason = lab_runner._unsupported_runtime_reason(
            spec,
            {"runtime": "huggingface", "package": "meta-llama/Llama-3"},
            "https://huggingface.co/meta-llama/Llama-3",
        )
        assert reason is not None
        assert "gated" in reason.lower()

    def test_hf_url_without_manifest_is_rejected(self):
        import lab_runner

        spec = {
            "name": "x",
            "url": "https://huggingface.co/x/y",
            "readme": "",
            "pypi": {},
            "hf": {},
        }
        reason = lab_runner._unsupported_runtime_reason(
            spec,
            {"runtime": "huggingface", "package": "x/y"},
            "https://huggingface.co/x/y",
        )
        assert reason is not None
        assert "manifest" in reason.lower() or "huggingface" in reason.lower()

    def test_readme_says_not_a_library_overrides_runtime(self):
        """A 'skills are markdown' README skips even if runtime=python."""
        import lab_runner

        spec = {
            "name": "some-skills",
            "url": "https://github.com/x/some-skills",
            "readme": "This repository contains skills — markdown files only.",
            "pypi": {"version": "0.1.0", "summary": "unrelated package"},
            "hf": {},
        }
        reason = lab_runner._unsupported_runtime_reason(
            spec,
            {"runtime": "python", "package": "some-skills"},
            "https://github.com/x/some-skills",
        )
        assert reason is not None
        assert "README" in reason or "library" in reason

    # ── Hermetic env: no secrets reach the child, across ALL runtimes ────

    def _patch_loud_secrets(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "parent-anthropic-sentinel")
        monkeypatch.setenv("OPENAI_API_KEY", "parent-openai-sentinel")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "parent-slack-sentinel")
        monkeypatch.setenv("GH_TOKEN", "parent-github-sentinel")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "parent-aws-key-sentinel")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "PARENT-SHOULD-NOT-LEAK")

    def test_hermetic_base_env_has_no_secrets(self, monkeypatch):
        """The base hermetic env is the shared root of all three runtime
        runners. Backs the README isolation claim."""
        import lab_runner

        self._patch_loud_secrets(monkeypatch)
        env = lab_runner._hermetic_base_env()
        forbidden = {
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "SLACK_BOT_TOKEN",
            "GH_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "SLACK_SIGNING_SECRET",
            "HF_TOKEN",
        }
        leaked = sorted(env.keys() & forbidden)
        assert leaked == [], f"hermetic base env leaked: {leaked}"
        # Sanity: PATH + HOME ARE pass-throughs (we need them).
        assert "PATH" in env and "HOME" in env


# ── Cost / frequency caps ───────────────────────────────────────────────────


class TestLabCapsReader:
    """``_within_caps`` is the bouncer at the door — reads today's lab-*
    lines from the cost ledger and refuses if either cap is hit.

    Cap fires → polite refusal, no Sonnet calls, no subprocess. This is the
    single most important cost-defense."""

    def test_empty_ledger_allows_run(self, tmp_path, monkeypatch):
        import lab_runner

        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        assert lab_runner._within_caps() is None

    def test_under_count_cap_allows_run(self, tmp_path, monkeypatch):
        import lab_runner

        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 3)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 5.0)

        today = datetime.now(UTC).isoformat()
        lines = [
            {"ts": today, "component": "lab-classify", "cost_usd": 0.01, "run_id": "abc"},
            {"ts": today, "component": "lab-generate", "cost_usd": 0.02, "run_id": "abc"},
            {"ts": today, "component": "lab-interpret", "cost_usd": 0.01, "run_id": "abc"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        assert lab_runner._within_caps() is None

    def test_run_count_cap_refuses(self, tmp_path, monkeypatch):
        import lab_runner

        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 1)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 100.0)

        today = datetime.now(UTC).isoformat()
        lines = [
            {"ts": today, "component": "lab-classify", "cost_usd": 0.01, "run_id": "first"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        refusal = lab_runner._within_caps()
        assert refusal is not None
        assert "daily cap" in refusal.lower()

    def test_usd_cap_refuses(self, tmp_path, monkeypatch):
        import lab_runner

        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 100)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 1.0)

        today = datetime.now(UTC).isoformat()
        lines = [
            {"ts": today, "component": "lab-classify", "cost_usd": 1.50, "run_id": "expensive"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        refusal = lab_runner._within_caps()
        assert refusal is not None
        assert "USD cap" in refusal

    def test_yesterdays_entries_dont_count(self, tmp_path, monkeypatch):
        """Caps reset at midnight UTC — yesterday's spend shouldn't gate today."""
        import lab_runner

        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 1)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 1.0)

        yesterday = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        lines = [
            {"ts": yesterday, "component": "lab-classify", "cost_usd": 0.50, "run_id": "old1"},
            {"ts": yesterday, "component": "lab-generate", "cost_usd": 0.50, "run_id": "old1"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        assert lab_runner._within_caps() is None

    def test_non_lab_costs_dont_count(self, tmp_path, monkeypatch):
        """Scout costs share the ledger but don't count against the lab cap —
        only ``lab-*`` component entries do."""
        import lab_runner

        monkeypatch.setattr(lab_runner, "COSTS_LEDGER", tmp_path / "costs.jsonl")
        monkeypatch.setattr(lab_runner, "LAB_RUNS_PER_DAY", 1)
        monkeypatch.setattr(lab_runner, "LAB_DAILY_USD_CAP", 1.0)

        today = datetime.now(UTC).isoformat()
        lines = [
            {"ts": today, "component": "scout-score", "cost_usd": 5.0, "run_id": "s1"},
            {"ts": today, "component": "scout-verdict", "cost_usd": 10.0, "run_id": "s1"},
            {"ts": today, "component": "scout-judge", "cost_usd": 5.0, "run_id": "s1"},
        ]
        (tmp_path / "costs.jsonl").write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n"
        )
        assert lab_runner._within_caps() is None


# ── Live subprocess hermetic check ──────────────────────────────────────────


class TestLabSubprocessHermetic:
    """The single most important behavioural guarantee: the generated test
    script runs with NO team API keys in the child env.

    Verified via subprocess introspection (the test asks the child to print
    its env) on the live python runtime — the Node + HF runners share the
    same ``_hermetic_base_env()`` root, separately covered by
    ``TestLabRuntimeDispatch::test_hermetic_base_env_has_no_secrets``."""

    def test_python_subprocess_env_contains_no_secrets(self, tmp_path, monkeypatch):
        import lab_runner

        monkeypatch.setenv("ANTHROPIC_API_KEY", "parent-anthropic-sentinel")
        monkeypatch.setenv("OPENAI_API_KEY", "parent-openai-sentinel")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "parent-slack-sentinel")
        monkeypatch.setenv("GH_TOKEN", "parent-github-sentinel")

        spec = {"name": "six", "package": "six", "url": "https://pypi.org/project/six/"}
        classification = {"runtime": "python", "package": "six"}
        script = textwrap.dedent(
            """
            import os, sys, json
            keys_present = sorted(k for k in os.environ
                                   if k in {
                                       "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                                       "SLACK_BOT_TOKEN", "GH_TOKEN",
                                       "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                       "AWS_SESSION_TOKEN",
                                   })
            print("LEAKED_SECRETS=" + json.dumps(keys_present))
            print("PATH_PRESENT=" + str("PATH" in os.environ))
            print("HOME_PRESENT=" + str("HOME" in os.environ))
        """
        ).strip()

        result = lab_runner._run_subprocess_python(spec, classification, script)
        if result["stage"] == "install" and result["exit_code"] != 0:
            pytest.skip(
                f"pip install of `six` failed in test env: {result['stderr'][:120]}"
            )

        assert "LEAKED_SECRETS=[]" in result["stdout"], (
            f"child env leaked secrets! stdout was:\n{result['stdout']}"
        )
        assert "PATH_PRESENT=True" in result["stdout"]
        assert "HOME_PRESENT=True" in result["stdout"]


# ── Test-excerpt helper ─────────────────────────────────────────────────────


class TestLabTestExcerpt:
    """``_test_excerpt`` pulls a small representative slice from the
    generated test script for the rich_text_preformatted block."""

    def test_skips_docstring_and_comments(self):
        import lab_runner

        script = '''"""This is a docstring."""

# A leading comment
# Another comment

import dspy
print("OK: imported")
obj = dspy.Predict("x -> y")
'''
        excerpt = lab_runner._test_excerpt(script, max_lines=3)
        assert "docstring" not in excerpt
        assert excerpt.startswith("import dspy")
        assert excerpt.count("\n") <= 2

    def test_returns_empty_on_empty_input(self):
        import lab_runner

        assert lab_runner._test_excerpt("") == ""
        assert lab_runner._test_excerpt(None) == ""

    def test_caps_at_max_lines(self):
        import lab_runner

        script = "\n".join(f"line_{i}" for i in range(20))
        excerpt = lab_runner._test_excerpt(script, max_lines=4)
        assert excerpt.count("\n") == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
