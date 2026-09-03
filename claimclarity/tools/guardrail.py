"""Guardrail checks run against a drafted appeal letter before a patient is
asked to approve it.

Two independent layers, combined:
- `scan_guaranteed_outcome_claims` is deterministic, pure code, no network -
  the same "this should be a plain function, not a model judgment" discipline
  as tools/history.py:detect_insurer_patterns. It catches the narrow, exact
  thing it's built to catch: language that promises a specific outcome. An
  appeal's outcome is never something ClaimClarity can guarantee, no matter
  how strong the findings look.
- `agent_guardrail_check` is a small, separate Strands Agent with a narrower
  policy than the appeal drafter or reviewer, for the subtler violations a
  regex can't catch - an unsupported medical claim, or something that reads
  as legal advice.

`run_guardrail_check` unions both, so a real violation missed by one layer
still gets caught by the other.
"""
from __future__ import annotations

import re

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import GuardrailFinding, GuardrailResult

_GUARANTEED_OUTCOME_PATTERNS = [
    r"\bguarantee(?:d)?\b",
    r"\bwill be approved\b",
    r"\byou will win\b",
    r"\b100% covered\b",
    r"\bcertain to (?:succeed|win)\b",
    r"\bwe promise\b",
]
_GUARANTEED_OUTCOME_RE = re.compile("|".join(_GUARANTEED_OUTCOME_PATTERNS), re.IGNORECASE)

_EXPLANATION = "An appeal letter must never promise a specific outcome to the patient."


def scan_guaranteed_outcome_claims(appeal_text: str) -> list[GuardrailFinding]:
    """Case-insensitively scan `appeal_text` for phrases that promise or
    guarantee a specific appeal outcome. Deterministic - no LLM, no network,
    offline-testable. One GuardrailFinding per match.
    """
    if not appeal_text:
        return []
    return [
        GuardrailFinding(
            rule="guaranteed_outcome_claim",
            excerpt=match.group(0),
            explanation=_EXPLANATION,
        )
        for match in _GUARANTEED_OUTCOME_RE.finditer(appeal_text)
    ]


AGENT_SYSTEM_PROMPT = """\
You are a compliance guardrail check for a drafted health insurance appeal \
letter. Your policy, exactly:

Flag any sentence that:
1. Promises or guarantees a specific appeal outcome, or
2. States a medical diagnosis or fact not clearly attributable to the \
provided findings, or
3. Gives legal advice beyond describing the appeal/escalation process.

Do not flag ordinary firm, confident advocacy language that makes no false \
or unsupported claim - a letter is allowed to argue its case forcefully. \
Only flag concrete, checkable violations of the three rules above.

For each violation, produce a GuardrailFinding with rule set to one of \
"guaranteed_outcome_claim", "unsupported_medical_claim", or "legal_advice", \
excerpt set to the exact offending text, and explanation set to a short, \
specific reason it violates the policy. passed is true only when findings is \
empty.
"""


def build_guardrail_agent() -> Agent:
    return create_agent(system_prompt=AGENT_SYSTEM_PROMPT)


def agent_guardrail_check(appeal_text: str) -> GuardrailResult:
    """Run the agent-based guardrail check against `appeal_text` - catches
    subtler violations (an unsupported medical claim, disguised legal advice)
    the deterministic regex scan misses."""
    agent = build_guardrail_agent()
    prompt = (
        "APPEAL LETTER TEXT TO CHECK:\n"
        f"{appeal_text}\n\n"
        "Check it against your policy now."
    )
    result = agent(prompt, structured_output_model=GuardrailResult)
    return result.structured_output


def run_guardrail_check(appeal_text: str) -> GuardrailResult:
    """Combine the deterministic and agent-based guardrail checks. passed is
    true only when neither layer found anything."""
    findings = scan_guaranteed_outcome_claims(appeal_text) + agent_guardrail_check(appeal_text).findings
    return GuardrailResult(passed=len(findings) == 0, findings=findings)
