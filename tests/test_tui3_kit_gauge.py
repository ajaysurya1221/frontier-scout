"""Tests for the v5 segmented gauge — bar() and gauge() in kit.py.

TDD: these are written first and should FAIL until kit.py is updated.

Acceptance criteria (from the V5-1 handoff §1):
  * bar() returns (lit, unlit) runs built from seg_on / seg_off glyphs — not the
    old bar_full / bar_empty.
  * A full bar is all-seg_on pips; an empty bar is all-seg_off pips (visible track).
  * ASCII mode uses '#' / '-'.
  * gauge() wraps bar() in Rich markup with label + tone-coloured runs + read word.
  * level→segments: high=3, medium=2, low=1, none/other=0 (of maximum=3).
  * Tone auto-selection: muted (empty), danger→red (>=2) else gold, else mint (full),
    gold (>=2), else red.
  * danger=True flips direction: high fill → red.
  * asciify() folds the four new glyphs.
  * mono() pass preserves segment glyphs + the read word (strips color only).
"""

from __future__ import annotations

from rich.text import Text

from frontier_scout.tui3.kit import ASCII, UNI, _ASCIIFY, asciify, bar, gauge, mono


# ── glyph presence ────────────────────────────────────────────────────────────

def test_new_glyphs_in_uni():
    assert UNI["seg_on"] == "▰"
    assert UNI["seg_off"] == "▱"
    assert UNI["cap_l"] == "▏"
    assert UNI["cap_r"] == "▕"


def test_new_glyphs_in_ascii():
    assert ASCII["seg_on"] == "#"
    assert ASCII["seg_off"] == "-"
    assert ASCII["cap_l"] == "["
    assert ASCII["cap_r"] == "]"


def test_asciify_folds_new_glyphs():
    assert asciify("▰▱▏▕") == "#-[]"


def test_asciify_map_has_new_glyphs():
    assert "▰" in _ASCIIFY
    assert "▱" in _ASCIIFY
    assert "▏" in _ASCIIFY
    assert "▕" in _ASCIIFY


# ── bar() segmented contract ─────────────────────────────────────────────────

def test_bar_full_is_all_seg_on():
    lit, unlit = bar(10, 10, 10)
    assert lit == "▰" * 10
    assert unlit == ""


def test_bar_empty_is_all_seg_off():
    lit, unlit = bar(0, 10, 10)
    assert lit == ""
    assert unlit == "▱" * 10


def test_bar_partial_split():
    lit, unlit = bar(3, 10, 10)
    # round(3/10 * 10) == 3 filled
    assert lit == "▰" * 3
    assert unlit == "▱" * 7
    assert len(lit) + len(unlit) == 10


def test_bar_width_contract_holds():
    """Total glyph count always == width."""
    for value, maximum, width in [(0, 10, 8), (5, 10, 14), (10, 10, 14), (3, 7, 5)]:
        lit, unlit = bar(value, maximum, width)
        assert len(lit) + len(unlit) == width, (value, maximum, width)


def test_bar_no_old_block_glyphs():
    """The solid █ / ░ must NOT appear — they are the old meter."""
    for v in (0, 5, 10):
        lit, unlit = bar(v, 10, 10)
        assert "█" not in lit + unlit
        assert "░" not in lit + unlit


def test_bar_ascii_mode():
    lit, unlit = bar(4, 8, 8, unicode=False)
    assert set(lit) <= {"#"}
    assert set(unlit) <= {"-"}
    assert len(lit) + len(unlit) == 8


def test_bar_ascii_full():
    lit, unlit = bar(8, 8, 8, unicode=False)
    assert lit == "#" * 8
    assert unlit == ""


def test_bar_ascii_empty():
    lit, unlit = bar(0, 8, 8, unicode=False)
    assert lit == ""
    assert unlit == "-" * 8


# ── gauge() labelled instrument ───────────────────────────────────────────────

def test_gauge_high_has_three_lit_pips():
    out = gauge(level="high")
    # Three seg_on glyphs
    assert out.count("▰") == 3
    assert out.count("▱") == 0


def test_gauge_none_is_all_unlit():
    out = gauge(level="none")
    assert out.count("▱") == 3
    assert out.count("▰") == 0


def test_gauge_medium_has_two_lit_one_unlit():
    out = gauge(level="medium")
    assert out.count("▰") == 2
    assert out.count("▱") == 1


def test_gauge_low_has_one_lit_two_unlit():
    out = gauge(level="low")
    assert out.count("▰") == 1
    assert out.count("▱") == 2


def test_gauge_level_mapping():
    """level string → correct number of lit segments."""
    assert gauge(level="high").count("▰") == 3
    assert gauge(level="medium").count("▰") == 2
    assert gauge(level="low").count("▰") == 1
    assert gauge(level="none").count("▰") == 0


def test_gauge_has_read_word():
    out = gauge(level="high", read="high")
    assert "high" in out


def test_gauge_has_label():
    out = gauge(label="fit", level="high", read="high")
    assert "fit" in out


def test_gauge_fit_high_tone_is_mint():
    """fit high → tone mint → #24d6a8 in output."""
    out = gauge(level="high", read="high")
    assert "#24d6a8" in out


def test_gauge_fit_low_tone_is_red():
    """fit low (non-danger) → tone red → #ff6b6b."""
    out = gauge(level="low", read="low")
    assert "#ff6b6b" in out


def test_gauge_danger_high_is_red():
    """danger=True + high fill → red (not mint)."""
    out = gauge(level="high", danger=True, read="high")
    assert "#ff6b6b" in out
    assert "#24d6a8" not in out


def test_gauge_danger_low_is_gold():
    """danger=True + low fill (v=1 < 2) → gold."""
    out = gauge(level="low", danger=True, read="low")
    assert "#e3c26f" in out


def test_gauge_none_tone_is_muted():
    """v=0 → muted regardless of danger."""
    out = gauge(level="none", read="none")
    assert "#6e8aa1" in out


def test_gauge_explicit_tone_overrides():
    """When tone is passed explicitly, auto-tone is bypassed."""
    out = gauge(level="low", tone="mint", read="low")
    assert "#24d6a8" in out


def test_gauge_ascii_mode():
    out = gauge(level="high", unicode=False)
    assert "#" in out   # seg_on in ASCII
    assert "▰" not in out


def test_gauge_output_is_valid_rich_markup():
    """gauge() output must be parseable by Rich without raising."""
    for level in ("high", "medium", "low", "none"):
        out = gauge(label="fit", level=level, read=level)
        Text.from_markup(out)


# ── mono pass ─────────────────────────────────────────────────────────────────

def test_mono_preserves_segment_glyphs():
    """mono() strips color but the seg glyphs + the read word survive."""
    out_colour = gauge(label="fit", level="high", read="high")
    out_mono = mono(out_colour)
    assert "▰" in out_mono
    assert "high" in out_mono


def test_mono_strips_hex_color():
    out_colour = gauge(label="fit", level="high", read="high")
    out_mono = mono(out_colour)
    assert "#" not in out_mono


def test_mono_is_valid_rich_markup():
    out = mono(gauge(label="risk", level="medium", danger=True, read="medium"))
    Text.from_markup(out)


# ── asciify + mono round-trip ─────────────────────────────────────────────────

def test_asciify_on_gauge_output():
    out = gauge(label="fit", level="high", read="high")
    ascii_out = asciify(out)
    assert "▰" not in ascii_out
    assert "#" in ascii_out  # seg_on folded to #


def test_gauge_ascii_mode_no_unicode_segs():
    out = gauge(level="medium", unicode=False)
    assert "▰" not in out
    assert "▱" not in out
