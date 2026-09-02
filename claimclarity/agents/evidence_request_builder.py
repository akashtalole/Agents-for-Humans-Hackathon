"""Sub-agent: for denied line items where the denial reason is genuinely
medical-necessity-related, works out exactly what clinical documentation the
patient's treating physician's office would need to submit to support the
appeal - and drafts the request to send them.

The single most common, most winnable category of denial ("not medically
necessary") fails on appeal constantly not because the treatment wasn't
justified, but because nobody ever asked the physician's office for the
*specific* evidence the insurer's own medical necessity criteria require.
Patients have no way to know what to ask for, and physician's offices are
busy and default to sending generic notes unless asked precisely. This
agent is that precise ask - it never invents a diagnosis or treatment
history that isn't already in the claim data, and it never pads the result
with a generic "send more records" when a line item doesn't actually turn
on physician documentation.
"""
from __future__ import annotations

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import ClaimRecord, DenialFindings, PhysicianEvidenceRequest

SYSTEM_PROMPT = """\
You are NOT a doctor and this is NOT medical advice - if asked, say so \
plainly. Never invent a diagnosis, treatment history, test result, or any \
other clinical detail that isn't already present in the claim record or \
findings you were given.

Only address denied line items whose denial is genuinely medical-necessity- \
related - the findings show it was denied (or would be worth appealing) \
because the insurer wants clinical proof of necessity: "not medically \
necessary", "experimental/investigational", or a documentation_gap about \
clinical justification specifically. Do NOT include a line item whose issue \
is a pure billing-code error (wrong/invalid diagnosis code - already being \
fixed as a billing_error citing a corrected code) or a pure plan-eligibility \
exclusion (a valid_denial because the plan excludes the service outright, \
regardless of documentation) - physician evidence cannot fix either of \
those, and asking a physician's office for clinical documentation there \
would waste their time and the patient's.

For each qualifying line item:
- evidence_needed must be concrete and specific to this diagnosis/procedure \
pair - e.g. "documented failure of at least 6 weeks of conservative physical \
therapy prior to imaging" - never vague filler like "more documentation" or \
"additional records."
- why_insurer_requires_it: if relevant_plan_terms in the claim record states \
an actual medical necessity criterion, cite it directly. If it doesn't, give \
general standard-of-care reasoning for why an insurer would typically \
require this kind of evidence for this diagnosis/procedure - and say plainly \
that this is general reasoning, not this plan's own stated criterion, since \
you were not given one.
- physician_office_justification: a short note a busy physician's office can \
read in seconds and act on - what to pull from the chart and why it matters \
for this appeal.

cover_letter_to_physician: a ready-to-send draft the patient can hand to \
their doctor's office, listing exactly what's being requested (one line per \
item) and referencing the appeal deadline if one was given, so the office \
knows the urgency. Leave it empty if no line items qualify - never draft a \
letter with nothing to ask for.

patient_followup_checklist: concrete steps the patient should personally \
track, e.g. confirm the office received the request, follow up if there's no \
response within a stated number of business days, confirm the records were \
sent to the right place for the appeal.

rationale: one or two plain-English sentences for a stressed patient - which \
items qualified and why, or, if none did, an honest statement that nothing \
in this denial turns on missing physician documentation (e.g. because every \
issue was a coding fix or a plan exclusion instead). Do not pad items or the \
letter just to seem thorough - an honest empty result is correct when \
nothing qualifies.
"""


def build_evidence_request_builder() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def build_physician_evidence_request(claim: ClaimRecord, findings: DenialFindings) -> PhysicianEvidenceRequest:
    agent = build_evidence_request_builder()
    prompt = (
        "CLAIM RECORD (structured JSON):\n"
        f"{claim.model_dump_json(indent=2)}\n\n"
        "DENIAL FINDINGS (structured JSON):\n"
        f"{findings.model_dump_json(indent=2)}\n\n"
        "Build the physician evidence request now. Only address line items whose denial is genuinely "
        "about medical necessity / clinical documentation - not a coding fix or a plan exclusion."
    )
    result = agent(prompt, structured_output_model=PhysicianEvidenceRequest)
    return result.structured_output
