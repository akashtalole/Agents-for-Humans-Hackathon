"""Enforced guardrail check on the drafted proposal's text: a deterministic,
offline-testable pattern scan for the most dangerous overclaims (no LLM, no
network - the guarantee doesn't depend on a model behaving), combined with a
small, separate agent-based check for subtler violations regex can't catch.

Same "pure code where it matters" discipline as bidwright/tools/history.py:
the deterministic half of this check is either actually there in the text or
it isn't, never a model's fuzzy recollection of what it wrote.
"""
from __future__ import annotations

import re

from strands import Agent

from bidwright.config import create_agent
from bidwright.models import GuardrailFinding, GuardrailResult

# Phrases that overstate compliance - only a real problem when this run has
# open blocking gaps to actually contradict. Matched case-insensitively with
# word boundaries so e.g. "fully compliant" doesn't also match inside some
# unrelated longer word.
_OVERCLAIM_PHRASES = [
    "fully compliant",
    "100% compliant",
    "meets all requirements",
    "no compliance gaps",
    "fully qualifies",
]

# Phrases that promise an outcome the proposal cannot control - flagged
# regardless of whether there are blocking gaps, because a proposal must
# never guarantee an award it doesn't get to decide.
_GUARANTEED_OUTCOME_PHRASES = [
    "guaranteed to win",
    "guaranteed award",
    "guaranteed contract",
]


def _pattern(phrase: str) -> re.Pattern[str]:
    # \b works fine around these phrases since they start/end on word
    # characters; re.escape keeps the literal "%" etc. safe.
    return re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)


def scan_overclaim_patterns(proposal_text: str, has_blocking_gaps: bool) -> list[GuardrailFinding]:
    """Deterministic (no LLM, no network) scan of `proposal_text` for
    concrete overclaim phrases. Offline-testable and safe to run on every
    job's current proposal_draft.md content."""
    findings: list[GuardrailFinding] = []

    if has_blocking_gaps:
        for phrase in _OVERCLAIM_PHRASES:
            for match in _pattern(phrase).finditer(proposal_text):
                findings.append(
                    GuardrailFinding(
                        rule="overstated_compliance_claim",
                        excerpt=match.group(0),
                        explanation=(
                            "This proposal has open blocking compliance gaps but claims full "
                            "compliance."
                        ),
                    )
                )

    for phrase in _GUARANTEED_OUTCOME_PHRASES:
        for match in _pattern(phrase).finditer(proposal_text):
            findings.append(
                GuardrailFinding(
                    rule="guaranteed_outcome_claim",
                    excerpt=match.group(0),
                    explanation=(
                        "A proposal must never promise a contract award outcome it cannot "
                        "control, regardless of compliance status."
                    ),
                )
            )

    return findings


GUARDRAIL_SYSTEM_PROMPT = """\
You are a compliance/legal guardrail reviewer for a small business's RFP \
proposal text. Apply exactly this policy:

Flag any sentence that:
- Promises a contract award outcome (implies the business is certain or \
near-certain to win, be selected, or be awarded the contract).
- Claims a certification, license, or insurance figure without qualification \
when the surrounding context suggests it might not be verified (e.g. stated \
as flat fact with no source, in a way that reads as riskier than a normal \
confident claim).
- Is misleading about compliance status (implies full compliance while \
elsewhere hedging, contradicting itself, or omitting a caveat that changes \
the meaning).

Do not flag ordinary confident sales language that makes no false or \
unverifiable claim - e.g. "we are excited to bring our expertise to this \
project" or "our team is well-suited for this work" are fine and must not \
be flagged.

For each real violation, produce a GuardrailFinding with `rule` as a short \
snake_case label you choose (e.g. "guaranteed_outcome_claim", \
"unverified_certification_claim", "misleading_compliance_claim"), `excerpt` \
as the exact offending sentence or phrase, and `explanation` for why it \
violates the policy. If there are no violations, findings must be empty.
"""


def build_guardrail_agent() -> Agent:
    return create_agent(system_prompt=GUARDRAIL_SYSTEM_PROMPT)


def agent_guardrail_check(proposal_text: str) -> GuardrailResult:
    """Small, separate agent-based check for guardrail violations the
    deterministic regex scan can't catch (paraphrased overclaims, subtler
    misleading language). Kept as its own tiny Agent with a narrow, explicit
    policy rather than folded into a bigger sub-agent's prompt."""
    agent = build_guardrail_agent()
    prompt = f"PROPOSAL TEXT:\n{proposal_text}\n\nApply the guardrail policy now."
    result = agent(prompt, structured_output_model=GuardrailResult)
    return result.structured_output


def run_guardrail_check(proposal_text: str, has_blocking_gaps: bool) -> GuardrailResult:
    """Union of the deterministic pattern scan and the agent-based check.
    passed is true only when neither half found anything."""
    findings = scan_overclaim_patterns(proposal_text, has_blocking_gaps)
    findings += agent_guardrail_check(proposal_text).findings
    return GuardrailResult(passed=len(findings) == 0, findings=findings)
