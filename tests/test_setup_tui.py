import asyncio
import json
from pathlib import Path

from frontier_scout.cli import main
from frontier_scout.tui.setup_diagnostics import (
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

    monkeypatch.setattr("frontier_scout.tui.setup_diagnostics.urllib.request.urlopen", fake_urlopen)

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
    # v1.2.1 Stream I — bare ``frontier-scout`` now runs the wizard for
    # first-time users. Pretend we're already onboarded so this test
    # exercises the "straight to TUI" path it always meant to cover.
    monkeypatch.setattr("frontier_scout.wizard.config.is_onboarded", lambda: True)

    assert main([]) == 0

    assert called["repo"] == Path(".")
    assert called["plain"] is False
    assert called["json_output"] is False


def test_textual_setup_app_mounts_at_80x24(tmp_path, monkeypatch):
    """Stream L — true POSIX-minimum terminal must mount without
    exception, and the Scout tab must gain the ``.compact`` class so
    its layout reflows to fit."""

    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed_repo(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            assert scout.has_class("compact"), (
                "Scout tab must adopt the .compact CSS class at 80x24 so the "
                "DataTable doesn't eat the entire visible area."
            )

    asyncio.run(run_test())


def test_textual_setup_app_drops_compact_when_resized_wide(tmp_path, monkeypatch):
    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed_repo(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            assert not scout.has_class("compact"), (
                "Scout tab must NOT carry .compact at 120x36 — adaptive "
                "layout should leave plenty of room."
            )

    asyncio.run(run_test())


def test_textual_setup_app_lands_on_scout_tab(tmp_path, monkeypatch):
    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed_repo(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)

        from textual.widgets import TabbedContent

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "scout"

    asyncio.run(run_test())


def test_textual_setup_app_quit_modal_preserves_log(tmp_path, monkeypatch):
    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)

        from textual.widgets import RichLog

        from frontier_scout.tui.modals import QuitConfirmScreen
        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            log = app.query_one("#result-log", RichLog)
            initial_lines = list(log.lines)
            await pilot.press("q")
            await pilot.pause()
            assert isinstance(app.screen, QuitConfirmScreen)
            await pilot.press("n")
            await pilot.pause()
            assert not isinstance(app.screen, QuitConfirmScreen)
            # Result log is unchanged by the quit prompt.
            assert list(log.lines)[: len(initial_lines)] == initial_lines

    asyncio.run(run_test())


def test_textual_setup_app_repo_path_modal_opens_on_slash(tmp_path, monkeypatch):
    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)

        from frontier_scout.tui.modals import RepoPathPromptScreen
        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.press("slash")
            await pilot.pause()
            assert isinstance(app.screen, RepoPathPromptScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, RepoPathPromptScreen)

    asyncio.run(run_test())


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


def test_scout_dismiss_persists_to_state(tmp_path, monkeypatch):
    """v1 replaces the v0.4.1 SelectionList pack persistence with a Scout dismiss
    that writes to ``setup_state.json``."""

    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)

        from textual.widgets import Button, DataTable

        from frontier_scout.store import setup_state_path
        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            # v1.3.0 Stream C — no auto-scout. Trigger it explicitly.
            await pilot.click("#scout-run")
            for _ in range(50):
                await pilot.pause()
                table = app.query_one("#scout-table", DataTable)
                if table.row_count > 0:
                    break
            else:
                raise AssertionError("Scout tab did not populate after ▶ Scout now")
            table.cursor_coordinate = (0, 0)
            await pilot.pause()
            app.query_one("#scout-dismiss", Button).press()
            await pilot.pause()
            state = json.loads(setup_state_path().read_text())
            assert state.get("dismissed_tools")

    asyncio.run(run_test())


def test_repo_path_modal_updates_analyse_bar(tmp_path, monkeypatch):
    """v1 surfaces the fingerprint as a compressed analyse bar (was #fingerprint
    panel in v0.4.1)."""

    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo_one = _seed_repo(tmp_path / "repo1")

        repo_two = tmp_path / "repo2"
        repo_two.mkdir()
        (repo_two / "package.json").write_text('{"name":"node-app"}\n')

        diagnostics = setup_diagnostics(repo_one, ollama_timeout_s=0.001)

        from textual.widgets import Input, Static

        from frontier_scout.tui.modals import RepoPathPromptScreen
        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            initial = str(app.query_one("#analyse-bar", Static).render())
            assert "python" in initial

            await pilot.press("slash")
            await pilot.pause()
            assert isinstance(app.screen, RepoPathPromptScreen)
            modal_input = app.screen.query_one("#repo-input", Input)
            modal_input.value = str(repo_two)
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause()
                content = str(app.query_one("#analyse-bar", Static).render())
                if "javascript" in content or "npm" in content.lower():
                    break
            else:
                raise AssertionError("analyse bar did not refresh for new repo path")

    asyncio.run(run_test())


def test_setup_too_small_terminal_message(tmp_path, monkeypatch):
    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)

        from textual.widgets import Static

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test(size=(60, 18)):
            await asyncio.sleep(0)
            banner_text = str(app.query_one("#status-banner", Static).render())
            # v1.2.1 Stream L — the banner message moved to "below 80×24"
            # phrasing now that we adapt above that threshold.
            assert "below 80" in banner_text or "Terminal is small" in banner_text

    asyncio.run(run_test())


def test_splash_no_longer_mounted_in_v12(tmp_path, monkeypatch):
    """v1.2 deletes the splash. `show_splash=True` is accepted for back-compat
    but the splash never mounts — the main screen is visible immediately."""

    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics, show_splash=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            # The TabbedContent is reachable immediately — no splash overlay.
            tc = app.query_one(TabbedContent)
            assert tc.active == "scout"

    asyncio.run(run_test())


def test_analyse_bar_surfaces_top_imports(tmp_path, monkeypatch):
    """v1 collapses the v0.4.1 evidence-bars panel into a compact analyse bar
    line that still names the top imports with counts."""

    async def run_test() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)
        diagnostics.profile.import_evidence.top_python = [
            ("fastapi", 12),
            ("pydantic", 8),
        ]
        diagnostics.profile.import_evidence.files_scanned = 20
        diagnostics.profile.import_evidence.available = True

        from textual.widgets import Static

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test():
            rendered = str(app.query_one("#analyse-bar", Static).render())
            assert "fastapi" in rendered
            assert "×12" in rendered

    asyncio.run(run_test())
