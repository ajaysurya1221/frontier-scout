"""Mission Control tab registry.

Each tab module under this package exports one widget class that can be
mounted inside a Textual ``TabPane``. The registry below names every tab
and the title shown in the tab strip; ``setup_app`` consumes it to build
the ``TabbedContent`` host.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TabSpec:
    slug: str
    title: str
    description: str


TAB_REGISTRY: list[TabSpec] = [
    TabSpec("scout", "⌖ Scout", "Discover the latest AI releases that fit this repo"),
    TabSpec("trials", "⚡ Trials", "Run and review try-before-trust receipts"),
    TabSpec("receipts", "📋 Receipts", "Local evidence ledger for evaluated tools"),
    TabSpec("guard", "🛡 Guard", "Local policy checks for risky adoption evidence"),
    TabSpec("reports", "📊 Reports", "Render static radar reports"),
    TabSpec("packs", "🧰 Packs", "Living Scout Packs — seeds, candidates, discovery"),
    TabSpec("deps", "📦 Deps", "Dependency intelligence — find meaningful upgrades"),
    TabSpec("incident", "🪐 Incident", "Engineering Scout incident-forensics demo"),
    TabSpec("settings", "⚙ Settings", "Policy, environment, and system state"),
]

TAB_SLUGS = [spec.slug for spec in TAB_REGISTRY]
DEFAULT_TAB = "scout"


def tab_by_slug(slug: str) -> TabSpec | None:
    for spec in TAB_REGISTRY:
        if spec.slug == slug:
            return spec
    return None
