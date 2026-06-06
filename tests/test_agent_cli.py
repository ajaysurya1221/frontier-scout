import json

from frontier_scout.cli import main


def _seed_repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# x\n")
    (tmp_path / ".env").write_text("X=1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    return str(tmp_path)


def test_agent_scan_json(tmp_path, capsys):
    repo = _seed_repo(tmp_path)
    rc = main(["agent", "scan", "--repo", repo, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["static_only"] is True
    assert any(s["path"] == ".env" for s in payload["surfaces"])


def test_agent_policy_init_writes_file(tmp_path):
    repo = _seed_repo(tmp_path)
    rc = main(["agent", "policy", "init", "--repo", repo])
    assert rc == 0
    assert (tmp_path / "frontier-scout.policy.json").exists()


def test_agent_check_block_exit_code(tmp_path):
    repo = _seed_repo(tmp_path)
    main(["agent", "policy", "init", "--repo", repo])
    rc = main(["agent", "check", "run rm -rf / now", "--repo", repo])
    assert rc == 4  # block


def test_agent_check_allow_exit_and_receipt(tmp_path):
    repo = _seed_repo(tmp_path)
    main(["agent", "policy", "init", "--repo", repo])
    rc = main(["agent", "check", "read the README file", "--repo", repo])
    assert rc == 0
    rc2 = main(["agent", "receipts", "list", "--repo", repo, "--json"])
    assert rc2 == 0


def test_agent_export_writes_snippets(tmp_path):
    repo = _seed_repo(tmp_path)
    main(["agent", "policy", "init", "--repo", repo])
    rc = main(["agent", "export", "claude", "--repo", repo,
               "--target", str(tmp_path / "out")])
    assert rc == 0
    assert (tmp_path / "out").exists()
