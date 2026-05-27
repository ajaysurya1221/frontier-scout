import asyncio
import json
from pathlib import Path

from frontier_scout.cli import main
from frontier_scout.tui.setup_diagnostics import (
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

    monkeypatch.setattr("frontier_scout.tui.setup_diagnostics.urllib.request.urlopen", fake_urlopen)

    providers = detect_providers(ollama_timeout_s=0.25)
    ollama = next(provider for provider in providers if provider.name == "Ollama")

    assert ollama.status == "found"
    assert ollama.models == ["qwen3:4b", "gemma3:2b"]


def test_setup_cli_plain_and_json_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = _seed_repo(tmp_path / "repo")

    assert main(["setup", "--repo", str(repo), "--plain"]) == 0
    plain = capsys.readouterr().out
    assert "Frontier Scout Mission Control" in plain
    assert "repo profile stays local" in plain

    assert main(["setup", "--repo", str(repo), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["repo"] == str(repo.resolve())
    assert payload["recommended_actions"][0]["id"] == "dry_scan"


def test_no_args_non_interactive_prints_help(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    assert main([]) == 0

    assert "usage: frontier-scout" in capsys.readouterr().out


def test_no_args_interactive_dispatches_setup(monkeypatch):
    called = {}

    def fake_run_setup(*, repo, plain, json_output, ollama_url):
        called["repo"] = repo
        called["plain"] = plain
        called["json_output"] = json_output
        called["ollama_url"] = ollama_url
        return 0

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("frontier_scout.tui.runner.run_setup", fake_run_setup)

    assert main([]) == 0

    assert called["repo"] == Path(".")
    assert called["plain"] is False
    assert called["json_output"] is False


def test_textual_setup_app_enter_runs_selected_safe_action(tmp_path, monkeypatch):
    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed_repo(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp

        def fake_run_scan(*, repo, dry_run, persist, pack=None, discover=False):
            assert dry_run is True
            assert persist is True
            return {"verdicts": [{"tool_name": "modelcontextprotocol/servers"}]}

        monkeypatch.setattr("frontier_scout.tui.setup_app.run_scan", fake_run_scan)
        app = SetupApp(diagnostics)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert "Dry scan complete: 1 verdicts" in str(app.query_one("#result").content)

    asyncio.run(run_test())


def test_textual_setup_app_quit_requires_confirmation(tmp_path, monkeypatch):
    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics)
        async with app.run_test() as pilot:
            await pilot.press("q")
            assert "Press q again" in str(app.query_one("#result").content)
            await pilot.press("escape")
            assert app._quit_requested is False

    asyncio.run(run_test())
