"""Runtime configuration for local demos and tests."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from .budgets import Budget


class PlatformConfig(BaseModel):
    home: Path
    actor_id: str = "user:local"
    default_model: str = "local-deterministic"
    budget: Budget = Budget()


def load_config() -> PlatformConfig:
    home = Path(os.environ.get("FRONTIER_SCOUT_HOME", "~/.frontier-scout")).expanduser()
    return PlatformConfig(home=home)

