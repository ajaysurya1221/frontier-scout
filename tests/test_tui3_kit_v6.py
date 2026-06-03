from frontier_scout.tui3.kit import (
    SPIN_UNI, SPIN_ASCII, spinner_frames, glyphs, asciify,
)


def test_spinner_frames_select_by_mode():
    assert spinner_frames(True) == SPIN_UNI
    assert spinner_frames(False) == SPIN_ASCII
    assert SPIN_ASCII == ["|", "/", "-", "\\"]
    assert len(SPIN_UNI) >= 4


def test_spark_ramp_glyphs():
    assert glyphs(True)["spark"] == "▁▂▃▄▅▆▇█"
    assert glyphs(False)["spark"] == ".:-=+*#%"
    folded = asciify("▁▂▃▄▅▆▇█")
    assert folded.isascii(), folded
    assert folded == ".:-=+*##"
    assert asciify("█") == "#"


def test_matrix_corner_glyphs():
    g = glyphs(True)
    assert (g["corner_tl"], g["corner_tr"], g["corner_bl"], g["corner_br"]) == ("⌜", "⌝", "⌞", "⌟")
    assert glyphs(False)["corner_tl"] == "+"
    for c in ("⌜", "⌝", "⌞", "⌟"):
        assert asciify(c) == "+"
