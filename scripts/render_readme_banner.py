"""Render the animated README mission-control banner.

The output is intentionally deterministic so the README hero can be regenerated
without screen recording tools or SaaS design software.
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
FRAME_COUNT = 60
FRAME_MS = 190


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    fonts = _fonts()
    frames: list[Image.Image] = []
    for index in range(FRAME_COUNT):
        image = _draw_frame(index, fonts)
        frame_path = SCRATCH_DIR / f"frame-{index:03d}.png"
        image.save(frame_path, optimize=True)
        frames.append(image.convert("P", palette=Image.Palette.ADAPTIVE, colors=192))

    _draw_frame(0, fonts).save(POSTER_PATH, optimize=True)
    frames[0].save(
        GIF_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {GIF_PATH.relative_to(ROOT)}")
    print(f"Wrote {POSTER_PATH.relative_to(ROOT)}")


def _draw_frame(index: int, fonts: dict[str, ImageFont.ImageFont]) -> Image.Image:
    # Frame 0 is the settled poster state, so GitHub shows a useful first still.
    phase = 1.0 if index == 0 else index / (FRAME_COUNT - 1)
    img = Image.new("RGB", (W, H), "#f7fbff")
    draw = ImageDraw.Draw(img)

    _draw_background(draw)
    _draw_header(draw, fonts)
    _draw_left_panel(draw, fonts, phase)
    _draw_graph_panel(draw, fonts, phase)
    _draw_dossier_panel(draw, fonts, phase)
    _draw_receipt_strip(draw, fonts, phase)
    return img


def _draw_background(draw: ImageDraw.ImageDraw) -> None:
    for y in range(H):
        ratio = y / H
        r = int(247 - ratio * 10)
        g = int(251 - ratio * 14)
        b = int(255 - ratio * 18)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    for x in range(80, W, 120):
        draw.line([(x, 130), (x, H - 110)], fill="#e8f0f7", width=1)
    for y in range(150, H - 100, 90):
        draw.line([(48, y), (W - 48, y)], fill="#e8f0f7", width=1)
    draw.rounded_rectangle((42, 34, W - 42, H - 34), radius=34, outline="#d5e4ef", width=2)


def _draw_header(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont]) -> None:
    draw.text((78, 62), "FRONTIER SCOUT", font=fonts["mono"], fill="#0f766e")
    draw.text((78, 96), "Personalized AI adoption mission control", font=fonts["title"], fill="#101828")
    draw.text(
        (78, 153),
        "Scout what's trending, map it to your repos, and prove safety before trust.",
        font=fonts["body"],
        fill="#475467",
    )
    _pill(draw, (1280, 74, 1516, 118), "local-first", "#ecfdf3", "#047857", fonts["small_bold"])
    _pill(draw, (1280, 128, 1516, 172), "no auto-install", "#fff7ed", "#c2410c", fonts["small_bold"])


def _draw_left_panel(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    box = (74, 220, 495, 690)
    _panel(draw, box, "Scout sweep", "public signals -> repo profile", fonts)
    sources = [
        ("GitHub Trending", 0.07),
        ("MCP servers", 0.14),
        ("Hacker News", 0.21),
        ("Hugging Face", 0.28),
        ("Model drops", 0.35),
    ]
    for i, (label, start) in enumerate(sources):
        y = 292 + i * 52
        pulse = _pulse(phase, start, 0.23)
        fill = _blend("#ffffff", "#dffcf4", pulse)
        outline = _blend("#d8e6ef", "#0f766e", pulse)
        draw.rounded_rectangle((108, y, 455, y + 38), radius=14, fill=fill, outline=outline, width=2)
        draw.ellipse((126, y + 12, 140, y + 26), fill=_blend("#98a2b3", "#0f766e", pulse))
        draw.text((154, y + 8), label, font=fonts["small_bold"], fill="#1d2939")
        if pulse > 0.1:
            draw.line((455, y + 19, 540, 452), fill=_blend("#d8e6ef", "#0f766e", pulse), width=3)

    draw.text((108, 574), "repo fingerprint", font=fonts["mono"], fill="#0f766e")
    chips = ["Python", "Docker", "AGENTS.md", "GitHub Actions", "MCP config"]
    positions = [(108, 606), (204, 606), (302, 606), (108, 648), (270, 648)]
    for i, (chip, pos) in enumerate(zip(chips, positions, strict=True)):
        visible = _smoothstep((phase - 0.18 - i * 0.035) / 0.18)
        _chip(draw, pos, chip, fonts["tiny_bold"], visible)


def _draw_graph_panel(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    box = (540, 220, 1072, 690)
    _panel(draw, box, "Scout graph", "repo -> fit -> permissions -> evidence", fonts)
    nodes = [
        ("repo", (615, 332), 0.18, "#155eef"),
        ("stack", (760, 282), 0.27, "#0f766e"),
        ("problem fit", (760, 414), 0.36, "#0f766e"),
        ("tool", (910, 348), 0.45, "#c2410c"),
        ("permission", (972, 500), 0.57, "#c2410c"),
        ("trial receipt", (760, 588), 0.72, "#155eef"),
    ]
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4), (4, 5), (5, 0)]
    for a, b in edges:
        progress = _smoothstep((phase - max(nodes[a][2], nodes[b][2])) / 0.24)
        if progress <= 0:
            continue
        _edge(draw, nodes[a][1], nodes[b][1], progress)
    for label, center, start, color in nodes:
        _node(draw, center, label, color, fonts, _smoothstep((phase - start) / 0.22))

    tool_visible = _smoothstep((phase - 0.44) / 0.22)
    if tool_visible:
        card = (604, 462, 1008, 532)
        draw.rounded_rectangle(
            card,
            radius=18,
            fill=_blend("#ffffff", "#fff7ed", tool_visible),
            outline="#fdba74",
            width=2,
        )
        draw.text((630, 480), "modelcontextprotocol/servers", font=fonts["small_bold"], fill="#9a3412")
        draw.text((630, 506), "relevant because this repo has agent + MCP signals", font=fonts["tiny"], fill="#667085")


def _draw_dossier_panel(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    box = (1116, 220, 1526, 690)
    _panel(draw, box, "Adoption dossier", "try-before-trust decision", fonts)
    stamp = _smoothstep((phase - 0.72) / 0.18)
    draw.rounded_rectangle((1162, 292, 1482, 382), radius=22, fill="#fff7ed", outline="#fdba74", width=2)
    draw.text((1188, 314), "VERDICT", font=fonts["mono"], fill="#c2410c")
    trial_color = _blend("#fed7aa", "#c2410c", stamp)
    draw.text((1290, 304), "TRIAL", font=fonts["stamp"], fill=trial_color)
    rows = [
        ("category", "MCP server", 0.50),
        ("fit", "high", 0.56),
        ("risk", "medium", 0.62),
        ("network", "likely", 0.68),
        ("policy", "blocked until receipt exists", 0.78),
    ]
    for i, (key, value, start) in enumerate(rows):
        visible = _smoothstep((phase - start) / 0.16)
        y = 424 + i * 44
        draw.rounded_rectangle((1162, y, 1482, y + 32), radius=12, fill=_blend("#ffffff", "#eef6ff", visible))
        draw.text((1180, y + 7), key, font=fonts["tiny_bold"], fill="#667085")
        draw.text((1268, y + 7), value, font=fonts["tiny_bold"], fill=_blend("#98a2b3", "#155eef", visible))

    seal_visible = _smoothstep((phase - 0.83) / 0.14)
    draw.rounded_rectangle(
        (1190, 624, 1454, 658),
        radius=17,
        fill=_blend("#ffffff", "#fef3c7", seal_visible),
        outline="#f59e0b",
        width=2,
    )
    draw.text((1218, 632), "CI guard: missing trial evidence", font=fonts["tiny"], fill="#92400e")


def _draw_receipt_strip(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.ImageFont], phase: float) -> None:
    draw.rounded_rectangle((74, 714, 1526, 828), radius=28, fill="#101828", outline="#344054", width=2)
    receipts = [
        ("377 scanned -> 5 verdicts", "#22c55e", 0.12),
        ("profile: local only", "#38bdf8", 0.26),
        ("sandbox: report-only receipt", "#f59e0b", 0.52),
        ("guard: missing trial evidence", "#fb7185", 0.76),
        ("eval: incident-cache-storm-001 score 1.0", "#a78bfa", 0.86),
    ]
    positions = [
        (112, 738, 415, 778),
        (438, 738, 674, 778),
        (698, 738, 1056, 778),
        (112, 786, 513, 816),
        (538, 786, 1034, 816),
    ]
    for (label, color, start), (x1, y1, x2, y2) in zip(receipts, positions, strict=True):
        visible = _smoothstep((phase - start) / 0.16)
        draw.rounded_rectangle((x1, y1, x2, y2), radius=18, fill=_blend("#1d2939", "#ffffff", visible * 0.04))
        draw.ellipse((x1 + 18, y1 + 12, x1 + 32, y1 + 26), fill=_blend("#667085", color, visible))
        draw.text((x1 + 44, y1 + 10), label, font=fonts["small_bold"], fill=_blend("#98a2b3", "#ffffff", visible))


def _panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    subtitle: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    draw.rounded_rectangle(box, radius=28, fill="#ffffff", outline="#d5e4ef", width=2)
    draw.rounded_rectangle((box[0], box[1], box[2], box[1] + 72), radius=28, fill="#f2f7fb")
    draw.rectangle((box[0], box[1] + 44, box[2], box[1] + 72), fill="#f2f7fb")
    draw.text((box[0] + 28, box[1] + 20), title, font=fonts["panel_title"], fill="#101828")
    draw.text((box[0] + 28, box[1] + 48), subtitle, font=fonts["tiny"], fill="#667085")


def _node(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    label: str,
    color: str,
    fonts: dict[str, ImageFont.ImageFont],
    visible: float,
) -> None:
    if visible <= 0:
        return
    x, y = center
    radius = int(28 + visible * 8)
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=_blend("#ffffff", color, 0.14),
        outline=color,
        width=3,
    )
    width = _text_width(fonts["tiny_bold"], label)
    draw.text((x - width / 2, y + radius + 8), label, font=fonts["tiny_bold"], fill="#344054")


def _edge(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    progress: float,
) -> None:
    x1, y1 = start
    x2, y2 = end
    x = x1 + (x2 - x1) * progress
    y = y1 + (y2 - y1) * progress
    draw.line((x1, y1, x, y), fill="#9ac7d7", width=4)
    draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="#0f766e")


def _pill(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    fill: str,
    text: str,
    font: ImageFont.ImageFont,
) -> None:
    draw.rounded_rectangle(box, radius=22, fill=fill, outline=_blend(fill, text, 0.25), width=2)
    tw = _text_width(font, label)
    draw.text((box[0] + (box[2] - box[0] - tw) / 2, box[1] + 12), label, font=font, fill=text)


def _chip(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    label: str,
    font: ImageFont.ImageFont,
    visible: float,
) -> None:
    x, y = pos
    width = _text_width(font, label) + 28
    draw.rounded_rectangle(
        (x, y, x + width, y + 30),
        radius=15,
        fill=_blend("#ffffff", "#ecfdf3", visible),
        outline="#b7e4d7",
    )
    draw.text((x + 14, y + 7), label, font=font, fill=_blend("#98a2b3", "#047857", visible))


def _fonts() -> dict[str, ImageFont.ImageFont]:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    mono_candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]

    def load(size: int, *, mono: bool = False) -> ImageFont.ImageFont:
        for path in mono_candidates if mono else candidates:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default(size=size)

    return {
        "title": load(46),
        "body": load(27),
        "panel_title": load(25),
        "stamp": load(54),
        "mono": load(20, mono=True),
        "small_bold": load(21),
        "tiny_bold": load(17),
        "tiny": load(16),
    }


def _pulse(phase: float, start: float, duration: float) -> float:
    t = (phase - start) / duration
    if t < 0 or t > 1:
        return 0.18 if phase > start else 0.0
    return 0.35 + 0.65 * math.sin(t * math.pi)


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


if __name__ == "__main__":
    main()
