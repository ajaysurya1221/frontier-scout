from rich.cells import cell_len
from frontier_scout.tui3.kit import meter, sweep, cell_width, glyphs, asciify


def test_cell_width_multicell_ascii():
    assert cell_width("(o)") == 3      # ascii radar_core is 3 cells — NOT len-counted wrong
    assert cell_width("#") == 1
    assert cell_width("▰") == 1


def test_meter_width_and_golden():
    assert len(meter(0.5, 20)) == 22                       # 20 pips + 2 brackets (unicode)
    assert meter(0.5, 20, unicode=False) == "[##########----------]"
    assert meter(0.72, 20, unicode=False) == "[##############------]"   # golden 'coverage' row
    assert meter(0.0, 20, unicode=False) == "[" + "-"*20 + "]"
    assert meter(1.0, 20, unicode=False) == "[" + "#"*20 + "]"


def test_sweep_width_and_golden():
    assert len(sweep(20, 7)) == 20                          # plain width invariant (unicode)
    # golden SCAN STATE sweep: width 22, head at col 7, 2-cell dim tail behind it
    assert sweep(22, 7, unicode=False) == "-----++#--------------"
    # motion off → static, still exactly `width` cells
    assert len(sweep(20, 7, motion=False)) == 20


def test_spark_and_ramp_unchanged():
    assert glyphs(False)["spark"] == ".:-=+*#%"
    assert all(ord(c) < 128 for c in asciify("▁▂▃▄▅▆▇█"))
