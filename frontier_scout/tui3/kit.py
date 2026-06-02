"""Mission Control (tui3) — render kit: glyphs, breakpoints, palette tokens.

Pure, dependency-light helpers shared across the Mission Control screens. No
Textual imports here so this module stays unit-testable in isolation.

The design ships two glyph sets (unicode default + ASCII fallback) and two color
modes (color + mono). Both are first-class per the responsive requirement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Palette (mirrors the design CSS :root, ADOPT=mint TRIAL=gold ASSESS=blue HOLD=red)
PALETTE = {
    "bg": "#0b1117",
    "panel": "#0d1622",
    "panel2": "#0f1c2b",
    "card": "#0c1a27",
    "field": "#070d14",
    "border": "#25405c",
    "border_soft": "#1a2c41",
    "border_faint": "#152232",
    "mint": "#24d6a8",
    "mint_dim": "#1b9a7a",
    "bright": "#d9f7ff",
    "text": "#a9bccd",
    "muted": "#6e8aa1",
    "blue": "#7aa6ff",
    "gold": "#e3c26f",
    "red": "#ff6b6b",
}

# ── Glyph sets ───────────────────────────────────────────────────────────────
UNI = {
    "bar_full": "█", "bar_empty": "░", "dot": "●", "ring": "○", "diamond": "◆",
    "arrow": "→", "check": "✓", "cross": "✕", "tri": "▸", "chev": "›",
    "radar_core": "◉", "pip": "·", "bullet": "▪", "vbar": "│",
    "enter": "⏎", "lr": "←→", "ud": "↑↓", "cmd": "⌘",
}
ASCII = {
    "bar_full": "#", "bar_empty": ".", "dot": "*", "ring": "o", "diamond": "<>",
    "arrow": "->", "check": "v", "cross": "x", "tri": ">", "chev": ">",
    "radar_core": "(o)", "pip": ".", "bullet": "-", "vbar": "|",
    "enter": "ent", "lr": "<>", "ud": "^v", "cmd": "^",
}


def glyphs(unicode: bool = True) -> dict[str, str]:
    """Return the active glyph map."""
    return UNI if unicode else ASCII


# Fold every unicode glyph (plus a few extras used in static help/overlay text)
# to its ASCII equivalent. Applied centrally in MissionControlApp._paint when
# unicode mode is off, so stray glyphs (e.g. in modals) still degrade cleanly.
_ASCIIFY = {
    "█": "#", "░": ".", "●": "*", "○": "o", "◆": "<>", "→": "->", "←": "<",
    "↑": "^", "↓": "v", "↔": "<>", "✓": "v", "✕": "x", "▸": ">", "›": ">",
    "◉": "(o)", "·": ".", "▪": "-", "│": "|", "⏎": "ent", "⌘": "^", "…": "...",
    "–": "-", "—": "--",
}


def asciify(s: str) -> str:
    """Fold unicode glyphs to ASCII (the unicode→ASCII fallback for stray glyphs)."""
    for u, a in _ASCIIFY.items():
        if u in s:
            s = s.replace(u, a)
    return s


_TAG = re.compile(r"\[([^\[\]]*)\]")
_STYLES = frozenset(
    {"b", "bold", "i", "italic", "u", "underline", "s", "strike",
     "strikethrough", "d", "dim", "r", "reverse", "blink"}
)


def mono(markup: str) -> str:
    """Strip color from Rich console markup, preserving structural styles.

    Colors (``#rrggbb``, named colors, ``on <color>`` backgrounds) are removed;
    structural styles (bold/dim/reverse/…) are kept so hierarchy survives in a
    no-color terminal. The result is always BALANCED valid markup — a closing
    ``[/]`` is emitted only for an opener we kept — so Rich never raises on it.
    """
    out: list[str] = []
    stack: list[bool] = []  # True if the opener at this depth was emitted
    pos = 0
    for m in _TAG.finditer(markup):
        out.append(markup[pos:m.start()])
        pos = m.end()
        inner = m.group(1).strip()
        if inner == "" or inner.startswith("/"):  # a closer
            if stack and stack.pop():
                out.append("[/]")
            continue
        kept: list[str] = []
        skip = False
        for tok in inner.split():
            if skip:  # token consumed by a preceding "on"
                skip = False
                continue
            if tok == "on":
                skip = True
                continue
            if tok.startswith("#"):
                continue
            if tok in _STYLES:
                kept.append(tok)
            # bare named colors are dropped
        if kept:
            out.append(f"[{' '.join(kept)}]")
            stack.append(True)
        else:
            stack.append(False)
    out.append(markup[pos:])
    return "".join(out)


# ── Verdict metadata ─────────────────────────────────────────────────────────
VERDICT_META = {
    "adopt": ("ADOPT", "mint"),
    "trial": ("TRIAL", "gold"),
    "assess": ("ASSESS", "blue"),
    "hold": ("HOLD", "red"),
}


def verdict_label(verdict: str) -> str:
    return VERDICT_META.get(verdict, VERDICT_META["assess"])[0]


def verdict_tone(verdict: str) -> str:
    return VERDICT_META.get(verdict, VERDICT_META["assess"])[1]


# Fit / risk word → tone. fit: high=good; risk: low=good (inverted).
def fit_tone(level: str) -> str:
    return {"high": "mint", "medium": "gold", "low": "red"}.get(level, "muted")


def risk_tone(level: str) -> str:
    return {"low": "mint", "medium": "gold", "high": "red"}.get(level, "muted")


def sev_tone(severity: str) -> str:
    return {"high": "red", "medium": "gold", "low": "muted"}.get(severity, "muted")


# ── Breakpoints (by cols×rows) — the responsive backbone ─────────────────────
@dataclass(frozen=True)
class Breakpoint:
    name: str          # tiny | micro | narrow | mid | wide
    rail: bool         # use the left rail (vs top tab strip)
    rail_compact: bool  # rail shows icons+numbers only
    numeric_tabs: bool  # tab strip shows numbers only
    master_detail: bool  # Scout shows list+detail side by side
    show_hero: bool     # Scout hero band has room


# Minimum usable terminal — below this we show the "resize to continue" floor.
MIN_COLS = 36
MIN_ROWS = 11


def breakpoint_for(cols: int, rows: int) -> Breakpoint:
    """Classify a terminal size into a responsive breakpoint.

    Mirrors the design's breakpointFor():
      tiny   cols<36 or rows<11  → floor
      micro  cols<58             → numeric tab strip, single column
      narrow cols<82             → labelled tab strip, single column
      mid    cols<116            → compact rail + main
      wide   >=116               → full rail + master/detail
    """
    if cols < MIN_COLS or rows < MIN_ROWS:
        return Breakpoint("tiny", False, False, False, False, False)
    if cols < 58:
        return Breakpoint("micro", False, False, True, False, rows >= 20)
    if cols < 82:
        return Breakpoint("narrow", False, False, False, False, rows >= 22)
    if cols < 116:
        return Breakpoint("mid", True, True, False, False, rows >= 26)
    return Breakpoint("wide", True, False, False, True, rows >= 24)


def bar(value: float, maximum: float, width: int, *, unicode: bool = True) -> tuple[str, str]:
    """Return (filled, empty) glyph runs for a fixed-width progress bar."""
    g = glyphs(unicode)
    frac = 0.0 if maximum <= 0 else max(0.0, min(1.0, value / maximum))
    filled = round(frac * width)
    return g["bar_full"] * filled, g["bar_empty"] * max(0, width - filled)


def pct(value: float, maximum: float) -> int:
    if maximum <= 0:
        return 0
    return round(max(0.0, min(1.0, value / maximum)) * 100)
