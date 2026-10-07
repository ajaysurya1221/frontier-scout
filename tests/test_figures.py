"""The README figures are generated, not drawn: the committed SVGs must match their generator.

`docs/assets/src/make_figures.py --check` regenerates the four SVGs in memory, confirms the
verdicts they show are still recorded in the committed sources it cites, and fails on any
difference. The structural checks keep the figures self-contained (no scripts, styles, raster
images or external references) so GitHub renders them the same everywhere.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
GENERATOR = ASSETS / "src" / "make_figures.py"
FIGURES = ("hero-light.svg", "hero-dark.svg", "where-light.svg", "where-dark.svg")
MONO_ADVANCE_EM = 0.62  # widest common monospace in the stack (SF Mono); Menlo is 0.60


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_figures", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_committed_figures_match_the_generator() -> None:
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("name", FIGURES)
def test_figure_is_self_contained_and_accessible(name: str) -> None:
    svg = (ASSETS / name).read_text(encoding="utf-8")
    for forbidden in ("<style", "<script", "<image", "<foreignObject", "href=", "@import", "url("):
        assert forbidden not in svg, f"{name} contains {forbidden!r}"
    assert re.search(r"<title id=\"title\">[^<]+</title>", svg)
    assert re.search(r"<desc id=\"desc\">[^<]+</desc>", svg)


def test_monospace_lines_fit_their_boxes() -> None:
    figures = _generator()
    for name, build in figures.FIGURES.items():
        for fit in build().fits:
            if fit.family != figures.MONO:
                continue
            width = len(fit.text) * (MONO_ADVANCE_EM + fit.spacing_em) * fit.size
            assert width <= fit.limit, f"{name}: {fit.text!r} needs {width:.0f}px of {fit.limit}px"
