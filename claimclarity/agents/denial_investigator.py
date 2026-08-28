"""Sub-agent: classifies each denied line item using real ICD-10 coding data
(via tools, not model memory) plus the plan's own coverage terms.

This is the agent that actually calls lookup_icd10_code / search_icd10_codes
before deciding anything - the whole point is that "is this code even valid"
gets answered by a lookup, not a guess.
"""
from __future__ import annotations

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import ClaimRecord, DenialFindings
from claimclarity.tools.icd10 import lookup_icd10_code, search_icd10_codes

SYSTEM_PROMPT = """\
You are a meticulous claims investigator working for the patient, not the \
insurer. For every denied line item, you determine whether the denial is a \
mechanical billing error, a documentation gap, or a legitimate coverage \
denial - and you back that judgment with evidence, not guesswork.

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
of documentation, classify "valid_denial" and worth_appealing=false - do not \
recommend appealing something that cannot succeed. If more documentation \
(e.g. prior authorization, medical necessity letter) would be needed to \
resolve it, classify "documentation_gap". If you genuinely cannot tell from \
the documents provided, classify "needs_review".
4. Never claim a code is invalid or valid without having called \
lookup_icd10_code on it first.

evidence must cite the specific tool result and/or plan term that drove your \
classification - be concrete, not vague. overall_recommendation is one or two \
sentences a stressed patient can read in ten seconds.
"""


def build_denial_investigator() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT, tools=[lookup_icd10_code, search_icd10_codes])


def investigate_denial(claim: ClaimRecord) -> DenialFindings:
    agent = build_denial_investigator()
    prompt = (
        "CLAIM RECORD (structured JSON):\n"
        f"{claim.model_dump_json(indent=2)}\n\n"
        "Investigate every denied line item now. Use your tools before concluding anything "
        "about diagnosis code validity."
    )
    result = agent(prompt, structured_output_model=DenialFindings)
    return result.structured_output
