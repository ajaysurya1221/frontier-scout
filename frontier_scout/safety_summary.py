"""High-risk capability flags, reused by the agent-policy decision engine.

A capability in :data:`RISKY_FLAGS` is one that gates an action behind explicit
human review (static analysis only — nothing is executed). (The former pack
safety-summary builder/renderer that lived here was removed with the packs flow.)
"""

from __future__ import annotations

RISKY_FLAGS = frozenset({"write", "shell", "credential", "network"})
