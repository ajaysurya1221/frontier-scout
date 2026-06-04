def pytest_ignore_collect(collection_path, config):
    # The snapshot suite needs pytest-textual-snapshot's `snap_compare` fixture,
    # which is absent when plugin autoload is disabled (the repo's default CI:
    # PYTEST_DISABLE_PLUGIN_AUTOLOAD=1). Skip collecting it there so CI stays green;
    # run it locally with `-p pytest_textual_snapshot`.
    #
    # Note: this hook is bypassed when pytest is given the path explicitly
    # (isinitpath check in _pytest/main.py); pytest_collect_modifyitems below
    # handles the explicit-path case so both "pytest tests/" and
    # "pytest tests/test_tui3_snapshots.py" are safe in CI.
    if collection_path.name == "test_tui3_snapshots.py":
        return not config.pluginmanager.hasplugin("pytest_textual_snapshot")
    return None


def pytest_collection_modifyitems(session, config, items):
    # Belt-and-suspenders guard: deselect snapshot tests when
    # pytest-textual-snapshot is not loaded (covers the explicit-path case that
    # pytest_ignore_collect cannot catch because isinitpath bypasses it).
    if config.pluginmanager.hasplugin("pytest_textual_snapshot"):
        return
    keep = []
    deselected = []
    for item in items:
        if item.fspath.basename == "test_tui3_snapshots.py":
            deselected.append(item)
        else:
            keep.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = keep
