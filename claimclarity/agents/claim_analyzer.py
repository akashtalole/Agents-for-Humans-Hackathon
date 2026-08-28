"""Sub-agent: turns raw EOB/denial text (plus supporting documents) into a
structured ClaimRecord."""
from __future__ import annotations

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import ClaimRecord

SYSTEM_PROMPT = """\
You are a patient-advocacy claims analyst. You read Explanation of Benefits \
(EOB) / denial notices, plan summaries of benefits, and medical record \
excerpts, and extract exactly what a patient needs to understand and \
possibly appeal a denial.

Rules:
- Extract only what the documents actually state. Never invent a claim \
number, code, or dollar amount that isn't present in the text.
- Capture every denied line item separately, with its own procedure code, \
diagnosis code as billed, denial reason text, and CARC/RARC codes if stated.
- Normalize dates to YYYY-MM-DD when you can determine the actual calendar \
date; otherwise leave the field as the document states it.
- Pull the specific plan terms relevant to the denied services into \
relevant_plan_terms (e.g. coverage limits, exclusions, coinsurance) - this is \
what will be used to judge whether a denial is legitimate.
- clinical_notes_summary should capture the clinical detail that could \
support the correct diagnosis code, if a medical record excerpt is provided.
"""


def build_claim_analyzer() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def analyze_claim(documents_text: str) -> ClaimRecord:
    agent = build_claim_analyzer()
    result = agent(
        "Extract a structured claim record from the following documents (an EOB/denial "
        "notice, and possibly a plan summary of benefits and/or medical record excerpt, "
        "concatenated together):\n\n"
        f"{documents_text}",
        structured_output_model=ClaimRecord,
    )
    return result.structured_output
