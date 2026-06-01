"""Radar — the signature character-grid radar with a rotating sweep + pings.

A faithful port of the design bundle's ``kit.jsx`` radar: a monospace grid of
cells where a beam rotates, ring dots light up as the beam passes, and coloured
pings (one per verdict tone) glow when the beam crosses them. It is all
character cells on purpose, so it renders identically in any terminal.

The widget animates via ``set_interval`` (independent of Textual's animation
system, which the Briefing disables for determinism). If the interval never
fires — e.g. in a head-less test — the first static frame is still drawn on
mount, so the radar is never blank.
"""

from __future__ import annotations

import math

from rich.text import Text
from textual.widgets import Static

# Verdict tones → colours, matching the theme palette.
_TONE = {
    "adopt": "#24d6a8",
    "trial": "#7aa6ff",
    "assess": "#e3c26f",
    "hold": "#6e8aa1",
}
_MINT = "#24d6a8"
_MINT_DIM = "#1b9a7a"

# A tasteful default constellation: one ping per verdict tone, spread around.
DEFAULT_PINGS: tuple[dict, ...] = (
    {"angle": 38, "radius": 0.66, "tone": "adopt"},
    {"angle": 145, "radius": 0.92, "tone": "trial"},
    {"angle": 222, "radius": 0.48, "tone": "assess"},
    {"angle": 305, "radius": 0.78, "tone": "hold"},
)


class Radar(Static):
    """A rotating character-grid radar. Purely decorative, never interactive."""

    def __init__(
        self,
        *,
        rows: int = 13,
        cols: int = 29,
        pings: tuple[dict, ...] = DEFAULT_PINGS,
        running: bool = True,
        speed: float = 9.0,
        id: str | None = None,  # noqa: A002 - Textual widget convention
        classes: str | None = None,
    ) -> None:
        super().__init__("", id=id, classes=classes)
        self._rows = rows
        self._cols = cols
        self._pings = pings
        self._running = running
        self._speed = speed
        self._sweep = 0.0

    def on_mount(self) -> None:
        self.update(self._frame())
        if self._running:
            self.set_interval(0.08, self._tick)

    def _tick(self) -> None:
        self._sweep = (self._sweep + self._speed) % 360.0
        self.update(self._frame())

    def _frame(self) -> Text:
        rows, cols = self._rows, self._cols
        cx = (cols - 1) / 2
        cy = (rows - 1) / 2
        max_r = cy - 0.2
        ring_r = (max_r * 0.34, max_r * 0.66, max_r * 0.98)
        sweep = self._sweep

        def behind(ang: float) -> float:
            return ((sweep - ang) % 360 + 360) % 360

        text = Text(justify="left")
        for r in range(rows):
            for c in range(cols):
                ex = (c - cx) * 0.5  # cells are ~half as wide as tall
                ey = r - cy
                rad = math.hypot(ex, ey)
                ch, style = " ", None
                if rad <= max_r + 0.5:
                    ang = math.degrees(math.atan2(ey, ex))
                    b = behind(ang)
                    on_ring = any(abs(rad - rr) < 0.42 for rr in ring_r)
                    ping = self._ping_at(rad, ang, max_r)
                    if rad < 0.9:
                        ch, style = "◉", f"bold {_MINT}"
                    elif ping is not None:
                        pb = behind(ping["angle"])
                        glow = pb < 90
                        color = _TONE.get(ping["tone"], _MINT)
                        ch = "●"
                        style = color if glow else f"dim {color}"
                    elif b < 6:  # leading beam line
                        ch, style = "·", _MINT
                    elif on_ring and b < 80:  # wedge-lit ring dots
                        ch, style = "·", _MINT_DIM
                    elif on_ring:
                        ch, style = "·", f"dim {_MINT_DIM}"
                text.append(ch, style=style)
            if r != rows - 1:
                text.append("\n")
        return text

    def _ping_at(self, rad: float, ang: float, max_r: float) -> dict | None:
        a_norm = (ang % 360 + 360) % 360
        for p in self._pings:
            pr = p.get("radius", 0.7) * max_r
            pang = (p["angle"] % 360 + 360) % 360
            da = abs(a_norm - pang)
            da = min(da, 360 - da)
            if abs(rad - pr) < 0.85 and da < 11:
                return p
        return None
