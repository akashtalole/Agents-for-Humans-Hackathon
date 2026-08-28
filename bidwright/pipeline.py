"""Top-level convenience wrapper used by both the CLI and the Streamlit demo."""
from __future__ import annotations

from dataclasses import dataclass

from bidwright.orchestrator import BidJob, build_orchestrator

TASK_PROMPT = (
    "Process this RFP end to end: load it and the company profile, extract "
    "requirements, check compliance, create a deadline reminder, and draft the "
    "proposal. Then give me the final summary."
)


@dataclass
class BidJobResult:
    job: BidJob
    summary_text: str


def run_bid_job(
    rfp_path: str,
    profile_path: str,
    output_dir: str,
    callback_handler=None,
) -> BidJobResult:
    """Run the full BidWright pipeline for one RFP and return the result.

    Pass `callback_handler` (see Strands' Agent callback_handler parameter) to
    stream tool-call/thinking events live, e.g. for a UI activity log.
    """
    job = BidJob(rfp_path=rfp_path, profile_path=profile_path, output_dir=output_dir)
    orchestrator = build_orchestrator(job, callback_handler=callback_handler)
    result = orchestrator(TASK_PROMPT)
    return BidJobResult(job=job, summary_text=str(result))
