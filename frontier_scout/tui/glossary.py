"""v1.3.0 — Glossary of Frontier Scout terms, surfaced two ways.

1. **Subtitle line** under each tab — one plain-English sentence the
   shell pulls from ``TAB_SUBTITLES``. First-time users see what a
   tab is for without having to learn jargon first.
2. **Glossary overlay** (`GlossaryScreen`) bound to ``?`` from any
   focus. Lists every term + a one-sentence definition. Pressing
   ``?`` again, or ``Esc``, closes it. Zero state — it's a
   read-only reference.

Why a static dict and not Markdown / JSON: the glossary travels in
the wheel and never changes between releases. Loading from disk would
add an init cost we don't need. Each entry stays a single sentence
to keep the overlay scannable.

Keep this file boring. New terms get added one line at a time.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


#: ``slug -> (display_label, one-sentence definition)``. Slugs are
#: stable handles other modules can reference; labels are what we
#: show to the user.
TERMS: dict[str, tuple[str, str]] = {
    # Core scout vocabulary
    "verdict": (
        "Verdict",
        "A scored, source-backed take on whether a tool / model / "
        "upgrade is worth your attention right now.",
    ),
    "adopt": (
        "ADOPT",
        "Worth installing today on the strength of evidence + repo "
        "fit; no further sandbox needed.",
    ),
    "trial": (
        "TRIAL",
        "Worth trying in a hermetic sandbox before adoption. Frontier "
        "Scout's lab handles the install + probe.",
    ),
    "assess": (
        "ASSESS",
        "Watch and re-evaluate later. Not safe to adopt yet, but not "
        "dismissed either.",
    ),
    "hold": (
        "HOLD",
        "Do not install. Either the evidence is weak or the cost / "
        "risk is too high for the value.",
    ),
    "fit": (
        "Fit",
        "How well a tool maps onto your repo's stack and existing "
        "agent config. Low / Medium / High.",
    ),
    "risk": (
        "Risk",
        "Cost of being wrong about adopting this tool. Low / Medium / "
        "High; raised when manifests touch sensitive capabilities.",
    ),
    "category": (
        "Category",
        "What kind of thing this is: dev tool, MCP server, agent "
        "framework, model drop, skill, vendor SDK, etc.",
    ),
    # Concerns taxonomy (v1.2.1 Stream K)
    "concern": (
        "Concern",
        "An explicit push-back reason on a verdict — e.g. weak fit, "
        "token-burn, abandoned project, security surface.",
    ),
    "weak_fit": (
        "weak fit",
        "Concern: no clear connection to your repo's stack — adopt "
        "only if you have a specific reason.",
    ),
    "token_burn": (
        "burns tokens",
        "Concern: per-call cost is meaningful; multiply by your "
        "actual call rate before adoption.",
    ),
    "abandoned": (
        "looks abandoned",
        "Concern: no public evidence of recent maintenance; releases "
        "stopped ≥ 9 months ago.",
    ),
    "security_surface": (
        "security surface",
        "Concern: permission manifest carries write / shell / "
        "credential capability. Sandbox before adoption.",
    ),
    "vendor_lock_in": (
        "vendor lock-in",
        "Concern: switching away later would mean rewriting against "
        "a different API surface.",
    ),
    "marketing_only": (
        "marketing-only",
        "Concern: short, vague description and no public code repo — "
        "could be a landing page, not a tool.",
    ),
    "unproven": (
        "unproven",
        "Concern: no local lab/trial receipt on file yet — your "
        "first run is the real test.",
    ),
    # Adjacent vocabulary
    "permission_manifest": (
        "Permission manifest",
        "What the tool can do once installed: network, write, shell, "
        "credentials. Source of the security surface concern.",
    ),
    "scout_pack": (
        "Scout Pack",
        "A curated set of seed repos / themes the live scout focuses "
        "on. Configure via `frontier-scout setup`.",
    ),
    "dossier": (
        "Dossier",
        "A per-tool adoption brief: source URL, fit, risk, "
        "permission map, alternatives, next safe step. Saved as "
        "Markdown under ~/.frontier-scout/.",
    ),
    "lab": (
        "Lab",
        "Hermetic sandbox install + probe of a package or model. "
        "Stripped HOME and env so it can't see your real keys.",
    ),
    "guard": (
        "Guard",
        "CI / local check that no tool in the stored ledger is in a "
        "HOLD state. `frontier-scout guard --format github` for "
        "Actions annotations.",
    ),
    "universal_mode": (
        "Universal mode",
        "Scout from outside a repo. Surfaces every seeded verdict, "
        "no personalisation, no scan persisted to SQLite.",
    ),
    "report": (
        "Report",
        "Static HTML of the latest scan for the current repo. Press "
        "`r` to render and open in your browser.",
    ),
    "diff": (
        "Diff",
        "Compare the current scout output to the previously saved "
        "one for this repo. Press `d` to open.",
    ),
}


#: One sentence per tab. Shown directly under the tab strip.
TAB_SUBTITLES: dict[str, str] = {
    "scout": (
        "New AI tools and dependency upgrades that fit your repo. "
        "Press [bold]▶ Scout now[/] (or [bold]s[/]) to run; "
        "[bold]Enter[/] to try the highlighted row; "
        "[bold]?[/] for the glossary."
    ),
    "settings": (
        "Your local Adoption-Firewall policy, automation schedule, "
        "and stored history. Nothing here calls the network."
    ),
}


def define(slug: str) -> str:
    """Return the one-sentence definition for ``slug``, or empty.

    Defensive helper so callers don't have to handle KeyError when
    they reference a term that might be removed in the future.
    """

    entry = TERMS.get(slug)
    return entry[1] if entry else ""


def label(slug: str) -> str:
    """Return the display label for ``slug``, or the slug itself."""

    entry = TERMS.get(slug)
    return entry[0] if entry else slug


class GlossaryScreen(ModalScreen[None]):
    """Lightweight read-only overlay listing every Frontier Scout term."""

    BINDINGS: ClassVar = [
        Binding("escape", "close", "Close", show=False),
        Binding("question_mark", "close", "Close", show=False),
        Binding("?", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    GlossaryScreen {
        align: center middle;
        background: #0b1117 70%;
    }

    GlossaryScreen #glossary-frame {
        width: 76;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        padding: 1 3;
        border: round #24d6a8;
        background: #0d1622;
    }

    GlossaryScreen #glossary-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    GlossaryScreen #glossary-body {
        color: #d9f7ff;
    }

    GlossaryScreen .glossary-term {
        text-style: bold;
        color: #24d6a8;
    }

    GlossaryScreen .glossary-hint {
        color: #6e8aa1;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="glossary-frame"):
            yield Static("Glossary — Frontier Scout vocabulary", id="glossary-title")
            with VerticalScroll(id="glossary-body"):
                # Group: verdicts, concerns, adjacent, modes.
                yield Static(self._rendered_terms(), markup=True)
            yield Static(
                "[#6e8aa1]Esc / q / ? to close.[/]",
                classes="glossary-hint",
                markup=True,
            )

    def _rendered_terms(self) -> str:
        groups: list[tuple[str, tuple[str, ...]]] = [
            (
                "Verdicts",
                ("verdict", "adopt", "trial", "assess", "hold", "fit", "risk", "category"),
            ),
            (
                "Concerns",
                (
                    "concern",
                    "weak_fit",
                    "token_burn",
                    "abandoned",
                    "security_surface",
                    "vendor_lock_in",
                    "marketing_only",
                    "unproven",
                ),
            ),
            (
                "Workflows",
                (
                    "lab",
                    "dossier",
                    "guard",
                    "report",
                    "diff",
                    "permission_manifest",
                    "scout_pack",
                    "universal_mode",
                ),
            ),
        ]
        lines: list[str] = []
        for heading, slugs in groups:
            lines.append(f"\n[#7aa6ff bold]{heading}[/]")
            for slug in slugs:
                lbl, definition = TERMS[slug]
                lines.append(f"  [#24d6a8 bold]{lbl}[/]  [#d9f7ff]{definition}[/]")
        return "\n".join(lines).strip()

    def action_close(self) -> None:
        self.dismiss(None)


__all__ = [
    "GlossaryScreen",
    "TAB_SUBTITLES",
    "TERMS",
    "define",
    "label",
]
