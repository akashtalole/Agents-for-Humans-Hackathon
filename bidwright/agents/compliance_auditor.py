"""Sub-agent: an independent second opinion on RFP compliance.

Unlike `proposal_reviewer.py` (which revises the SAME agent's own drafted
proposal after seeing its output), this agent re-derives a compliance
verdict from scratch - the same structured requirements and company
profile `compliance_checker.py` used, but with no knowledge of what that
first check concluded. A genuine disagreement between two independent
assessments is a stronger correctness signal than a single LLM call, and
is never silently resolved here in favor of either agent - see
`orchestrator.py`'s `cross_verify_compliance` tool, which forces any
disputed requirement to `needs_review` regardless of which agent was
right.
"""
from __future__ import annotations

from strands import Agent

from bidwright.config import create_agent
from bidwright.models import ComplianceCrossCheck, ComplianceReport, RFPRequirements

AUDITOR_SYSTEM_PROMPT = """\
You are a second, independent compliance auditor for a small business that \
bids on contracts - a skeptical, adversarial check on a first reviewer's \
work, not a replacement for it. You are given the same structured RFP \
requirements and the same company capability profile a first reviewer \
already assessed, but you have NOT seen their conclusions and must reach \
your own from scratch.

Rules:
- Assume the first reviewer may have been too lenient. Actively look for \
reasons a requirement might not actually be met even if the profile seems \
to imply it is - vague wording, an ambiguous certification, a coverage \
amount that's close but not clearly sufficient.
- Be conservative. Never mark a requirement "met" unless the company \
profile explicitly supports it. If the profile is silent on something, \
mark it "needs_review", not "met".
- severity="blocking" for anything the RFP describes as a mandatory \
eligibility requirement (required certification, minimum insurance, \
required license). severity="warning" for anything scored/preferred but \
not mandatory. severity="info" for informational-only items.
- For every gap, give a concrete, actionable recommendation.
- overall_status is "ready" only if there are zero blocking gaps. \
Otherwise it is "gaps_found".
- List every requirement that IS met in met_requirements, briefly.
"""

COMPARE_SYSTEM_PROMPT = """\
You compare two independently-produced compliance reports for the SAME RFP \
and company, written by two separate reviewers who did not see each \
other's work. Your only job is to find genuine disagreements - cases where \
one reviewer's conclusion (met vs. gap vs. needs_review, and blocking vs. \
not) differs from the other's for what is clearly the same underlying \
requirement, even if worded differently. Do not invent disagreements over \
minor wording differences that don't change the actual conclusion. For \
every disagreement, copy the requirement text EXACTLY as it appears in the \
first report (verbatim) so it can be matched programmatically. Count how \
many requirements the two reports substantively agree on.
"""


def build_compliance_auditor() -> Agent:
    return create_agent(system_prompt=AUDITOR_SYSTEM_PROMPT)


def audit_compliance(requirements: RFPRequirements, profile_text: str) -> ComplianceReport:
    agent = build_compliance_auditor()
    prompt = (
        "RFP REQUIREMENTS (structured JSON):\n"
        f"{requirements.model_dump_json(indent=2)}\n\n"
        "COMPANY CAPABILITY PROFILE:\n"
        f"{profile_text}\n\n"
        "Produce your own independent compliance report now."
    )
    result = agent(prompt, structured_output_model=ComplianceReport)
    return result.structured_output


def compare_compliance_reports(first: ComplianceReport, second: ComplianceReport) -> ComplianceCrossCheck:
    agent = create_agent(system_prompt=COMPARE_SYSTEM_PROMPT)
    prompt = (
        "FIRST REPORT:\n"
        f"{first.model_dump_json(indent=2)}\n\n"
        "SECOND (INDEPENDENT) REPORT:\n"
        f"{second.model_dump_json(indent=2)}\n\n"
        "Produce the cross-check now."
    )
    result = agent(prompt, structured_output_model=ComplianceCrossCheck)
    return result.structured_output
