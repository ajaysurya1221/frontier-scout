"""Install-time isolation tests (Codex review finding #1).

The runtime hermeticity was already covered by ``test_lab.py``. The
v1.2.1 fix extends the guarantee to **install-time** subprocesses too —
this file proves it. Until v1.2.1, ``pip install`` and the HF runtime
installer ran without ``env=`` or ``cwd=``, so package install hooks
could read ``ANTHROPIC_API_KEY`` and anything under the user's real
``~/`` during the install phase.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture
def lab_runner():
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import lab_runner as module

    return module


# ---------------------------------------------------------------------------
# _hermetic_base_env now accepts temp_home and respects it.
# ---------------------------------------------------------------------------


def test_hermetic_base_env_uses_temp_home_when_provided(tmp_path, monkeypatch, lab_runner):
    monkeypatch.setenv("HOME", "/Users/real-human")
    env = lab_runner._hermetic_base_env(temp_home=tmp_path)
    assert env["HOME"] == str(tmp_path)
    assert env["HOME"] != "/Users/real-human"


def test_hermetic_base_env_falls_back_to_real_home_without_arg(monkeypatch, lab_runner):
    monkeypatch.setenv("HOME", "/Users/real-human")
    env = lab_runner._hermetic_base_env()
    assert env["HOME"] == "/Users/real-human"


# ---------------------------------------------------------------------------
# _neutralised_env scrubs install-time config sources.
# ---------------------------------------------------------------------------


def test_neutralised_env_has_no_secrets(tmp_path, monkeypatch, lab_runner):
    """Adoption Firewall claim #1: install-time subprocess cannot read
    parent-process credentials."""

    # detect-secrets allowlisting — these are obviously-fake canaries
    # we set and then assert the lab DOES NOT see them. Tagging them so
    # CI's Secret-scan step doesn't trip on what is, by design, the
    # leak-detection plumbing.
    secrets = {
        "ANTHROPIC_API_KEY": "canary-anthropic",        # pragma: allowlist secret
        "OPENAI_API_KEY": "canary-openai",              # pragma: allowlist secret
        "GH_TOKEN": "canary-github",                    # pragma: allowlist secret
        "GITHUB_TOKEN": "canary-github-2",              # pragma: allowlist secret
        "AWS_ACCESS_KEY_ID": "canary-aws",              # pragma: allowlist secret
        "AWS_SECRET_ACCESS_KEY": "canary-aws-2",        # pragma: allowlist secret
        "SLACK_BOT_TOKEN": "canary-slack",              # pragma: allowlist secret
        "HF_TOKEN": "canary-hf",                        # pragma: allowlist secret
        "HUGGINGFACE_HUB_TOKEN": "canary-hf-2",         # pragma: allowlist secret
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)

    env = lab_runner._neutralised_env(tmp_path)

    for key in secrets:
        assert key not in env, f"install env leaked {key}"
    for sentinel in secrets.values():
        for key, value in env.items():
            assert sentinel not in value, f"sentinel {sentinel!r} present in {key}={value!r}"


def test_neutralised_env_uses_temp_home(tmp_path, monkeypatch, lab_runner):
    monkeypatch.setenv("HOME", "/Users/real-human")
    env = lab_runner._neutralised_env(tmp_path)
    assert env["HOME"] == str(tmp_path)


def test_neutralised_env_disables_pip_user_config(tmp_path, lab_runner):
    import os

    env = lab_runner._neutralised_env(tmp_path)
    # pip user/global config sources point at /dev/null (or platform equivalent).
    assert env["PIP_CONFIG_FILE"] == os.devnull
    # Empty (not unset) so pip won't reach an inherited index.
    assert env["PIP_INDEX_URL"] == ""
    assert env["PIP_EXTRA_INDEX_URL"] == ""
    assert env["PIP_NO_INPUT"] == "1"


def test_neutralised_env_pip_index_override_via_env(tmp_path, monkeypatch, lab_runner):
    monkeypatch.setenv("LAB_PIP_INDEX_URL", "https://internal.mirror/simple/")
    env = lab_runner._neutralised_env(tmp_path)
    assert env["PIP_INDEX_URL"] == "https://internal.mirror/simple/"


def test_neutralised_env_disables_hf_token(tmp_path, lab_runner):
    env = lab_runner._neutralised_env(tmp_path)
    assert env["HF_HUB_DISABLE_IMPLICIT_TOKEN"] == "1"
    assert env["HF_HUB_DISABLE_TELEMETRY"] == "1"
    assert env["HF_HOME"].startswith(str(tmp_path))


def test_neutralised_env_disables_npm_user_config(tmp_path, lab_runner):
    import os

    env = lab_runner._neutralised_env(tmp_path)
    assert env["npm_config_userconfig"] == os.devnull
    assert env["npm_config_globalconfig"] == os.devnull
    assert env["npm_config_cache"].startswith(str(tmp_path))
    assert env["NO_UPDATE_NOTIFIER"] == "1"


# ---------------------------------------------------------------------------
# Install subprocesses get env= and cwd= (this is the contract that was
# broken before v1.2.1).
# ---------------------------------------------------------------------------


def _capture_subprocess(monkeypatch, lab_runner):
    """Patch subprocess.run with a recorder and return the recorded calls."""

    calls = []

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        return FakeProc()

    monkeypatch.setattr(lab_runner.subprocess, "run", fake_run)
    return calls


def test_python_install_runs_with_neutralised_env_and_temp_cwd(monkeypatch, lab_runner):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leak-canary-1")

    calls = _capture_subprocess(monkeypatch, lab_runner)
    spec = {"name": "six", "package": "six", "url": "https://pypi.org/project/six/"}
    classification = {"runtime": "python", "package": "six"}
    lab_runner._run_subprocess_python(spec, classification, "print('ok')")

    install_call = next(c for c in calls if c["cmd"][1:5] == ["-m", "pip", "install", "--quiet"])
    assert "env" in install_call, "pip install must pass env="
    assert "cwd" in install_call, "pip install must pass cwd="
    assert install_call["cwd"], "cwd cannot be empty"
    assert "ANTHROPIC_API_KEY" not in install_call["env"]
    for value in install_call["env"].values():
        assert "leak-canary-1" not in value
    # cwd must point inside the temp dir; the env's HOME must match.
    assert install_call["env"]["HOME"] == install_call["cwd"]


def test_hf_install_runs_with_neutralised_env_and_temp_cwd(monkeypatch, lab_runner):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leak-canary-hf")
    monkeypatch.setenv("HF_TOKEN", "leak-canary-hf-token")

    calls = _capture_subprocess(monkeypatch, lab_runner)
    spec = {"name": "small-model", "package": "small-model", "url": "https://huggingface.co/some/model"}
    classification = {"runtime": "huggingface", "package": "small-model"}
    lab_runner._run_subprocess_hf(spec, classification, "print('ok')")

    install_call = next(
        c
        for c in calls
        if "huggingface_hub" in c["cmd"] and "pip" in c["cmd"]
    )
    assert "env" in install_call
    assert "cwd" in install_call
    assert "ANTHROPIC_API_KEY" not in install_call["env"]
    assert "HF_TOKEN" not in install_call["env"]
    for value in install_call["env"].values():
        assert "leak-canary-hf" not in value


def test_node_install_runs_with_neutralised_env_and_temp_cwd(monkeypatch, lab_runner):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leak-canary-node")

    calls = _capture_subprocess(monkeypatch, lab_runner)
    spec = {"name": "lodash", "package": "lodash", "url": "https://npmjs.com/package/lodash"}
    classification = {"runtime": "node", "package": "lodash"}
    lab_runner._run_subprocess_node(spec, classification, "console.log('ok');")

    install_call = next(c for c in calls if c["cmd"][:2] == ["npm", "install"])
    assert "env" in install_call
    assert "cwd" in install_call
    assert "ANTHROPIC_API_KEY" not in install_call["env"]
    for value in install_call["env"].values():
        assert "leak-canary-node" not in value
    assert install_call["env"]["HOME"] == install_call["cwd"]
