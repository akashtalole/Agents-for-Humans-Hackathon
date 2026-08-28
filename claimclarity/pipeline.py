"""Top-level convenience wrapper used by both the CLI and the Streamlit demo."""
from __future__ import annotations

from dataclasses import dataclass

from claimclarity.orchestrator import ClaimCase, build_orchestrator

TASK_PROMPT = (
    "Process this claim denial end to end: load the documents, extract the claim "
    "details, create an appeal deadline reminder, investigate the denial using "
    "real ICD-10 code checks, and draft the appeal package. Then give me the "
    "final summary."
)


@dataclass
class ClaimCaseResult:
    case: ClaimCase
    summary_text: str


def run_claim_case(documents_paths: list[str], output_dir: str, callback_handler=None) -> ClaimCaseResult:
    """Run the full ClaimClarity pipeline for one claim and return the result.

    `documents_paths` is typically the denial notice/EOB plus, if available,
    a plan summary of benefits and a medical record excerpt - pass whatever
    you have; a denial notice alone is enough to run the pipeline, just with
    less to reason about.

    Pass `callback_handler` (see Strands' Agent callback_handler parameter) to
    stream tool-call events live, e.g. for a UI activity log.
    """
    case = ClaimCase(documents_paths=documents_paths, output_dir=output_dir)
    orchestrator = build_orchestrator(case, callback_handler=callback_handler)
    result = orchestrator(TASK_PROMPT)
    return ClaimCaseResult(case=case, summary_text=str(result))
