"""Single source of truth for provider selection (which provider, and why).

Layered on the low-level ``available_providers()`` / ``resolve_provider()``
primitives so BOTH the TUI and the headless scan resolve identically — the UI
indicator can never disagree with what a scan actually used.

Ladder (highest first): explicit flag/env > saved preference > auto-detect.
When >1 provider is available, no preference is saved, and the caller is
interactive (the TUI), ``select()`` returns ``must_ask`` so the UI can prompt
once and remember. Headless callers never get ``must_ask``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from frontier_scout import preferences

from . import available_providers, resolve_provider
from .base import LLMProvider


@dataclass(frozen=True)
class Selection:
    name: str   # "" when reason is "must_ask" or "none"
    reason: str  # "flag" | "preference" | "auto" | "must_ask" | "none"


def select(*, cli_override: str | None = None, interactive: bool = False) -> Selection:
    """Resolve which provider to use and why (see module docstring for the ladder).

    A flag value (``cli_override`` / ``FRONTIER_SCOUT_PROVIDER``) is returned
    verbatim with reason ``"flag"`` and is NOT validated here — downstream
    ``current_provider()`` -> ``resolve_provider()`` validates it and raises the
    canonical ``ProviderUnavailable`` if it is unknown or unusable. This keeps
    one validation path and one error message.
    """
    pinned = (cli_override or os.environ.get("FRONTIER_SCOUT_PROVIDER") or "").strip().lower()
    if pinned:
        return Selection(pinned, "flag")
    avail = available_providers()
    pref = preferences.preferred_provider()
    if pref and pref in avail:
        return Selection(pref, "preference")
    if interactive and len(avail) > 1:
        return Selection("", "must_ask")
    if avail:
        return Selection(avail[0], "auto")
    return Selection("", "none")


_CACHED: LLMProvider | None = None  # GIL-protected; a concurrent first build is benign


def current_provider() -> LLMProvider:
    """The built provider for this process, cached. Honors ``FRONTIER_SCOUT_PROVIDER`` env + saved preference.

    Raises ``ProviderUnavailable`` (with the ``--demo`` hint) when nothing is
    usable, exactly as ``resolve_provider()`` does today.
    """
    global _CACHED
    if _CACHED is None:
        chosen = select()
        _CACHED = resolve_provider(chosen.name or None)
    return _CACHED


def reset_provider() -> None:
    """Drop the cache so a runtime switch takes effect on the next scan."""
    global _CACHED
    _CACHED = None
