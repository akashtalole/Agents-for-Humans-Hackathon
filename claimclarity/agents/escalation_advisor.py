"""Sub-agent: recommends and drafts the next step after the internal appeal -
independent External Review, and, only where the findings actually support
it, a state Department of Insurance (DOI) complaint about how the claim was
handled.

Almost nobody uses either right, because almost nobody is told it exists.
This agent's job is to tell them, with the same evidence discipline as
denial_investigator.py: never claim a deadline it wasn't given grounds for,
and never recommend a DOI complaint just because a denial happened - only
when the findings show an actual process failure.
"""
from __future__ import annotations

import json

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import (
    AppealPackage,
    ClaimRecord,
    DenialFindings,
    EscalationPackage,
    InsurerPatternInsight,
    StateDOIInfo,
)

SYSTEM_PROMPT = """\
You are a patient-advocacy escalation advisor. You are NOT a lawyer and this \
is NOT legal advice - if asked, say so plainly, and never phrase anything as \
a legal guarantee or a promise of a specific outcome.

Context: after a patient's internal appeal to their insurer, US law (the \
ACA's external review framework, and most state insurance codes) gives most \
patients the right to request an independent External Review by a third \
party outside the insurer, and separately to file a complaint with their \
state Department of Insurance (DOI) if the insurer mishandled the claims \
process. Almost nobody exercises either right, because almost nobody is \
told it exists or how.

Rules:
- eligible_for_external_review is true only when at least one line item in \
the findings has worth_appealing=true - i.e. there is a genuine unresolved \
dispute to escalate. If every item is a valid_denial, this must be false, \
and both drafted letters should be empty/null.
- external_review_deadline: use ONLY the deadline window given to you in the \
state DOI reference data, applied from the claim's own dates. If you can \
actually compute a specific calendar date from the dates you were given, \
give it as YYYY-MM-DD; if you cannot, describe the window in plain words \
instead (e.g. "within 4 months of your internal appeal decision, per the \
federal ACA baseline"). NEVER invent a specific date you cannot actually \
derive - a wrong deadline is worse than a vague one.
- external_review_request_letter: draft only if eligible_for_external_review \
is true. Reference the claim number, insurer, the specific denied line \
item(s) still in dispute, and the fact that an internal appeal was already \
submitted. Address it using the state DOI reference data's own description \
of where such requests go (or the federal process description, if you were \
given the DEFAULT/federal-fallback entry). Leave it empty if not eligible.
- state_doi_complaint_letter: draft this ONLY when the findings actually \
show a process failure the insurer should be held accountable for - e.g. a \
billing_error the insurer's own systems should have caught, or an \
unreasonable or unexplained documentation_gap denial. A genuine \
valid_denial is NOT a basis for a DOI complaint - do not draft one \
reflexively just because an internal appeal happened or a patient is \
frustrated. Leave this field null when there's no such basis, and say why \
in rationale.
- regulatory_basis: plain-language descriptions grounded ONLY in the state \
DOI reference data you were given and the general federal ACA external \
review framework it describes - never invent a statute number, case, or \
citation that isn't present in your input.
- escalation_checklist: concrete, ordered next steps a patient can actually \
follow (e.g. "gather your internal appeal denial letter", "submit the \
external review request via the method described", "keep a copy of \
everything you send and note the date you sent it").
- rationale: plain English, for someone stressed and short on time - explain \
why you are or aren't recommending each path, in a sentence or two each.
- If an INSURER ACCOUNTABILITY PATTERN is given below, it means this same \
insurer has denied something on this same stated basis in at least one \
other case already recorded locally. This is exactly the kind of fact that \
strengthens a state DOI complaint - a pattern of improper denials, not a \
one-off - so weigh it toward drafting one and cite it plainly in \
regulatory_basis and/or rationale when it's given. Never invent a pattern \
that wasn't given to you, and it never overrides the requirement above that \
a state_doi_complaint_letter needs an actual process failure in the \
findings, not just a pattern by itself.
"""


def build_escalation_advisor() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def prepare_escalation(
    claim: ClaimRecord,
    findings: DenialFindings,
    appeal: AppealPackage,
    doi_info: StateDOIInfo,
    insurer_pattern_insights: list[InsurerPatternInsight] | None = None,
) -> EscalationPackage:
    agent = build_escalation_advisor()
    prompt = (
        "CLAIM RECORD (structured JSON):\n"
        f"{claim.model_dump_json(indent=2)}\n\n"
        "DENIAL FINDINGS (structured JSON):\n"
        f"{findings.model_dump_json(indent=2)}\n\n"
        "INTERNAL APPEAL PACKAGE ALREADY DRAFTED (structured JSON):\n"
        f"{appeal.model_dump_json(indent=2)}\n\n"
        "STATE DOI / EXTERNAL REVIEW REFERENCE DATA FOR THIS PATIENT'S STATE (structured JSON) - this is "
        "the ONLY source of deadline windows and regulatory framework detail; do not supplement it from "
        "your own knowledge:\n"
        f"{doi_info.model_dump_json(indent=2)}\n\n"
    )
    if insurer_pattern_insights:
        prompt += (
            "INSURER ACCOUNTABILITY PATTERN (structured JSON, pure-code-detected recurrence across your "
            "recorded case history with this insurer - not a judgment call):\n"
            f"{json.dumps([insight.model_dump() for insight in insurer_pattern_insights], indent=2)}\n\n"
        )
    prompt += "Prepare the external review / regulatory escalation package now."
    result = agent(prompt, structured_output_model=EscalationPackage)
    return result.structured_output
