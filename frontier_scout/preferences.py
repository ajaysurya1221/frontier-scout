"""Persisted Mission Control preferences.

Stored in the existing Frontier Scout home dir (``FRONTIER_SCOUT_HOME`` /
``~/.frontier-scout``). Holds NO secrets — only the chosen provider *name*.
A missing or corrupt file degrades to "no preference" so selection always
falls through to auto-detect rather than crashing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from frontier_scout import store

_SCHEMA = 1  # version for future migrations; not validated on load yet


def _path() -> Path:
    return store.home_dir() / "preferences.json"


def load_preferences() -> dict[str, Any]:
    try:
        with _path().open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def preferred_provider() -> str | None:
    val = load_preferences().get("provider")
    return val if isinstance(val, str) and val else None


def save_preferred_provider(name: str) -> None:
    store.init_home()  # ensure the home dir exists
    data = {"schema": _SCHEMA, "provider": name}
    path = _path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp.replace(path)  # atomic on POSIX
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
