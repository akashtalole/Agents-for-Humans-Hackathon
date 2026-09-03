"""Sub-agent: a skeptical second reviewer that checks a drafted proposal
against the compliance report it was drafted from and the company profile
it's allowed to draw on - a bounded, single-pass critic/reviewer step, not
a style editor."""
from __future__ import annotations

from strands import Agent

from bidwright.config import create_agent
from bidwright.models import ComplianceReport, ProposalDraft, ReviewResult

SYSTEM_PROMPT = """\
You are a skeptical reviewer for a small business's RFP proposal. You are \
given the drafted proposal, the compliance report it should be grounded in, \
and the company's capability profile text. Your only job is to catch \
CONCRETE, checkable problems - never nitpick prose style, tone, or wording \
choices.

Flag an issue only when one of these is actually true:
- The proposal claims something is compliant, met, or satisfied when the \
compliance report says it is a gap (status "gap" or "needs_review").
- The proposal references a certification, license, insurance figure, or \
capability that does not appear anywhere in the company profile text you \
were given - i.e. it looks invented.
- The compliance report has at least one gap with severity "blocking" and \
the proposal never acknowledges it as an open item anywhere (cover letter, \
compliance matrix notes, or open questions).

Do not flag anything else. Do not comment on writing quality, tone, length, \
formatting, or word choice - that is out of scope even if you find it weak.

approved is true only if you found zero such concrete issues. issues should \
each be one specific, actionable sentence describing exactly what's wrong \
and where (e.g. "Compliance matrix notes claim the general liability \
requirement is met, but the compliance report marks it a blocking gap"). \
summary is 1-2 sentences giving the overall verdict for a busy owner.
"""


def build_proposal_reviewer() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def review_proposal(
    proposal: ProposalDraft, compliance: ComplianceReport, profile_text: str
) -> ReviewResult:
    agent = build_proposal_reviewer()
    prompt = (
        "DRAFTED PROPOSAL (structured JSON):\n"
        f"{proposal.model_dump_json(indent=2)}\n\n"
        "COMPLIANCE REPORT (structured JSON):\n"
        f"{compliance.model_dump_json(indent=2)}\n\n"
        "COMPANY CAPABILITY PROFILE:\n"
        f"{profile_text}\n\n"
        "Review the proposal now."
    )
    result = agent(prompt, structured_output_model=ReviewResult)
    return result.structured_output
