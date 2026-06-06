# tests/test_agent_exporters.py
from frontier_scout.agent_firewall.models import AgentPolicy
from frontier_scout.exporters.policy_snippets import (
    build_agents_md_snippet,
    build_claude_md_snippet,
    build_pr_checklist,
    export_policy_snippets,
)


def _policy():
    return AgentPolicy(
        blocked_shell_commands=["rm -rf"],
        protected_file_globs=["**/.env*", ".github/workflows/**"],
        approval_gates=["shell", "credential", "ci"],
        required_checks=["pytest", "ruff check ."],
        mcp_server_allowlist=["github"],
        policy_notes="use sk-ant-PLANTEDSECRET as the token",  # planted
    )


def test_claude_md_snippet_has_sections_and_is_advisory():
    s = build_claude_md_snippet(_policy())
    assert "advisory" in s.lower()
    assert "rm -rf" in s and ".github/workflows" in s and "pytest" in s
    assert "enforce" not in s.lower() or "does not enforce" in s.lower()


def test_pr_checklist_is_markdown_checkboxes():
    s = build_pr_checklist(_policy())
    assert "- [ ]" in s and "pytest" in s


def test_agents_md_snippet_built():
    assert "Approval gates" in build_agents_md_snippet(_policy()) or \
        "approval" in build_agents_md_snippet(_policy()).lower()


def test_export_writes_redacted_files(tmp_path):
    out = export_policy_snippets(_policy(), str(tmp_path))
    assert set(out) == {"claude", "agents-md", "pr-checklist"}
    for path in out.values():
        text = open(path).read()
        assert "sk-ant-PLANTEDSECRET" not in text  # redacted at write
