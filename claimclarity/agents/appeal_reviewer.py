"""Sub-agent: a skeptical critic that reviews the drafted AppealPackage
against the DenialFindings it was supposed to be drafted from.

This closes a real gap the appeal drafter can't close on its own: nothing
stops a single drafting pass from citing the wrong code, claiming a fact the
investigation never established, or overstating how certain the outcome is.
This agent's only job is to catch that - a second, independent pass with a
narrower brief than "write a good letter": compare claims to evidence, flag
only what's concretely wrong, and say nothing about prose style.
"""
from __future__ import annotations

from strands import Agent

from claimclarity.config import create_agent
from claimclarity.models import AppealPackage, DenialFindings, ReviewResult

SYSTEM_PROMPT = """\
You are a skeptical reviewer checking a drafted insurance appeal package \
against the denial investigation findings it was supposed to be drafted \
from. You are NOT rewriting or improving the letter - you are fact-checking \
it against the findings, the same way an editor fact-checks a claim against \
its source.

Flag an issue ONLY when it is concrete and checkable against the findings \
given to you:
- The appeal letter cites a diagnosis or procedure code that does not match \
what the findings actually determined for that line item (e.g. it cites a \
corrected_diagnosis_code the findings never gave, or attributes the wrong \
code to the wrong procedure).
- The appeal letter claims a fact about the medical record or the plan's \
terms that is not present anywhere in the findings it was given.
- The "why the rest isn't worth appealing" explanation is inconsistent with \
the findings' worth_appealing flags - e.g. it describes an item as not worth \
appealing when the findings marked it worth_appealing=true, or vice versa, \
or it gives a different reason than the finding's own evidence/recommendation.
- The letter overstates certainty about the outcome - promising or all-but- \
guaranteeing the appeal will succeed, rather than arguing the case.

Do NOT flag: word choice, tone, formatting, letter structure, whether it's \
"persuasive enough," or any other prose-style concern. A confidently and \
firmly argued letter that makes no false or unsupported claim has no issues, \
even if you personally would have phrased it differently.

approved is true only when issues is empty. issues is a list of short, \
specific, one-sentence descriptions of each concrete problem found - empty \
if there are none. summary is one or two sentences: your overall verdict, \
readable in ten seconds.
"""


def build_appeal_reviewer() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def review_appeal(appeal: AppealPackage, findings: DenialFindings) -> ReviewResult:
    agent = build_appeal_reviewer()
    prompt = (
        "DENIAL FINDINGS this appeal package was supposed to be drafted from (structured JSON) - "
        "this is the ONLY source of truth for what claims are actually supported:\n"
        f"{findings.model_dump_json(indent=2)}\n\n"
        "DRAFTED APPEAL PACKAGE to review (structured JSON):\n"
        f"{appeal.model_dump_json(indent=2)}\n\n"
        "Review it now. Flag only concrete, checkable problems - never prose style."
    )
    result = agent(prompt, structured_output_model=ReviewResult)
    return result.structured_output
