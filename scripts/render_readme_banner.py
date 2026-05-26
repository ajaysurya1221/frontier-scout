"""Render the animated README mission-control banner.

The renderer is deterministic so the README hero can be regenerated without
screen recording tools or SaaS design software. Layout is expressed as named
constants and small helpers; motion is restrained (one cycling pipeline step,
one travelling signal dot, gentle source pulses) so the result reads as a calm
product radar rather than a strobing graph.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"
SCRATCH_DIR = ROOT / ".scratch" / "banner"
GIF_PATH = ASSET_DIR / "frontier-scout-mission-control.gif"
POSTER_PATH = ASSET_DIR / "frontier-scout-mission-control-poster.png"

W, H = 1600, 900
FRAME_COUNT = 40
FRAME_MS = 250  # 40 * 250ms = 10.0s loop

# Palette (light, high-contrast, technical product feel)
BG_TOP = (247, 251, 255)
BG_BOTTOM = (235, 243, 250)
INK = "#0b1220"
INK_SOFT = "#475467"
INK_MUTED = "#7d8a9c"
RULE = "#dbe6f0"
PANEL_FILL = "#ffffff"
PANEL_BORDER = "#d6e3ee"
PANEL_HEADER = "#f3f8fc"
ACCENT_TEAL = "#0f766e"
ACCENT_TEAL_SOFT = "#d1faf2"
ACCENT_BLUE = "#155eef"
ACCENT_BLUE_SOFT = "#e0ecff"
ACCENT_AMBER = "#b45309"
ACCENT_AMBER_SOFT = "#fef3c7"
ACCENT_AMBER_BORDER = "#f4c674"
ACCENT_ROSE = "#be1241"
ACCENT_VIOLET = "#6d28d9"

# Layout constants (px, top-left origin)
OUTER = (40, 36, 1560, 864)
OUTER_RADIUS = 32

HEADER_X = 72
HEADER_TITLE_Y = 92
HEADER_LABEL_Y = 60
HEADER_SUB_Y = 152
PILL_Y1 = 60
PILL_Y2 = 110

# Three main panels share a baseline (top = 220, bottom = 686)
PANEL_TOP = 224
PANEL_BOTTOM = 668
PANEL_HEADER_H = 70
PANEL_RADIUS = 22

LEFT_PANEL = (60, PANEL_TOP, 446, PANEL_BOTTOM)
CENTER_PANEL = (466, PANEL_TOP, 1158, PANEL_BOTTOM)
RIGHT_PANEL = (1178, PANEL_TOP, 1540, PANEL_BOTTOM)

EVIDENCE_STRIP = (60, 692, 1540, 832)


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    fonts = _fonts()

    frames: list[Image.Image] = []
    for index in range(FRAME_COUNT):
        image = _draw_frame(index, fonts)
        (SCRATCH_DIR / f"frame-{index:03d}.png").write_bytes(_png_bytes(image))
        frames.append(image.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))

    poster = _draw_frame(0, fonts)
    poster.save(POSTER_PATH, optimize=True)
    frames[0].save(
        GIF_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {GIF_PATH.relative_to(ROOT)} ({GIF_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"Wrote {POSTER_PATH.relative_to(ROOT)} ({POSTER_PATH.stat().st_size / 1024:.1f} KB)")


# -------- frame composition --------------------------------------------------


def _draw_frame(index: int, fonts: dict[str, ImageFont.ImageFont]) -> Image.Image:
    phase = index / FRAME_COUNT  # [0, 1)
    img = _make_background()
    draw = ImageDraw.Draw(img)
    _draw_outer_frame(draw)
    _draw_header(draw, fonts, phase)
    _draw_scout_panel(draw, fonts, phase)
    _draw_pipeline_panel(draw, fonts, phase)
    _draw_dossier_panel(draw, fonts, phase)
    _draw_evidence_strip(draw, fonts, phase)
    return img


def _make_background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    # Vertical gradient
    for y in range(H):
        t = y / (H - 1)
        r = round(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = round(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = round(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    # Subtle dotted grid for the "technical" feel — much lighter than the
    # previous bold lines so it never competes with content.
    for x in range(80, W, 48):
        for y in range(80, H, 48):
            draw.point((x, y), fill="#e2ecf3")
    return img


def _draw_outer_frame(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle(OUTER, radius=OUTER_RADIUS, outline="#cfdeeb", width=2)


def _draw_header(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    # Eyebrow with status dot
    glow = 0.55 + 0.45 * math.sin(phase * 2 * math.pi)
    draw.ellipse((HEADER_X, HEADER_LABEL_Y + 6, HEADER_X + 12, HEADER_LABEL_Y + 18),
                 fill=_blend(ACCENT_TEAL_SOFT, ACCENT_TEAL, glow))
    draw.text((HEADER_X + 22, HEADER_LABEL_Y + 2), "FRONTIER SCOUT · MISSION CONTROL",
              font=fonts["eyebrow"], fill=ACCENT_TEAL)

    draw.text((HEADER_X, HEADER_TITLE_Y), "Personalized AI adoption mission control",
              font=fonts["title"], fill=INK)
    draw.text((HEADER_X, HEADER_SUB_Y),
              "Scout what's trending, map it to your repos, and prove safety before trust.",
              font=fonts["sub"], fill=INK_SOFT)

    # Right-side pills
    _pill(draw, (1308, PILL_Y1, 1516, PILL_Y1 + 38), "local-first",
          fill=ACCENT_TEAL_SOFT, text_color=ACCENT_TEAL, font=fonts["pill"])
    _pill(draw, (1308, PILL_Y2, 1516, PILL_Y2 + 38), "no auto-install",
          fill=ACCENT_AMBER_SOFT, text_color=ACCENT_AMBER, font=fonts["pill"])
    _pill(draw, (1308, PILL_Y2 + 50, 1516, PILL_Y2 + 88), "try before trust",
          fill=ACCENT_BLUE_SOFT, text_color=ACCENT_BLUE, font=fonts["pill"])

    # Thin separator under header
    draw.line((72, 198, W - 72, 198), fill=RULE, width=1)


# -------- left panel: scout sweep -------------------------------------------


def _draw_scout_panel(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    _panel(draw, LEFT_PANEL, "Scout sweep", "public signals to local fingerprint", fonts)
    x1, y1, x2, _ = LEFT_PANEL

    sources = [
        ("GitHub Trending", "trending repos & releases"),
        ("MCP servers", "modelcontextprotocol registry"),
        ("Hacker News", "front-page launches"),
        ("Hugging Face", "model & dataset drops"),
        ("Model drops", "frontier vendor releases"),
    ]
    list_top = y1 + PANEL_HEADER_H + 14
    row_h = 46
    list_x1 = x1 + 22
    list_x2 = x2 - 22

    # Highlighted source cycles slowly (one full cycle per loop)
    active_idx = int(phase * len(sources)) % len(sources)

    for i, (label, hint) in enumerate(sources):
        y = list_top + i * row_h
        active = i == active_idx
        bg = ACCENT_TEAL_SOFT if active else "#f6fafd"
        border = ACCENT_TEAL if active else "#e1ecf3"
        draw.rounded_rectangle((list_x1, y, list_x2, y + row_h - 6),
                               radius=12, fill=bg, outline=border, width=1)
        # Status dot
        dot_color = ACCENT_TEAL if active else "#a6b6c4"
        draw.ellipse((list_x1 + 16, y + 14, list_x1 + 28, y + 26), fill=dot_color)
        draw.text((list_x1 + 42, y + 6), label, font=fonts["row_title"], fill=INK)
        draw.text((list_x1 + 42, y + 24), hint, font=fonts["row_hint"], fill=INK_MUTED)
        if active:
            # Right-edge arrow indicating signal forwarded to pipeline
            ax = list_x2 - 18
            ay = y + (row_h - 6) // 2
            draw.polygon([(ax - 8, ay - 6), (ax, ay), (ax - 8, ay + 6)], fill=ACCENT_TEAL)

    # Repo fingerprint section
    fp_top = list_top + len(sources) * row_h + 14
    draw.text((list_x1, fp_top), "REPO FINGERPRINT", font=fonts["section"], fill=ACCENT_TEAL)
    draw.text((list_x1, fp_top + 20),
              "what this codebase actually uses", font=fonts["row_hint"], fill=INK_MUTED)

    chips = ["Python", "Docker", "AGENTS.md", "GitHub Actions", "MCP config"]
    chip_y = fp_top + 50
    cx = list_x1
    for chip in chips:
        cw = _text_width(fonts["chip"], chip) + 24
        if cx + cw > list_x2:
            cx = list_x1
            chip_y += 38
        draw.rounded_rectangle((cx, chip_y, cx + cw, chip_y + 30),
                               radius=14, fill="#ecf7f3", outline="#b6dccf", width=1)
        draw.text((cx + 12, chip_y + 7), chip, font=fonts["chip"], fill=ACCENT_TEAL)
        cx += cw + 8


# -------- center panel: adoption pipeline -----------------------------------


def _draw_pipeline_panel(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    _panel(draw, CENTER_PANEL, "Adoption pipeline",
           "repo  ›  fit  ›  tool  ›  permission  ›  receipt", fonts)
    x1, y1, x2, y2 = CENTER_PANEL

    steps = [
        ("01", "Repo profile", "Python · Docker · MCP", ACCENT_BLUE, ACCENT_BLUE_SOFT),
        ("02", "Fit match", "stack + agent signals", ACCENT_TEAL, ACCENT_TEAL_SOFT),
        ("03", "Tool candidate", "MCP · model · plugin", ACCENT_TEAL, ACCENT_TEAL_SOFT),
        ("04", "Permission map", "net · shell · fs", ACCENT_AMBER, ACCENT_AMBER_SOFT),
        ("05", "Trial receipt", "sandbox · report-only", ACCENT_VIOLET, "#ede4fb"),
    ]
    inner_x1 = x1 + 24
    inner_x2 = x2 - 24
    inner_w = inner_x2 - inner_x1
    card_w = 108
    card_h = 130
    gap = (inner_w - card_w * len(steps)) // (len(steps) - 1)
    card_top = y1 + PANEL_HEADER_H + 22
    card_bot = card_top + card_h
    rail_y = card_bot + 38  # below cards, clearly visible

    centers: list[tuple[int, int]] = []
    for i, _ in enumerate(steps):
        cx = inner_x1 + i * (card_w + gap) + card_w // 2
        centers.append((cx, (card_top + card_bot) // 2))

    # Active card cycles in lockstep with the signal
    active_idx = min(len(steps) - 1, int(phase * len(steps)) % len(steps))

    # Cards
    for i, (num, title, detail, accent, accent_soft) in enumerate(steps):
        cx, cy = centers[i]
        active = i == active_idx
        box = (cx - card_w // 2, card_top, cx + card_w // 2, card_bot)
        fill = accent_soft if active else "#ffffff"
        border = accent if active else "#dce6ef"
        border_w = 2 if active else 1
        if active:
            for d in range(4, 0, -1):
                draw.rounded_rectangle((box[0] + d, box[1] + d + 2, box[2] + d, box[3] + d + 2),
                                       radius=14, outline="#e6eff7")
        draw.rounded_rectangle(box, radius=14, fill=fill, outline=border, width=border_w)
        # Step number pill
        draw.rounded_rectangle((cx - 22, box[1] + 10, cx + 22, box[1] + 32),
                               radius=11, fill=accent, outline=None)
        nw = _text_width(fonts["step_num"], num)
        draw.text((cx - nw / 2, box[1] + 13), num, font=fonts["step_num"], fill="#ffffff")
        # Title
        _draw_centered_wrapped(draw, title, fonts["step_title"],
                               cx, box[1] + 46, card_w - 12, INK, line_height=20)
        # Detail
        _draw_centered_wrapped(draw, detail, fonts["step_detail"],
                               cx, box[3] - 36, card_w - 12, INK_MUTED, line_height=16)
        # Connector stub from card bottom down to rail
        stub_color = accent if active else "#cdd9e3"
        draw.line((cx, box[3], cx, rail_y - 8), fill=stub_color, width=2)

    # Rail
    rail_left, rail_right = centers[0][0], centers[-1][0]
    draw.line((rail_left, rail_y, rail_right, rail_y), fill="#d4e0ea", width=2)
    # Tick at each step
    for cx, _ in centers:
        draw.ellipse((cx - 5, rail_y - 5, cx + 5, rail_y + 5),
                     fill="#ffffff", outline="#9bb1c2", width=2)
    # Highlight the active tick
    acx = centers[active_idx][0]
    draw.ellipse((acx - 7, rail_y - 7, acx + 7, rail_y + 7),
                 fill=ACCENT_TEAL, outline=ACCENT_TEAL, width=2)

    # Travelling signal — moves across rail once per loop, eased.
    travel_t = _smoothstep((phase * 1.0) % 1.0)
    signal_x = int(rail_left + (rail_right - rail_left) * travel_t)
    # Glow trail behind signal
    for offset in range(48, 0, -6):
        alpha_ratio = 1 - offset / 48
        col = _blend("#d4e0ea", ACCENT_TEAL, alpha_ratio * 0.65)
        draw.line((max(rail_left, signal_x - offset), rail_y, signal_x, rail_y),
                  fill=col, width=2)
    # Halo + dot
    draw.ellipse((signal_x - 10, rail_y - 10, signal_x + 10, rail_y + 10),
                 fill=ACCENT_TEAL_SOFT, outline=None)
    draw.ellipse((signal_x - 5, rail_y - 5, signal_x + 5, rail_y + 5),
                 fill=ACCENT_TEAL)

    # Chevron marker between cards (on the rail, small)
    for i in range(len(steps) - 1):
        ax = (centers[i][0] + centers[i + 1][0]) // 2
        chev_color = ACCENT_TEAL if i == active_idx else "#b6c5d3"
        draw.polygon([(ax - 5, rail_y - 6), (ax + 5, rail_y), (ax - 5, rail_y + 6)],
                     fill=chev_color)

    # Highlight callout under the pipeline
    callout_y = y2 - 92
    draw.rounded_rectangle((inner_x1, callout_y, inner_x2, callout_y + 68),
                           radius=14, fill="#fff8ec", outline=ACCENT_AMBER_BORDER, width=1)
    # Inline icon (sparkle/star-ish)
    icon_cx, icon_cy = inner_x1 + 30, callout_y + 34
    draw.polygon([
        (icon_cx, icon_cy - 12), (icon_cx + 4, icon_cy - 4),
        (icon_cx + 12, icon_cy), (icon_cx + 4, icon_cy + 4),
        (icon_cx, icon_cy + 12), (icon_cx - 4, icon_cy + 4),
        (icon_cx - 12, icon_cy), (icon_cx - 4, icon_cy - 4),
    ], fill=ACCENT_AMBER)
    draw.text((inner_x1 + 56, callout_y + 12),
              "Highlighted candidate", font=fonts["section"], fill=ACCENT_AMBER)
    draw.text((inner_x1 + 56, callout_y + 34),
              "modelcontextprotocol/servers · matches agent + MCP signals in this repo",
              font=fonts["row_hint"], fill="#5b3a09")


# -------- right panel: adoption dossier --------------------------------------


def _draw_dossier_panel(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    _panel(draw, RIGHT_PANEL, "Adoption dossier", "try-before-trust verdict", fonts)
    x1, y1, x2, y2 = RIGHT_PANEL

    inner_x1 = x1 + 22
    inner_x2 = x2 - 22

    # Verdict card
    verdict_top = y1 + PANEL_HEADER_H + 14
    verdict_bot = verdict_top + 96
    draw.rounded_rectangle((inner_x1, verdict_top, inner_x2, verdict_bot),
                           radius=18, fill="#fff7ed", outline=ACCENT_AMBER_BORDER, width=2)
    draw.text((inner_x1 + 18, verdict_top + 14),
              "VERDICT", font=fonts["section"], fill=ACCENT_AMBER)
    # Stamp pulses gently
    stamp_glow = 0.7 + 0.3 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi))
    stamp_color = _blend("#d97706", "#9a3412", stamp_glow)
    draw.text((inner_x1 + 18, verdict_top + 36), "TRIAL",
              font=fonts["stamp"], fill=stamp_color)
    # Small "approved with conditions" tag
    tag_x = inner_x1 + 18
    tag_y = verdict_top + 78
    tag_w = 220
    draw.rounded_rectangle((tag_x, tag_y, tag_x + tag_w, tag_y + 16),
                           radius=8, fill=ACCENT_AMBER_BORDER)
    draw.text((tag_x + 8, tag_y + 1), "approved with conditions",
              font=fonts["tag"], fill="#5b3a09")

    # Metadata rows
    rows = [
        ("category", "MCP server", ACCENT_BLUE),
        ("fit", "high", ACCENT_TEAL),
        ("risk", "medium", ACCENT_AMBER),
        ("network", "likely", ACCENT_BLUE),
        ("policy", "needs receipt", ACCENT_ROSE),
    ]
    row_top = verdict_bot + 16
    row_h = 38
    for i, (key, value, color) in enumerate(rows):
        y = row_top + i * row_h
        # Subtle alternating row tint
        if i % 2 == 0:
            draw.rounded_rectangle((inner_x1, y, inner_x2, y + row_h - 6),
                                   radius=10, fill="#f6fafd")
        # Color bar on left
        draw.rectangle((inner_x1 + 6, y + 6, inner_x1 + 10, y + row_h - 12), fill=color)
        draw.text((inner_x1 + 22, y + 6), key, font=fonts["row_key"], fill=INK_MUTED)
        vw = _text_width(fonts["row_value"], value)
        draw.text((inner_x2 - vw - 10, y + 6), value, font=fonts["row_value"], fill=INK)

    # CI guard banner — separated from rows so it never overlaps
    guard_y1 = y2 - 56
    guard_y2 = y2 - 18
    draw.rounded_rectangle((inner_x1, guard_y1, inner_x2, guard_y2),
                           radius=12, fill="#fde9ee", outline="#f3b5c2", width=1)
    # Lock icon (small)
    lx, ly = inner_x1 + 16, (guard_y1 + guard_y2) // 2
    draw.rectangle((lx, ly - 2, lx + 10, ly + 7), fill=ACCENT_ROSE)
    draw.arc((lx - 1, ly - 11, lx + 11, ly + 1), start=180, end=360,
             fill=ACCENT_ROSE, width=2)
    draw.text((inner_x1 + 34, guard_y1 + 8),
              "CI guard · missing trial evidence", font=fonts["row_value"], fill=ACCENT_ROSE)


# -------- evidence strip ----------------------------------------------------


def _draw_evidence_strip(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    x1, y1, x2, y2 = EVIDENCE_STRIP
    # Light card, not the heavy dark slab.
    draw.rounded_rectangle((x1, y1, x2, y2), radius=20, fill="#ffffff", outline=PANEL_BORDER, width=1)
    # Header band
    band_h = 36
    draw.rounded_rectangle((x1, y1, x2, y1 + band_h), radius=20, fill=PANEL_HEADER)
    draw.rectangle((x1, y1 + band_h - 20, x2, y1 + band_h), fill=PANEL_HEADER)
    draw.text((x1 + 22, y1 + 8), "EVIDENCE", font=fonts["section"], fill=ACCENT_TEAL)
    draw.text((x1 + 122, y1 + 8), "this run, all local", font=fonts["row_hint"], fill=INK_MUTED)

    items = [
        ("377 scanned, 5 verdicts surfaced", "scout", ACCENT_TEAL),
        ("profile: local only", "privacy", ACCENT_BLUE),
        ("sandbox: report-only receipt", "trial", ACCENT_AMBER),
        ("guard: missing trial evidence", "ci", ACCENT_ROSE),
        ("eval: incident-cache-storm-001 · score 1.0", "eval", ACCENT_VIOLET),
    ]
    body_y1 = y1 + band_h + 14
    body_y2 = y2 - 14
    avail = (x2 - x1) - 32
    col_w = avail // len(items)
    for i, (text, label, color) in enumerate(items):
        cx1 = x1 + 16 + i * col_w + 4
        cx2 = cx1 + col_w - 8
        # Subtle highlight on the item that matches the active pipeline step
        active = i == int(phase * len(items)) % len(items)
        fill = _blend("#ffffff", color, 0.06) if active else "#fbfdff"
        border = _blend("#e1ecf3", color, 0.6) if active else "#e6eff5"
        draw.rounded_rectangle((cx1, body_y1, cx2, body_y2),
                               radius=14, fill=fill, outline=border, width=1)
        # Status dot
        draw.ellipse((cx1 + 14, body_y1 + 18, cx1 + 26, body_y1 + 30), fill=color)
        draw.text((cx1 + 36, body_y1 + 8), label.upper(), font=fonts["section"], fill=color)
        _draw_wrapped(draw, text, fonts["evidence"], cx1 + 14, body_y1 + 32,
                      cx2 - cx1 - 28, INK, line_height=18)


# -------- primitives --------------------------------------------------------


def _panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    subtitle: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    x1, y1, x2, y2 = box
    # Soft shadow
    for d in range(3, 0, -1):
        draw.rounded_rectangle((x1 + d, y1 + d + 2, x2 + d, y2 + d + 2),
                               radius=PANEL_RADIUS, outline="#e6eff7")
    draw.rounded_rectangle(box, radius=PANEL_RADIUS, fill=PANEL_FILL, outline=PANEL_BORDER, width=1)
    # Header band
    draw.rounded_rectangle((x1, y1, x2, y1 + PANEL_HEADER_H), radius=PANEL_RADIUS, fill=PANEL_HEADER)
    draw.rectangle((x1, y1 + PANEL_HEADER_H - 22, x2, y1 + PANEL_HEADER_H), fill=PANEL_HEADER)
    # Header separator
    draw.line((x1 + 16, y1 + PANEL_HEADER_H, x2 - 16, y1 + PANEL_HEADER_H), fill=RULE, width=1)
    # Title + subtitle
    draw.ellipse((x1 + 22, y1 + 28, x1 + 34, y1 + 40), fill=ACCENT_TEAL)
    draw.text((x1 + 42, y1 + 14), title, font=fonts["panel_title"], fill=INK)
    draw.text((x1 + 42, y1 + 40), subtitle, font=fonts["row_hint"], fill=INK_MUTED)


def _pill(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    *,
    fill: str,
    text_color: str,
    font: ImageFont.ImageFont,
) -> None:
    draw.rounded_rectangle(box, radius=20, fill=fill, outline=_blend(fill, text_color, 0.35), width=1)
    tw = _text_width(font, label)
    th = _text_height(font, label)
    cx = (box[0] + box[2]) // 2
    cy = (box[1] + box[3]) // 2
    draw.text((cx - tw / 2, cy - th / 2 - 1), label, font=font, fill=text_color)


def _draw_centered_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    cx: int,
    top_y: int,
    max_w: int,
    color: str,
    *,
    line_height: int,
) -> None:
    lines = _wrap(text, font, max_w)
    for i, line in enumerate(lines):
        tw = _text_width(font, line)
        draw.text((cx - tw / 2, top_y + i * line_height), line, font=font, fill=color)


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    x: int,
    y: int,
    max_w: int,
    color: str,
    *,
    line_height: int,
) -> None:
    lines = _wrap(text, font, max_w)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_height), line, font=font, fill=color)


def _wrap(text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if _text_width(font, candidate) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# -------- fonts -------------------------------------------------------------


def _fonts() -> dict[str, ImageFont.ImageFont]:
    sans_candidates = [
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    sans_bold_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    mono_candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]

    def load(size: int, kind: str = "sans") -> ImageFont.ImageFont:
        paths = {"sans": sans_candidates, "bold": sans_bold_candidates, "mono": mono_candidates}[kind]
        for path in paths:
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size=size)
                except OSError:
                    continue
        return ImageFont.load_default(size=size)

    return {
        "eyebrow": load(15, "mono"),
        "title": load(44, "bold"),
        "sub": load(22, "sans"),
        "pill": load(15, "bold"),
        "panel_title": load(22, "bold"),
        "section": load(13, "mono"),
        "row_title": load(16, "bold"),
        "row_hint": load(13, "sans"),
        "row_key": load(14, "sans"),
        "row_value": load(15, "bold"),
        "chip": load(13, "bold"),
        "step_num": load(13, "bold"),
        "step_title": load(15, "bold"),
        "step_detail": load(12, "sans"),
        "tag": load(11, "bold"),
        "stamp": load(40, "bold"),
        "evidence": load(13, "sans"),
    }


# -------- low-level helpers -------------------------------------------------


def _smoothstep(value: float) -> float:
    x = max(0.0, min(1.0, value))
    return x * x * (3 - 2 * x)


def _blend(a: str, b: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    ar, ag, ab = _hex(a)
    br, bg, bb = _hex(b)
    return f"#{round(ar + (br - ar) * ratio):02x}{round(ag + (bg - ag) * ratio):02x}{round(ab + (bb - ab) * ratio):02x}"


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _text_width(font: ImageFont.ImageFont, text: str) -> int:
    left, _, right, _ = font.getbbox(text)
    return right - left


def _text_height(font: ImageFont.ImageFont, text: str) -> int:
    _, top, _, bottom = font.getbbox(text)
    return bottom - top


def _png_bytes(image: Image.Image) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    main()
