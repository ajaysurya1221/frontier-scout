"""Splash screen rendered before the main mission-control UI.

Static composition only — concentric radar rings, a sweep wedge, three
colored pings, the FRONTIER · SCOUT wordmark, and a "press any key"
footer. Auto-dismisses after 1.4 seconds or on any keypress.
"""

from __future__ import annotations

import math
from typing import ClassVar

from rich.align import Align
from rich.console import Group
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from frontier_scout import __version__


_AUTO_DISMISS_SECONDS = 1.4


def _render_radar() -> Group:
    """Return a Rich renderable for the radar art.

    Three concentric rings of muted dots, a quadrant sweep wedge tinted
    mint, the center marker, and three colored pings (mint, gold, blue)
    placed at fixed offsets — matching the designer's HTML splash.
    """

    # 21x11 grid (cols x rows) gives a nicely proportioned terminal circle.
    cols, rows = 21, 11
    cx, cy = cols // 2, rows // 2
    grid: list[list[str]] = [[" "] * cols for _ in range(rows)]
    style: list[list[str]] = [["dim white"] * cols for _ in range(rows)]

    # Three rings drawn at radii proportional to the box dimensions.
    radii = [5.0, 3.2, 1.6]
    for r in radii:
        steps = max(28, int(2 * math.pi * r * 1.8))
        for step in range(steps):
            theta = 2 * math.pi * step / steps
            # Terminal cells are taller than wide -> compress y.
            x = cx + r * math.cos(theta)
            y = cy + r * math.sin(theta) * 0.55
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < cols and 0 <= yi < rows and grid[yi][xi] == " ":
                grid[yi][xi] = "·"
                style[yi][xi] = "#25405c"

    # Sweep wedge — light mint dots in the top-right quadrant.
    for r in (1.2, 2.0, 2.8, 3.6, 4.4):
        for step in range(0, 12):
            theta = math.radians(270 + step * 7)  # arc sweeping from up to right
            x = cx + r * math.cos(theta)
            y = cy + r * math.sin(theta) * 0.55
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < cols and 0 <= yi < rows and grid[yi][xi] == " ":
                grid[yi][xi] = "·"
                style[yi][xi] = "#24d6a8"

    # Center.
    grid[cy][cx] = "◉"
    style[cy][cx] = "bold #24d6a8"

    # Pings — placed deliberately, matching the SVG's positions.
    pings = [
        (cx + 4, cy - 2, "#24d6a8"),
        (cx - 3, cy + 2, "#e3c26f"),
        (cx + 5, cy + 1, "#7aa6ff"),
    ]
    for px, py, color in pings:
        if 0 <= px < cols and 0 <= py < rows:
            grid[py][px] = "●"
            style[py][px] = f"bold {color}"

    lines = []
    for y in range(rows):
        line = Text()
        for x in range(cols):
            line.append(grid[y][x], style[y][x])
        lines.append(line)
    return Group(*lines)


class SplashScreen(Screen[None]):
    """One-frame brand splash that auto-dismisses into mission control."""

    DEFAULT_CSS = """
    SplashScreen {
        background: #0b1117;
        align: center middle;
    }

    SplashScreen #splash-frame {
        width: auto;
        height: auto;
        padding: 1 4;
        border: round #25405c;
        background: #0d1622;
    }

    SplashScreen #splash-radar {
        width: 21;
        height: 11;
        content-align: center middle;
    }

    SplashScreen #splash-wordmark {
        margin-top: 1;
        color: #d9f7ff;
        text-style: bold;
        text-align: center;
    }

    SplashScreen #splash-tagline {
        color: #6e8aa1;
        text-align: center;
    }

    SplashScreen #splash-footer {
        margin-top: 1;
        color: #25405c;
        text-align: center;
    }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "dismiss", "Skip", show=False),
        Binding("space", "dismiss", "Skip", show=False),
        Binding("enter", "dismiss", "Skip", show=False),
        Binding("q", "dismiss", "Skip", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-frame"):
            yield Static(Align.center(_render_radar(), vertical="middle"), id="splash-radar")
            yield Static(f"FRONTIER · SCOUT  v{__version__}", id="splash-wordmark")
            yield Static("try-before-trust radar", id="splash-tagline")
            yield Static("press any key — auto-continue", id="splash-footer")

    def __init__(self) -> None:
        super().__init__()
        self._dismissed = False

    def on_mount(self) -> None:
        self.set_timer(_AUTO_DISMISS_SECONDS, self._auto_dismiss)

    def _auto_dismiss(self) -> None:
        self._safe_dismiss()

    def action_dismiss(self) -> None:  # type: ignore[override]
        self._safe_dismiss()

    def on_key(self, event: events.Key) -> None:
        # Any unbound key dismisses too.
        event.stop()
        self._safe_dismiss()

    def _safe_dismiss(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        self.dismiss(None)
