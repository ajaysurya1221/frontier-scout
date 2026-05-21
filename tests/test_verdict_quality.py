"""
Verdict quality gate — uses deepeval to score Scout's verdicts against known truths.

Runs on every PR via GitHub Actions. Live tests (those that
hit Anthropic) are gated behind the `live` marker — invoke with `-m live` to
run them.

Golden truths reflect *policy decisions*, not just model expectations. Each
golden carries a rationale comment explaining why we hold that position.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="deepeval.*")

# Mark the entire file as 'live' — all tests here require ANTHROPIC_API_KEY
# and make real API calls. CI runs them via `pytest -m live` only on PRs.
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("OPENAI_API_KEY"),
        reason="ANTHROPIC_API_KEY and OPENAI_API_KEY are required for live verdict quality tests",
    ),
]


# Round 3 — golden truths updated based on reviewer's live-test findings.
# Each entry documents the policy rationale for its expected label.
GOLDEN = [
    # ADOPT — proven, SOC2-attested, already in stack
    {"tool": "LangGraph",         "verdict": "adopt", "soc2": "safe"},
    # rationale: backbone of the example agent stack; LangChain investment; LangSmith SOC2 path.

    {"tool": "LangSmith",         "verdict": "adopt", "soc2": "safe"},
    # rationale: official observability; SOC2 Type II; already adopted in many LangChain teams.

    {"tool": "ccusage",           "verdict": "adopt", "soc2": "safe"},
    # rationale: read-only cost telemetry; no PII surface; trivial integration.

    # TRIAL — promising, needs lab validation
    {"tool": "mem0",              "verdict": "trial", "soc2": "conditional"},
    # rationale: self-host required; no formal SOC2 attestation; clear lab path.

    # ASSESS — emerging or stack-adjacent
    {"tool": "Hermes Agent",      "verdict": "assess", "soc2": "conditional"},
    # rationale: emerging framework; not yet warranting lab time.

    {"tool": "deepagents",        "verdict": "assess", "soc2": "conditional"},
    # rationale (Round 3 update): the model rates this conditional because it's
    # a younger LangChain experimental project. Reviewer confirmed this is a
    # reasonable policy stance — younger projects without org backing default
    # to conditional. Updated from prior "safe".

    {"tool": "agentskills.io",    "verdict": "trial",  "soc2": "conditional"},
    # rationale (final audit): the model rates SOC2 status `conditional`
    # because the skill-marketplace pattern doesn't yet carry a vendor
    # attestation; it's an open ecosystem where individual skills are
    # third-party content. The model is right to be conservative. Verdict
    # stays `trial` — emerging-but-actionable in a single sprint.

    # CONDITIONAL — usable with caveats
    {"tool": "Claude Code",       "verdict": "adopt", "soc2": "conditional"},
    # rationale (Round 3 update): SOC2 status is conditional pending the
    # `.claudeignore` + secret-scanning + regulated-data exclusion controls
    # that the team must put in place to use this safely on sensitive data. The model
    # was right; the prior "safe" golden was wrong policy. Verdict stays
    # ADOPT because we *are* using it.

    # HOLD — not for us
    {"tool": "Google ADK Python", "verdict": "hold", "soc2": "conditional"},
    # rationale: Vertex AI lock-in adds GCP as a vendor; rewrite cost prohibitive.

    {"tool": "LiteLLM",           "verdict": "trial", "soc2": "conditional"},
    # rationale (Round 3 update): the model rates this trial, not hold, because
    # the proxy is a legitimate cost/governance lever IF self-hosted. Reviewer
    # confirmed this is more defensible than a blanket hold. Updated from
    # prior "hold". Trial = self-host required, no prod data.
]


def _generate_verdict(tool: str) -> dict:
    """Call Scout's verdict pipeline on a synthetic input describing the tool."""
    import anthropic
    from prompts import cached_system_blocks
    from tools import VERDICT_TOOL

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=cached_system_blocks(),
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "emit_verdicts"},
        messages=[{
            "role": "user",
            "content": (
                f"Emit a verdict for the tool '{tool}'. "
                f"Apply the standard evaluation rubric. Use realistic stack context — "
                f"The team builds AI-native software on Python/FastAPI/LangGraph/AWS."
            ),
        }],
    )
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return tool_use.input["verdicts"][0]


@pytest.mark.parametrize("case", GOLDEN, ids=[g["tool"] for g in GOLDEN])
def test_verdict_quality(case):
    from deepeval import assert_test
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    metric = GEval(
        name="Verdict Correctness",
        criteria=(
            "The verdict should: (1) match the expected adopt/trial/assess/hold label, "
            "(2) correctly identify SOC2 status, (3) reference the configured stack specifically, "
            "(4) avoid generic marketing language."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.7,
    )
    actual = _generate_verdict(case["tool"])
    test_case = LLMTestCase(
        input=f"Evaluate: {case['tool']}",
        actual_output=(
            f"verdict={actual['verdict']} soc2={actual['soc2']} "
            f"what={actual['what']} why={actual['why_it_matters']}"
        ),
        expected_output=f"verdict={case['verdict']} soc2={case['soc2']}",
    )
    assert actual["verdict"] == case["verdict"], (
        f"{case['tool']}: got verdict={actual['verdict']}, expected={case['verdict']}"
    )
    assert actual["soc2"] == case["soc2"], (
        f"{case['tool']}: got soc2={actual['soc2']}, expected={case['soc2']}"
    )
    assert_test(test_case, [metric])


# The incident-as-ADOPT regression lives in tests/test_validators.py — it
# doesn't require an API call (validators are pure Python) and should run on
# every PR regardless of ANTHROPIC_API_KEY availability.
