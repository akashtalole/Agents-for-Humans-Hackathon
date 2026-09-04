"""Sub-agent: an independent second opinion on each denied line item's
classification.

Unlike `appeal_reviewer.py` (which revises the SAME agent's own drafted
appeal after seeing its output), this agent re-investigates every denied
line item from scratch - the same ClaimRecord `denial_investigator.py`
used, including the same real ICD-10 lookup tools, but with no knowledge of
what that first investigation concluded. Because `LineItemFinding` carries
a stable `procedure_code`, comparing the two independent findings lists
doesn't need an LLM at all - see `compare_denial_findings` below, plain
code matching by procedure_code and diffing `classification` directly. A
genuine disagreement is never silently resolved in favor of either
investigation - see `orchestrator.py`'s `cross_verify_denial_findings`.
"""
from __future__ import annotations

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import ClaimRecord, DenialCrossCheck, DenialCrossCheckItem, DenialFindings
from claimclarity.tools.icd10 import lookup_icd10_code, search_icd10_codes

AUDITOR_SYSTEM_PROMPT = """\
You are a second, independent claims investigator working for the patient - \
a skeptical, adversarial check on a first investigator's work, not a \
replacement for it. You are given the same structured claim record a first \
investigator already assessed, but you have NOT seen their conclusions and \
must reach your own from scratch.

Process, for every line item with a diagnosis code:
1. ALWAYS call lookup_icd10_code on the diagnosis code as billed before \
concluding anything about it. Do not rely on your own knowledge of whether a \
code is billable - the tool is the source of truth.
2. If the code is not billable (e.g. a category header), call \
search_icd10_codes using terms from the clinical notes to find the correct, \
specific billable code, and propose it as corrected_diagnosis_code.
3. Compare the denial reason and plan terms: if the service is covered under \
the plan and the only problem is the code, classify "billing_error" and \
worth_appealing=true. If the plan explicitly excludes the service regardless \
of documentation, classify "valid_denial" and worth_appealing=false. If more \
documentation would resolve it, classify "documentation_gap". If you \
genuinely cannot tell, classify "needs_review".
4. Be skeptical of an easy "billing_error" conclusion - actively look for a \
plan exclusion or documentation problem a more lenient first pass might \
have missed. Never claim a code is invalid or valid without having called \
lookup_icd10_code on it first.

evidence must cite the specific tool result and/or plan term that drove your \
classification.
"""


def build_denial_auditor() -> Agent:
    return create_agent(system_prompt=AUDITOR_SYSTEM_PROMPT, tools=[lookup_icd10_code, search_icd10_codes])


def audit_denial(claim: ClaimRecord) -> DenialFindings:
    agent = build_denial_auditor()
    prompt = (
        "CLAIM RECORD (structured JSON):\n"
        f"{claim.model_dump_json(indent=2)}\n\n"
        "Investigate every denied line item now, independently. Use your tools before "
        "concluding anything about diagnosis code validity."
    )
    result = agent(prompt, structured_output_model=DenialFindings)
    return result.structured_output


def compare_denial_findings(first: DenialFindings, second: DenialFindings) -> DenialCrossCheck:
    """Plain-code diff, no LLM: both findings lists carry a stable
    `procedure_code` per line item (both investigations worked from the same
    ClaimRecord), so matching and comparing classifications is exact rather
    than a semantic-matching problem."""
    second_by_code = {f.procedure_code: f for f in second.findings}
    items: list[DenialCrossCheckItem] = []
    disagreement_count = 0

    for first_item in first.findings:
        second_item = second_by_code.get(first_item.procedure_code)
        second_classification = (
            second_item.classification.value if second_item is not None else "not assessed by auditor"
        )
        agrees = second_item is not None and second_item.classification == first_item.classification
        if not agrees:
            disagreement_count += 1
        items.append(
            DenialCrossCheckItem(
                procedure_code=first_item.procedure_code,
                first_classification=first_item.classification.value,
                second_classification=second_classification,
                agrees=agrees,
            )
        )

    if disagreement_count == 0:
        summary = f"Both investigations agree on all {len(items)} line item(s)."
    else:
        summary = (
            f"{disagreement_count} of {len(items)} line item(s) received a different classification "
            "from the independent auditor - each is forced to needs_review rather than trusting "
            "either investigation alone."
        )

    return DenialCrossCheck(items=items, disagreement_count=disagreement_count, summary=summary)
