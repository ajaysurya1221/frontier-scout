"""Generate the README figures: ``docs/assets/{hero,where}-{light,dark}.svg``.

Standard library only, deterministic, no network. ``--write`` regenerates the four files;
``--check`` regenerates them in memory and exits 1 if a committed file is missing or differs.
``tests/test_figures.py`` runs ``--check``, so CI fails when a figure and its source drift.

The SVGs contain only ``<rect>``, ``<path>``, ``<polygon>`` and ``<text>`` elements: no
``<style>`` blocks, no scripts, no raster images, no external fonts or links. Text uses system
font stacks so GitHub renders it without web fonts, and every line has a width budget with
room for font-metric differences between platforms. ``<title>`` and ``<desc>`` carry the full
text of each figure.

The hero's evidence card shows three verdicts and exit codes. Each one is recorded in a
committed file, and both modes first confirm that the exact strings in ``SOURCES`` are still
present, so the figures cannot drift from the evidence silently:

- ``examples/demo-walkthrough.md``: step 3, a path outside ``allowed_file_globs``
  (``SCOPE_OUTSIDE_ALLOWED``), ``FAIL`` with ``exit: 1``; step 4, a protected path backed
  only by an unsigned receipt (``APPROVAL_UNAUTHENTICATED``), ``UNVERIFIED`` with
  ``exit: 1``; step 5, an in-scope change, ``PASS`` with ``exit: 0``.
- ``tests/test_verify_regression_matrix.py``: the same three outcomes as real-git cases
  (``test_d1_out_of_scope_addition_fails``,
  ``test_d2_local_receipt_cannot_authorise_protected_change``,
  ``test_control_benign_in_scope_change_passes``).
- ``docs/evaluation/verifier-2026-10-06.md``: the CLI exits 0 only for PASS in enforcing mode
  and always exits 0 in advisory mode.
- ``.github/workflows/frontier-scout-verify.yml``: this repository runs the CLI and the
  composite Action (``uses: ./``) on its own pull requests, both in advisory mode.
- ``action.yml``: attestation is opt-in (``attest`` defaults to ``"false"``).

The scope-verification figure contains no measured numbers.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent
REPO = ASSETS.parent.parent

SOURCES: tuple[tuple[str, str], ...] = (
    (
        "examples/demo-walkthrough.md",
        "[SCOPE_OUTSIDE_ALLOWED] scripts/bootstrap.sh: changed (A) outside allowed_file_globs and "
        "not a protected path (out of scope).\nexit: 1\n",
    ),
    ("examples/demo-walkthrough.md", "\nFAIL: scope violated (1 path(s) outside allowed_file_globs)"),
    (
        "examples/demo-walkthrough.md",
        "\nUNVERIFIED: scope verified (every changed path is allowed or protected by the base policy); "
        "approval provenance not authenticated for 1 protected path(s) (receipts are unsigned); "
        "1 changed file(s), 1 receipt(s)",
    ),
    ("examples/demo-walkthrough.md", "A human must approve it out of band.\nexit: 1\n"),
    ("examples/demo-walkthrough.md", "\nPASS: scope verified (every changed path is allowed"),
    ("examples/demo-walkthrough.md", "(hooks may not be installed).\nexit: 0\n"),
    (
        "tests/test_verify_regression_matrix.py",
        "def test_d1_out_of_scope_addition_fails(tmp_path):\n    repo, base = _make_repo(tmp_path)\n"
        '    repo.write("scripts/exfil.sh", "curl example.invalid\\n")\n    repo.commit("out of scope")\n'
        "    res = verify_pr(repo.root, base=base)\n    assert res.ok is False\n"
        '    assert res.verdict == "fail" and res.scope == "violated"\n',
    ),
    (
        "tests/test_verify_regression_matrix.py",
        '    assert res.ok is False\n    assert res.verdict == "unverified" and res.unverified is True\n'
        '    assert "APPROVAL_UNAUTHENTICATED" in _codes(res)\n',
    ),
    (
        "tests/test_verify_regression_matrix.py",
        "def test_control_benign_in_scope_change_passes(tmp_path):\n",
    ),
    ("tests/test_verify_regression_matrix.py", '    assert res.verdict == "pass" and res.summary.startswith("PASS")\n'),
    (
        "docs/evaluation/verifier-2026-10-06.md",
        "The CLI exits 0 only for PASS in enforcing mode, and always exits 0 in advisory mode.",
    ),
    (
        ".github/workflows/frontier-scout-verify.yml",
        '--receipts "frontier-scout-receipts/*.json"\n          --advisory\n',
    ),
    (".github/workflows/frontier-scout-verify.yml", '      - uses: ./\n        with:\n          advisory: "true"\n'),
    ("action.yml", "  attest:\n"),
    ("action.yml", 'never silently degrades to unsigned evidence. Unavailable to fork PRs.\n    default: "false"\n'),
)

SERIF = "Georgia, 'Times New Roman', serif"
MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
SANS = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

ARROW = chr(0x2192)
DOT = chr(0x00B7)  # middle dot


@dataclass(frozen=True)
class Theme:
    name: str
    ground: str
    text: str
    soft: str
    muted: str
    accent: str
    card: str
    card_text: str
    card_muted: str
    card_accent: str
    fail: str
    unverified: str
    passed: str
    lane_outer: str
    lane_inner: str
    box: str
    box_border: str
    arrow: str


LIGHT = Theme(
    name="light",
    ground="#F4F1EA",
    text="#16211D",
    soft="#3E3D38",
    muted="#6B6A65",
    accent="#8A5A00",
    card="#16211D",
    card_text="#E9E4D8",
    card_muted="#A8A397",
    card_accent="#E8B14A",
    fail="#F0A48A",
    unverified="#E8B14A",
    passed="#7FD1A8",
    lane_outer="#ECE8DD",
    lane_inner="#E9E4D8",
    box="#FFFFFF",
    box_border="#D9D4C7",
    arrow="#6B6A65",
)

DARK = Theme(
    name="dark",
    ground="#0F1512",
    text="#F0ECE2",
    soft="#CFCBC1",
    muted="#9A978E",
    accent="#E8B14A",
    card="#F4F1EA",
    card_text="#16211D",
    card_muted="#6B6A65",
    card_accent="#8A5A00",
    fail="#B8431F",
    unverified="#8A5A00",
    passed="#1F7A4D",
    lane_outer="#161E1A",
    lane_inner="#1A231F",
    box="#212B26",
    box_border="#34413A",
    arrow="#9A978E",
)


@dataclass(frozen=True)
class Span:
    text: str
    fill: str | None = None
    weight: int | None = None


@dataclass(frozen=True)
class Fit:
    """A text line and its width budget (recorded, not emitted).

    ``tests/test_figures.py`` checks monospace lines against the budget; proportional lines were
    laid out against measured Georgia, SF, Arial and Verdana metrics with room to spare.
    """

    text: str
    family: str
    size: int
    weight: int
    spacing_em: float
    limit: int


@dataclass
class Canvas:
    width: int
    height: int
    title: str
    desc: str
    body: list[str] = field(default_factory=list)
    fits: list[Fit] = field(default_factory=list)

    def rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        fill: str,
        *,
        rx: int = 0,
        stroke: str | None = None,
        stroke_width: int = 1,
        dashed: bool = False,
    ) -> None:
        attrs = [f'x="{x}"', f'y="{y}"', f'width="{w}"', f'height="{h}"']
        if rx:
            attrs.append(f'rx="{rx}"')
        attrs.append(f'fill="{fill}"')
        if stroke:
            attrs.append(f'stroke="{stroke}" stroke-width="{stroke_width}"')
            if dashed:
                attrs.append('stroke-dasharray="7 5"')
        self.body.append(f"<rect {' '.join(attrs)}/>")

    def text(
        self,
        x: int,
        y: int,
        spans: Sequence[Span] | str,
        *,
        size: int,
        family: str,
        fill: str,
        limit: int,
        weight: int = 400,
        anchor: str = "start",
        spacing_em: float = 0.0,
    ) -> None:
        items = [Span(spans)] if isinstance(spans, str) else list(spans)
        attrs = [f'x="{x}"', f'y="{y}"', f'font-family="{escape(family)}"', f'font-size="{size}"']
        attrs.append(f'fill="{fill}"')
        if weight != 400:
            attrs.append(f'font-weight="{weight}"')
        if anchor != "start":
            attrs.append(f'text-anchor="{anchor}"')
        if spacing_em:
            attrs.append(f'letter-spacing="{spacing_em:g}em"')
        parts = []
        for span in items:
            span_attrs = []
            if span.fill:
                span_attrs.append(f'fill="{span.fill}"')
            if span.weight:
                span_attrs.append(f'font-weight="{span.weight}"')
            content = escape(span.text, quote=False)
            parts.append(f"<tspan {' '.join(span_attrs)}>{content}</tspan>" if span_attrs else content)
        self.body.append(f"<text {' '.join(attrs)}>{''.join(parts)}</text>")
        full = "".join(span.text for span in items)
        heaviest = max([weight] + [span.weight or weight for span in items])
        self.fits.append(Fit(full, family, size, heaviest, spacing_em, limit))

    def line(self, points: Sequence[tuple[int, int]], stroke: str, *, width: int = 2, dashed: bool = False) -> None:
        d = " ".join(f"{'M' if i == 0 else 'L'} {x} {y}" for i, (x, y) in enumerate(points))
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.body.append(
            f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width}"{dash} '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    def arrow(self, points: Sequence[tuple[int, int]], color: str, *, dashed: bool = False) -> None:
        """A polyline whose last segment ends in a filled head (axis-aligned segments only)."""
        (x0, y0), (x1, y1) = points[-2], points[-1]
        dx = (x1 > x0) - (x1 < x0)
        dy = (y1 > y0) - (y1 < y0)
        head = 11
        base = (x1 - dx * head, y1 - dy * head)
        self.line([*points[:-1], base], color, dashed=dashed)
        px, py = -dy * 6, dx * 6
        tri = [(x1, y1), (base[0] + px, base[1] + py), (base[0] - px, base[1] - py)]
        pts = " ".join(f"{x},{y}" for x, y in tri)
        self.body.append(f'<polygon points="{pts}" fill="{color}"/>')

    def render(self) -> str:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" aria-labelledby="title desc">'
        )
        lines = [
            head,
            f'<title id="title">{escape(self.title, quote=False)}</title>',
            f'<desc id="desc">{escape(self.desc, quote=False)}</desc>',
            *self.body,
            "</svg>",
        ]
        return "\n".join(lines) + "\n"


# --- hero --------------------------------------------------------------------------------

EYEBROW_NAME = "frontier-scout"
EYEBROW_REST = f" {DOT} PR scope verifier {DOT} policy compiler"
THESIS = ("Did this agent PR", "stay inside the scope", "declared on its", "base branch?")
SUBLINE = (
    "One typed policy compiles into Claude Code controls;",
    "CI checks every PR diff against it.",
    "Anything unproven is never a pass.",
)
CARD_HEADER = f"verify-pr {DOT} POLICY AND LOCK READ FROM THE BASE COMMIT"
OUTCOMES = (
    ("path outside allowed_file_globs", "FAIL (exit 1)", "fail"),
    ("protected path, unsigned receipt only", "UNVERIFIED (exit 1)", "unverified"),
    ("change within declared scope", "PASS (exit 0)", "passed"),
)
CARD_FOOTER = ("examples/demo-walkthrough.md", "this repo runs the Action on its own PRs (advisory)")


def hero(theme: Theme) -> Canvas:
    title = "Frontier Scout: did this agent PR stay inside the scope declared on its base branch?"
    desc = " ".join(
        [
            f"{EYEBROW_NAME}{EYEBROW_REST}.",
            " ".join(THESIS),
            " ".join(SUBLINE),
            f"Evidence card, {CARD_HEADER.replace(DOT, '-')}:",
            "; ".join(f"{cond} {ARROW} {verdict}" for cond, verdict, _ in OUTCOMES) + ".",
            f"Sources: {CARD_FOOTER[0]}; {CARD_FOOTER[1]}.",
        ]
    )
    c = Canvas(1600, 520, title, desc)
    c.rect(0, 0, 1600, 520, theme.ground)

    left, left_w = 72, 740
    c.text(
        left,
        68,
        [Span(EYEBROW_NAME, fill=theme.accent, weight=600), Span(EYEBROW_REST)],
        size=20,
        family=MONO,
        fill=theme.muted,
        limit=left_w,
    )
    for i, line in enumerate(THESIS):
        c.text(left, 140 + 64 * i, line, size=60, family=SERIF, fill=theme.text, weight=700, limit=left_w)
    for i, line in enumerate(SUBLINE):
        c.text(left, 392 + 34 * i, line, size=25, family=SANS, fill=theme.soft, limit=left_w)

    card_x, card_y, card_w, card_h = 868, 56, 660, 408
    inner_x, inner_w = card_x + 34, card_w - 68
    c.rect(card_x, card_y, card_w, card_h, theme.card, rx=16)
    c.text(
        inner_x,
        106,
        CARD_HEADER,
        size=15,
        family=MONO,
        fill=theme.card_muted,
        spacing_em=0.05,
        limit=inner_w,
    )
    for i, (condition, verdict, tone) in enumerate(OUTCOMES):
        y = 156 + 80 * i
        c.text(inner_x, y, condition, size=21, family=MONO, fill=theme.card_text, limit=inner_w)
        c.text(
            inner_x,
            y + 32,
            [Span(f"{ARROW} "), Span(verdict, fill=getattr(theme, tone))],
            size=24,
            family=MONO,
            fill=theme.card_text,
            weight=700,
            limit=inner_w,
        )
    for i, line in enumerate(CARD_FOOTER):
        c.text(inner_x, 398 + 22 * i, line, size=15, family=MONO, fill=theme.card_muted, limit=inner_w)
    return c


# --- where it sits -------------------------------------------------------------------------

WHERE_TITLE = "Where frontier-scout sits"
WHERE_SUB = (
    "Between an agent's pull request and the merge decision: every changed path is checked against "
    "the scope declared on the base branch."
)


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int
    title: str
    lines: tuple[tuple[str, str], ...]  # (family key, text)
    dashed: bool = False

    @property
    def cx(self) -> int:
        return self.x + self.w // 2


LANE_Y, LANE_H = 132, 404
LANES = (
    (64, 420, "AGENT PR + BASE BRANCH", "outer"),
    (524, 552, "CI", "inner"),
    (1116, 420, "MERGE DECISION", "outer"),
)

BASE = Box(88, 180, 372, 96, "Base commit", (("mono", "frontier-scout.policy.json"), ("mono", "+ policy.lock.json")))
DIFF = Box(88, 300, 372, 96, "Candidate PR diff", (("mono", "git diff --name-status -z -M"), ("mono", "base...HEAD")))
RECEIPTS = Box(
    88,
    420,
    372,
    96,
    "Local receipts",
    (("sans", "unsigned input:"), ("sans", "reported, never an approval")),
    dashed=True,
)
OWN_PRS = Box(
    556,
    420,
    488,
    96,
    "This repository's own PRs",
    (("mono", "frontier-scout-verify.yml"), ("sans", "advisory: verdict reported, exit 0")),
)
EVIDENCE = Box(
    1140,
    180,
    372,
    96,
    "Verdict + evidence JSON",
    (("sans", "PR annotations, step summary"), ("sans", "exit 0 only on PASS (enforcing)")),
)
ATTEST = Box(
    1140,
    300,
    372,
    96,
    "Attestation (optional)",
    (("mono", f'attest: "true" {ARROW} Sigstore'), ("sans", "names the workflow, not the approver")),
    dashed=True,
)
GATE = Box(1140, 420, 372, 96, "Merge gate", (("sans", "only from a workflow"), ("sans", "the PR cannot edit")))

VERIFIER_X, VERIFIER_Y, VERIFIER_W, VERIFIER_H = 556, 180, 488, 216
VERIFIER_LINES = (
    "policy + lock read from the base commit",
    "every changed path checked against",
)
VERIFIER_GLOBS = "allowed_file_globs, protected_file_globs"
VERIFIER_NOTE = "anything unproven is never a pass"


def _box(c: Canvas, theme: Theme, box: Box, lane_fill: str) -> None:
    fill = lane_fill if box.dashed else theme.box
    stroke = theme.muted if box.dashed else theme.box_border
    c.rect(
        box.x, box.y, box.w, box.h, fill, rx=10, stroke=stroke, stroke_width=2 if box.dashed else 1, dashed=box.dashed
    )
    limit = box.w - 24
    c.text(
        box.cx, box.y + 34, box.title, size=21, family=SANS, fill=theme.text, weight=700, anchor="middle", limit=limit
    )
    for i, (kind, text) in enumerate(box.lines):
        family, size = (MONO, 17) if kind == "mono" else (SANS, 18)
        c.text(
            box.cx, box.y + 62 + 24 * i, text, size=size, family=family, fill=theme.soft, anchor="middle", limit=limit
        )


def where(theme: Theme) -> Canvas:
    title = "Where frontier-scout sits: the PR diff against the policy on the base branch"
    desc = " ".join(
        [
            f"{WHERE_SUB}",
            "Inputs: the base commit's frontier-scout.policy.json and policy.lock.json, and the candidate",
            "PR diff (git diff --name-status -z -M base...HEAD). Local receipts are an unsigned input:",
            "reported, never an approval.",
            "In CI, agent verify-pr reads the policy and lock from the base commit and checks every changed",
            "path against allowed_file_globs and protected_file_globs. Verdicts: FAIL, UNVERIFIED or PASS;",
            "anything unproven is never a pass.",
            "Outputs: the verdict and an evidence JSON, with PR annotations and a step summary; exit 0 only",
            'on PASS when enforcing. Attestation is optional: with attest: "true" the evidence JSON is signed',
            "through Sigstore, which names the workflow that produced it, not the approver.",
            "A merge gate must run from a workflow the PR cannot edit.",
            "This repository's own PRs run the check in frontier-scout-verify.yml in advisory mode:",
            "the verdict is reported and the job exits 0.",
        ]
    )
    c = Canvas(1600, 560, title, desc)
    c.rect(0, 0, 1600, 560, theme.ground)
    c.text(64, 72, WHERE_TITLE, size=34, family=SERIF, fill=theme.text, weight=700, limit=1472)
    c.text(64, 108, WHERE_SUB, size=19, family=SANS, fill=theme.soft, limit=1472)

    fills = {"outer": theme.lane_outer, "inner": theme.lane_inner}
    for x, w, label, kind in LANES:
        c.rect(x, LANE_Y, w, LANE_H, fills[kind], rx=12)
        c.text(x + 20, LANE_Y + 28, label, size=15, family=MONO, fill=theme.muted, spacing_em=0.12, limit=w - 40)

    # Arrows first, so boxes sit on top of their ends.
    c.arrow([(BASE.x + BASE.w, 228), (VERIFIER_X, 228)], theme.arrow)
    c.arrow([(DIFF.x + DIFF.w, 348), (VERIFIER_X, 348)], theme.arrow)
    c.arrow([(RECEIPTS.x + RECEIPTS.w, 468), (504, 468), (504, 376), (VERIFIER_X, 376)], theme.arrow, dashed=True)
    right = VERIFIER_X + VERIFIER_W
    c.arrow([(right, 228), (EVIDENCE.x, 228)], theme.accent)
    c.text(1092, 218, "verdict", size=14, family=MONO, fill=theme.accent, anchor="middle", limit=88)
    c.arrow([(EVIDENCE.cx, EVIDENCE.y + EVIDENCE.h), (EVIDENCE.cx, ATTEST.y)], theme.arrow, dashed=True)
    c.arrow([(right, 376), (1092, 376), (1092, 468), (GATE.x, 468)], theme.accent)
    c.arrow([(OWN_PRS.cx, OWN_PRS.y), (OWN_PRS.cx, VERIFIER_Y + VERIFIER_H)], theme.arrow)

    lane_fill = {BASE: theme.lane_outer, DIFF: theme.lane_outer, RECEIPTS: theme.lane_outer, OWN_PRS: theme.lane_inner}
    for box in (BASE, DIFF, RECEIPTS, OWN_PRS, EVIDENCE, ATTEST, GATE):
        _box(c, theme, box, lane_fill.get(box, theme.lane_outer))

    c.rect(VERIFIER_X, VERIFIER_Y, VERIFIER_W, VERIFIER_H, theme.card, rx=12, stroke=theme.accent, stroke_width=2)
    cx, limit = VERIFIER_X + VERIFIER_W // 2, VERIFIER_W - 32
    c.text(
        cx,
        216,
        "agent verify-pr",
        size=24,
        family=MONO,
        fill=theme.card_accent,
        weight=700,
        anchor="middle",
        limit=limit,
    )
    for i, line in enumerate(VERIFIER_LINES):
        c.text(cx, 250 + 26 * i, line, size=19, family=SANS, fill=theme.card_text, anchor="middle", limit=limit)
    c.text(cx, 302, VERIFIER_GLOBS, size=16, family=MONO, fill=theme.card_text, anchor="middle", limit=limit)
    sep = Span(f" {DOT} ", fill=theme.card_muted)
    verdicts = [Span("FAIL", fill=theme.fail), sep, Span("UNVERIFIED", fill=theme.unverified), sep]
    verdicts.append(Span("PASS", fill=theme.passed))
    # Start-anchored at a computed x (monospace, about 0.6 em per character): some renderers
    # misplace coloured tspans inside middle-anchored text.
    row_chars = sum(len(span.text) for span in verdicts)
    c.text(
        cx - round(row_chars * 0.61 * 20 / 2),
        342,
        verdicts,
        size=20,
        family=MONO,
        fill=theme.card_text,
        weight=700,
        limit=limit,
    )
    c.text(cx, 372, VERIFIER_NOTE, size=17, family=SANS, fill=theme.card_muted, anchor="middle", limit=limit)
    return c


# --- driver --------------------------------------------------------------------------------

FIGURES: dict[str, Callable[[], Canvas]] = {
    "hero-light.svg": lambda: hero(LIGHT),
    "hero-dark.svg": lambda: hero(DARK),
    "where-light.svg": lambda: where(LIGHT),
    "where-dark.svg": lambda: where(DARK),
}


def check_sources() -> list[str]:
    problems = []
    for rel, needle in SOURCES:
        path = REPO / rel
        if not path.is_file():
            problems.append(f"source missing: {rel}")
        elif needle not in path.read_text(encoding="utf-8"):
            problems.append(f"{rel} no longer contains: {needle!r}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate the SVG files")
    mode.add_argument("--check", action="store_true", help="fail if a committed SVG differs")
    args = parser.parse_args(argv)

    problems = check_sources()
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1

    stale = []
    for name, build in FIGURES.items():
        content = build().render()
        path = ASSETS / name
        if args.write:
            path.write_bytes(content.encode("utf-8"))
            print(f"wrote {path.relative_to(REPO)}")
        elif not path.is_file() or path.read_bytes() != content.encode("utf-8"):
            stale.append(name)
    if stale:
        print(
            f"error: out of date: {', '.join(stale)}; run python3 docs/assets/src/make_figures.py --write",
            file=sys.stderr,
        )
        return 1
    if args.check:
        print(f"ok: {len(FIGURES)} figures match the generator and its sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
