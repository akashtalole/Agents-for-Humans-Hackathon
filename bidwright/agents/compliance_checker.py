"""Sub-agent: compares extracted RFP requirements against a company's profile
and flags gaps that need a human decision."""
from __future__ import annotations

from strands import Agent

from bidwright.config import create_agent
from bidwright.models import ComplianceReport, RFPRequirements

SYSTEM_PROMPT = """\
You are a meticulous compliance officer for a small business that bids on \
contracts. You are given a structured list of RFP requirements and a \
company's capability profile, and you decide which requirements are met, \
which are gaps, and which need human review.

Rules:
- Be conservative. Never mark a requirement "met" unless the company profile \
explicitly supports it. If the profile is silent on something, mark it \
"needs_review", not "met".
- severity="blocking" for anything the RFP describes as a mandatory \
eligibility requirement (required certification, minimum insurance, required \
license). severity="warning" for anything scored/preferred but not mandatory. \
severity="info" for informational-only items.
- For every gap, give a concrete, actionable recommendation a business owner \
could act on this week, e.g. "Increase general liability coverage from \
$1,000,000 to the required $2,000,000 minimum before the deadline" or \
"Confirm with your insurance broker whether your existing policy already \
qualifies."
- overall_status is "ready" only if there are zero blocking gaps. Otherwise \
it is "gaps_found".
- List every requirement that IS met in met_requirements, briefly.
"""


def build_compliance_checker() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def check_compliance(requirements: RFPRequirements, profile_text: str) -> ComplianceReport:
    agent = build_compliance_checker()
    prompt = (
        "RFP REQUIREMENTS (structured JSON):\n"
        f"{requirements.model_dump_json(indent=2)}\n\n"
        "COMPANY CAPABILITY PROFILE:\n"
        f"{profile_text}\n\n"
        "Produce the compliance report now."
    )
    result = agent(prompt, structured_output_model=ComplianceReport)
    return result.structured_output
