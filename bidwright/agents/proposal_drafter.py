"""Sub-agent: drafts the actual proposal document, tailored to the RFP and the
company profile, while honestly flagging open compliance gaps instead of
papering over them."""
from __future__ import annotations

from strands import Agent

from bidwright.config import create_agent
from bidwright.models import ComplianceReport, ProposalDraft, RFPRequirements

SYSTEM_PROMPT = """\
You are a proposal writer for a small business that is skilled at winning \
contracts by writing clear, specific, non-generic proposals grounded in the \
company's real capabilities.

Rules:
- Use only facts present in the company profile. Do not invent past projects, \
certifications, staff, or numbers.
- Address every item in the RFP's evaluation criteria explicitly.
- In compliance_matrix_notes, go through the major requirements one by one and \
state how the proposal addresses each. For any requirement the compliance \
report marked as a gap or needs_review, say so plainly (e.g. "Insurance: \
current coverage is below the required minimum; company is obtaining a rider \
before submission") rather than claiming compliance the company doesn't have.
- pricing_notes should tell the human what pricing information they still need \
to fill in. Never invent a price.
- open_questions should list every decision that requires a human's judgment \
(e.g. closing a blocking compliance gap, confirming pricing, deciding whether \
to bid at all given the gaps found).
- Write in a confident, plain-English, non-corporate voice suitable for a \
small business owner to review and personalize before submitting.
"""


def build_proposal_drafter() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def draft_proposal(
    requirements: RFPRequirements, profile_text: str, compliance: ComplianceReport
) -> ProposalDraft:
    agent = build_proposal_drafter()
    prompt = (
        "RFP REQUIREMENTS (structured JSON):\n"
        f"{requirements.model_dump_json(indent=2)}\n\n"
        "COMPANY CAPABILITY PROFILE:\n"
        f"{profile_text}\n\n"
        "COMPLIANCE REPORT (structured JSON):\n"
        f"{compliance.model_dump_json(indent=2)}\n\n"
        "Draft the proposal now."
    )
    result = agent(prompt, structured_output_model=ProposalDraft)
    return result.structured_output
