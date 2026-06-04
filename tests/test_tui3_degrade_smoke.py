"""v6 cross-mode degradation smoke — no unicode glyph may leak in ascii mode."""
from frontier_scout.tui3.kit import asciify, glyphs, spinner_frames

# Every v6 unicode glyph that must have an ascii fallback (incl. the cell-precision
# rework's box-grid + sweep-tail glyphs: box_h ─, box_v │, box_x ┼, seg_mid ▒).
V6_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏▰▱⌜⌝⌞⌟▁▂▃▄▅▆▇█✕◉─│┼▒"


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def test_ascii_glyph_table_is_pure_ascii():
    g = glyphs(False)
    # every value in the ascii glyph table is ascii-only
    for key, val in g.items():
        assert _is_ascii(val), f"glyphs(False)[{key!r}] = {val!r} leaks unicode"


def test_spark_ramp_ascii():
    assert glyphs(False)["spark"] == ".:-=+*#%"
    assert _is_ascii(asciify("▁▂▃▄▅▆▇█"))
    assert "#" in asciify("█")          # full block still folds to '#'


def test_spinner_frames_degrade():
    assert all(_is_ascii(f) for f in spinner_frames(False))
    assert not all(_is_ascii(f) for f in spinner_frames(True))   # unicode frames are braille


def test_asciify_folds_every_v6_glyph():
    assert _is_ascii(asciify(V6_UNICODE)), f"asciify leaked: {asciify(V6_UNICODE)!r}"


def test_corner_and_motif_glyphs_have_ascii():
    g = glyphs(False)
    for key in ("corner_tl", "corner_tr", "corner_bl", "corner_br", "cross",
                "seg_on", "seg_off", "radar_core", "spark"):
        assert key in g and _is_ascii(g[key]), f"{key} missing/leaks in ascii table"
