"""Mission Control tab registry — v1.2 simplified to Scout + Settings.

Every other surface (Incident, Packs, Trials, Receipts, Reports, Guard,
Deps) lives on the CLI; the TUI focuses on the scout-and-act flow.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TabSpec:
    slug: str
    title: str
    description: str


TAB_REGISTRY: list[TabSpec] = [
    TabSpec("scout", "⌖ Scout", "Discover and act on AI tools + dependency upgrades that fit your repo"),
    TabSpec("settings", "⚙ Settings", "Policy, environment, automation, and history"),
]

TAB_SLUGS = [spec.slug for spec in TAB_REGISTRY]
DEFAULT_TAB = "scout"


def tab_by_slug(slug: str) -> TabSpec | None:
    for spec in TAB_REGISTRY:
        if spec.slug == slug:
            return spec
    return None
