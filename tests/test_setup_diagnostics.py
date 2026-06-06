"""Setup diagnostics + the non-interactive ``setup --plain``/``--json`` CLI surface.

``setup_diagnostics`` is the local-only, never-leaks-secrets profiler that powers
``frontier-scout setup --plain``/``--json`` (the classic/Briefing TUIs were removed;
Mission Control is the only interactive UI). These tests pin the diagnostic data
contract and the CLI rendering, independent of any TUI.
"""

import json
from pathlib import Path

from frontier_scout.cli import main
from frontier_scout.setup_diagnostics import (
    ProviderStatus,
    _recommended_actions,
    detect_providers,
    diagnostics_to_plain,
    setup_diagnostics,
)


def _seed_repo(path: Path) -> Path:
    path.mkdir()
    (path / "AGENTS.md").write_text("# agent rules\n")
    (path / ".mcp.json").write_text("{}\n")
    (path / ".env.local").write_text("OPENAI_API_KEY=must-not-leak\n")
    (path / "requirements.txt").write_text("langchain-core==1.3.5\n")
    (path / "Dockerfile").write_text("FROM python:3.12-slim\n")
    (path / ".github" / "workflows").mkdir(parents=True)
    (path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    return path


def test_setup_diagnostics_profiles_repo_and_never_exposes_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-should-not-appear")
    repo = _seed_repo(tmp_path / "repo")

    diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)
    payload = diagnostics.model_dump()
    rendered = diagnostics_to_plain(diagnostics)

    assert payload["profile"]["languages"] == ["python"]
    assert "Dockerfile" in payload["profile"]["containers"]
    assert ".mcp.json" in payload["profile"]["agent_configs"]
    assert payload["profile"]["dependencies"][0]["name"] == "langchain-core"
    assert any(
        provider["name"] == "OpenAI API" and provider["status"] == "present" for provider in payload["providers"]
    )
    assert "sk-secret-should-not-appear" not in json.dumps(payload)
    assert "must-not-leak" not in rendered
    assert "Local deterministic" in rendered


def test_ollama_detector_lists_models_without_requiring_login(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"models":[{"name":"qwen3:4b"},{"name":"gemma3:2b"}]}'

    def fake_urlopen(request, timeout):
        assert timeout == 0.25
        return Response()

    monkeypatch.setattr("frontier_scout.setup_diagnostics.urllib.request.urlopen", fake_urlopen)

    providers = detect_providers(ollama_timeout_s=0.25)
    ollama = next(provider for provider in providers if provider.name == "Ollama")

    assert ollama.status == "found"
    assert ollama.models == ["qwen3:4b", "gemma3:2b"]


def test_setup_cli_plain_and_json_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    repo = _seed_repo(tmp_path / "repo")

    assert main(["setup", "--repo", str(repo), "--plain"]) == 0
    plain = capsys.readouterr().out
    assert "Frontier Scout Mission Control" in plain
    assert "repo profile stays local" in plain

    assert main(["setup", "--repo", str(repo), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["repo"] == str(repo.resolve())
    # API key present -> dry_scan is first, evaluate_url second.
    assert payload["recommended_actions"][0]["id"] == "dry_scan"
    assert payload["recommended_actions"][1]["id"] == "evaluate_url"
    assert payload["scout_packs_selected"] == []


def test_setup_cli_packs_flag_persists_selection(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = _seed_repo(tmp_path / "repo")

    assert main(["setup", "--repo", str(repo), "--packs", "ai-devtools,mcp", "--plain"]) == 0
    plain = capsys.readouterr().out
    assert "[x] ai-devtools" in plain
    assert "[x] mcp" in plain
    assert "[ ] rag-memory" in plain


def test_no_args_non_interactive_prints_help(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    assert main([]) == 0

    assert "usage: frontier-scout" in capsys.readouterr().out


def test_recommended_actions_reorder_when_no_providers(tmp_path):
    no_providers = [
        ProviderStatus(name="Local deterministic", kind="stub", status="found", detail=""),
        ProviderStatus(name="Ollama", kind="local-model-runtime", status="unavailable", detail=""),
        ProviderStatus(name="Claude CLI", kind="cli", status="missing", detail=""),
        ProviderStatus(name="Codex CLI", kind="cli", status="missing", detail=""),
        ProviderStatus(name="Anthropic API", kind="api-key", status="missing", detail=""),
        ProviderStatus(name="OpenAI API", kind="api-key", status="missing", detail=""),
        ProviderStatus(name="GitHub token", kind="api-key", status="missing", detail=""),
    ]
    actions = _recommended_actions(tmp_path, no_providers)
    ids = [action.id for action in actions]
    # The offline demo lives at `frontier-scout --demo`, not in the action list.
    assert "demo_report" not in ids
    assert ids[0] == "dry_scan"

    with_key = list(no_providers)
    with_key[5] = ProviderStatus(name="OpenAI API", kind="api-key", status="present", detail="set")
    actions_with_key = _recommended_actions(tmp_path, with_key)
    ids_with_key = [action.id for action in actions_with_key]
    assert ids_with_key[0] == "dry_scan"
    assert ids_with_key.index("evaluate_url") < ids_with_key.index("deps_scan")
    assert "API key detected" in next(a.description for a in actions_with_key if a.id == "evaluate_url")
