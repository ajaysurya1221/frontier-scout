"""Persisted wizard configuration in ``~/.frontier-scout/config.toml``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

import tomli_w

from frontier_scout.store import home_dir, init_home


def config_path() -> Path:
    return home_dir() / "config.toml"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists() or tomllib is None:
        return {}
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def save_config(data: dict[str, Any]) -> Path:
    init_home()
    path = config_path()
    path.write_text(tomli_w.dumps(data))
    return path


def update_llm(backend: str) -> None:
    """Set the user's preferred LLM backend."""

    cfg = load_config()
    cfg.setdefault("llm", {})["preferred"] = backend
    save_config(cfg)


def update_mode(mode: str) -> None:
    """Set the user's chosen mode — 'automation' or 'adhoc'."""

    cfg = load_config()
    cfg.setdefault("setup", {})["mode"] = mode
    save_config(cfg)


def mark_wizard_complete() -> None:
    cfg = load_config()
    cfg.setdefault("setup", {})["onboarded"] = True
    save_config(cfg)


def is_onboarded() -> bool:
    return bool(load_config().get("setup", {}).get("onboarded"))


__all__ = [
    "config_path",
    "is_onboarded",
    "load_config",
    "mark_wizard_complete",
    "save_config",
    "update_llm",
    "update_mode",
]
