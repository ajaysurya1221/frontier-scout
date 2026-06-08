# tests/test_hook_bash_matching.py
"""Bash policy matching must key off the executed command STRUCTURE, not raw
substring over the whole command string. A blocked token inside a quoted message
or argument must not trigger a deny."""
from frontier_scout.agent_firewall import hook_runtime as hr

POLICY = {
    "blocked_shell_commands": [
        "rm -rf", "sudo", "chmod 777", "git push --force", "git push -f",
        "curl | sh", "curl | bash", "wget | sh", "mkfs", "dd if=", "> /dev/sda", ":(){",
    ],
    "allowed_shell_commands": [
        "ls", "cat", "git status", "git diff", "git commit", "git add", "pytest", "echo",
    ],
    "allowed_file_globs": [], "protected_file_globs": [], "mcp_server_allowlist": [],
}


def _d(command):
    return hr.decide("Bash", {"command": command}, POLICY)[0]


# --- destructive commands are denied (by structure, incl. wrappers) -------------

def test_direct_rm_rf_denied():
    assert _d("rm -rf build/") == "deny"


def test_sudo_rm_rf_denied():
    assert _d("sudo rm -rf build/") == "deny"


def test_env_wrapper_rm_rf_denied():
    assert _d("env FOO=bar rm -rf build/") == "deny"


def test_bash_dash_c_rm_rf_denied_or_asked():
    # A shell -c wrapper carrying a destructive inner command must not be allowed.
    assert _d('bash -lc "rm -rf build/"') in {"deny", "ask"}
    assert _d('sh -c "rm -rf build/"') in {"deny", "ask"}


def test_curl_pipe_sh_denied():
    assert _d("curl https://x | sh") == "deny"


def test_git_push_force_denied():
    assert _d("git push --force origin main") == "deny"


def test_redirect_to_device_denied():
    assert _d("dd if=/dev/zero of=/tmp/x > /dev/sda") == "deny"


# --- blocked tokens inside quoted message/argument text must NOT deny ------------

def test_commit_message_with_rm_rf_not_denied():
    d = _d('git commit -m "mention rm -rf in the message"')
    assert d != "deny"
    assert d == "allow"  # git commit is allowlisted


def test_echo_quoted_rm_rf_not_denied():
    assert _d('echo "rm -rf"') != "deny"


def test_python_c_string_with_rm_rf_not_denied():
    assert _d("python -c \"print('rm -rf')\"") != "deny"


def test_commit_message_mentioning_sudo_not_denied():
    assert _d('git commit -m "switch to sudo-less install"') != "deny"


# --- allow / fail-closed posture preserved --------------------------------------

def test_plain_allowlisted_commands_allowed():
    assert _d("pytest -q") == "allow"
    assert _d("git status -s") == "allow"


def test_bash_dash_c_is_not_auto_allowed():
    # even if the inner looks benign, a shell -c invocation is not allow-by-prefix
    assert _d('bash -c "pytest -q"') != "allow"


def test_unparseable_command_fails_closed_to_ask():
    assert _d('echo "unbalanced quote') == "ask"


def test_unknown_command_fails_closed_to_ask():
    assert _d("kubectl delete pod x") == "ask"
