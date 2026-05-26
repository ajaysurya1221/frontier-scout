"""Render the README banner from the designer-provided HTML source.

The source HTML is committed so the banner remains editable. This script uses
Playwright/Chromium to capture the animated design at 1600x900 and Pillow to
assemble an optimized GIF plus a static poster frame.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HTML = ROOT / "docs" / "assets" / "frontier-scout-banner-source.html"
ASSET_DIR = ROOT / "docs" / "assets"
SCRATCH_DIR = ROOT / ".scratch" / "readme-html-banner"
GIF_PATH = ASSET_DIR / "frontier-scout-mission-control.gif"
POSTER_PATH = ASSET_DIR / "frontier-scout-mission-control-poster.png"

WIDTH = 1600
HEIGHT = 900
FRAME_COUNT = 36
FRAME_MS = 300
MAX_GIF_MB = 12


def main() -> None:
    if not SOURCE_HTML.exists():
        raise SystemExit(f"Missing source HTML: {SOURCE_HTML}")
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    screenshots = _capture_frames()
    poster = Image.open(BytesIO(screenshots[0])).convert("RGB")
    poster.save(POSTER_PATH, optimize=True)

    frames: list[Image.Image] = []
    for index, payload in enumerate(screenshots):
        frame = Image.open(BytesIO(payload)).convert("RGB")
        frame_path = SCRATCH_DIR / f"frame-{index:03d}.png"
        frame.save(frame_path, optimize=True)
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=96))

    frames[0].save(
        GIF_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )

    gif_mb = GIF_PATH.stat().st_size / (1024 * 1024)
    print(f"Wrote {GIF_PATH.relative_to(ROOT)} ({gif_mb:.2f} MB)")
    print(f"Wrote {POSTER_PATH.relative_to(ROOT)} ({POSTER_PATH.stat().st_size / 1024:.1f} KB)")
    if gif_mb > MAX_GIF_MB:
        print(f"Warning: GIF exceeds {MAX_GIF_MB} MB target; consider fewer frames or lower palette size.")


def _capture_frames() -> list[bytes]:
    html_url = SOURCE_HTML.resolve().as_uri()
    screenshots: list[bytes] = []
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page.goto(html_url, wait_until="networkidle")
        page.wait_for_selector("#stage", timeout=5000)
        page.wait_for_timeout(500)
        for index in range(FRAME_COUNT):
            if index:
                page.wait_for_timeout(FRAME_MS)
            screenshots.append(page.screenshot(type="png", full_page=False))
        browser.close()
    return screenshots


def _launch_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except PlaywrightError:
        return playwright.chromium.launch(channel="chrome", headless=True)


if __name__ == "__main__":
    main()
