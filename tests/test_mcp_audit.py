from frontier_scout.mcp_audit import classify_mcp_capabilities


def test_classifies_read_write_network_and_shell_capabilities():
    manifest = classify_mcp_capabilities(
        """
        tools/list:
          - name: read_file
            description: Read repository files
          - name: write_file
            description: Modify files on disk
          - name: run_command
            description: Execute shell commands
          - name: fetch_url
            description: Call an external API over HTTP
        """
    )

    assert manifest.capabilities["read"] == "likely"
    assert manifest.capabilities["write"] == "likely"
    assert manifest.capabilities["shell"] == "likely"
    assert manifest.capabilities["network"] == "likely"
    assert manifest.dangerous_flags == ["network", "shell", "write"]


def test_unknown_text_fails_closed():
    manifest = classify_mcp_capabilities("")

    assert manifest.capabilities["unknown"] == "likely"
    assert manifest.confidence == "low"
    assert "unknown" in manifest.dangerous_flags
