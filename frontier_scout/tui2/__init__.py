"""The Briefing TUI (v1.5.0) — a calm, wizard-style scout interface.

Built alongside the classic ``tui/`` and shipped as the default. The classic UI
stays reachable for one release via ``FRONTIER_SCOUT_UI=classic`` / ``--ui classic``.

Public entry point: :func:`run_briefing`.
"""

from __future__ import annotations

from frontier_scout.tui2.app import BriefingApp, run_briefing
from frontier_scout.tui2.state import AppState, Concern, Finding

__all__ = ["AppState", "BriefingApp", "Concern", "Finding", "run_briefing"]
