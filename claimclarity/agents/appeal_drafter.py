"""Sub-agent: drafts the actual appeal letter for line items worth appealing,
and an honest plain-language explanation for the ones that aren't."""
from __future__ import annotations

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import AppealPackage, ClaimRecord, DenialFindings

SYSTEM_PROMPT = """\
You write formal insurance appeal letters that get results, and you refuse to \
write a hopeless one just to make a patient feel better.

Rules:
- Use only facts present in the claim record and findings. Never invent \
policy numbers, dates, or clinical details.
- appeal_letter must cover every line item where worth_appealing is true: \
cite the claim number, date of service, the specific denial reason/CARC code \
being contested, the corrected diagnosis code where applicable, and the plan \
term that supports coverage. Address it to the insurer's appeals department \
and leave a signature line for the patient. If NO line items are worth \
appealing, leave appeal_letter empty - do not write a letter with nothing to \
argue.
- non_appeal_explanation must plainly explain, for each line item where \
worth_appealing is false, why appealing would not succeed, in the finding's \
own terms (e.g. plan exclusion). If every item is worth appealing, this can \
be empty.
- open_questions lists decisions only the patient can make: whether to still \
appeal a long-shot item, whether to call their provider's billing office \
about a documentation gap, etc.
- Plain English. This is going to someone who is probably already stressed \
about a medical bill.
"""


def build_appeal_drafter() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def draft_appeal(claim: ClaimRecord, findings: DenialFindings) -> AppealPackage:
    agent = build_appeal_drafter()
    prompt = (
        "CLAIM RECORD (structured JSON):\n"
        f"{claim.model_dump_json(indent=2)}\n\n"
        "DENIAL FINDINGS (structured JSON):\n"
        f"{findings.model_dump_json(indent=2)}\n\n"
        "Produce the appeal package now."
    )
    result = agent(prompt, structured_output_model=AppealPackage)
    return result.structured_output
