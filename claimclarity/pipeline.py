"""Top-level convenience wrapper used by both the CLI and the Streamlit demo."""
from __future__ import annotations

from dataclasses import dataclass

from claimclarity.orchestrator import ClaimCase, build_orchestrator

TASK_PROMPT = (
    "Process this claim denial end to end: load the documents, extract the claim "
    "details, create an appeal deadline reminder, investigate the denial using "
    "real ICD-10 code checks, record this case and check for recurring insurer "
    "denial patterns, build the physician evidence request for anything "
    "that turns on medical necessity, draft the appeal package, review it and "
    "revise if needed (bounded to one revision pass), run the appeal guardrail "
    "check, and prepare the external review / regulatory escalation package. "
    "Then give me the final summary."
)


@dataclass
class ClaimCaseResult:
    case: ClaimCase
    summary_text: str


def run_claim_case(
    documents_paths: list[str],
    output_dir: str,
    history_file: str = "claimclarity_history.json",
    callback_handler=None,
) -> ClaimCaseResult:
    """Run the full ClaimClarity pipeline for one claim and return the result.

    `documents_paths` is typically the denial notice/EOB plus, if available,
    a plan summary of benefits and a medical record excerpt - pass whatever
    you have; a denial notice alone is enough to run the pipeline, just with
    less to reason about.

    `history_file` is the persistent cross-run insurer accountability history
    JSON file (see claimclarity/tools/history.py) - deliberately independent
    of `output_dir` by default, since it needs to persist and accumulate
    across cases even when `output_dir` changes case to case. A missing file
    is simply treated as "no prior cases recorded yet", not an error.

    Pass `callback_handler` (see Strands' Agent callback_handler parameter) to
    stream tool-call events live, e.g. for a UI activity log.
    """
    case = ClaimCase(documents_paths=documents_paths, output_dir=output_dir, history_file=history_file)
    orchestrator = build_orchestrator(case, callback_handler=callback_handler)
    result = orchestrator(TASK_PROMPT)
    return ClaimCaseResult(case=case, summary_text=str(result))
