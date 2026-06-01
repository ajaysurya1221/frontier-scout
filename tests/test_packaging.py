"""Guard against the v1.5.1 packaging regression.

v1.5.1 shipped a wheel/sdist that omitted the Textual stylesheets
(``tui2/theme.tcss``, ``tui3/theme.tcss``) because ``pyproject.toml`` declared
no ``package-data``. Every ``pip install`` then crashed on launch with
``StylesheetError: unable to read CSS file '.../theme.tcss'``. These tests lock
the fix in place. See CHANGELOG 1.5.2.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import frontier_scout

PKG = Path(frontier_scout.__file__).resolve().parent
ROOT = PKG.parent


def test_textual_stylesheets_live_beside_their_apps() -> None:
    """Each App subclass sets ``CSS_PATH = "theme.tcss"`` resolved next to its
    module, so the file must exist there in both source and installed layouts."""
    for sub in ("tui2", "tui3"):
        css = PKG / sub / "theme.tcss"
        assert css.is_file(), f"missing Textual stylesheet: {css}"


@pytest.mark.skipif(
    not (ROOT / "pyproject.toml").is_file(),
    reason="pyproject.toml is only present in a source checkout",
)
def test_pyproject_bundles_tcss_as_package_data() -> None:
    """``package-data`` must keep a ``*.tcss`` glob, or the built wheel ships
    without stylesheets again (the v1.5.1 regression)."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    package_data = data["tool"]["setuptools"]["package-data"]
    globs = [g for patterns in package_data.values() for g in patterns]
    assert any(g.endswith(".tcss") for g in globs), (
        "package-data must include a *.tcss glob or the wheel ships without "
        f"stylesheets (v1.5.1 regression); got {package_data}"
    )
