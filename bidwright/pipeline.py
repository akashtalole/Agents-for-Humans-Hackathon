"""Top-level convenience wrapper used by both the CLI and the Streamlit demo."""
from __future__ import annotations

from dataclasses import dataclass

from bidwright.orchestrator import BidJob, build_orchestrator

TASK_PROMPT = (
    "Process this RFP end to end: load it and the company profile, extract "
    "requirements, check compliance, draft a teaming plan for any gaps that "
    "could be closed by partnering with a subcontractor, create a deadline "
    "reminder, and draft the proposal. Then give me the final summary."
)


@dataclass
class BidJobResult:
    job: BidJob
    summary_text: str


def run_bid_job(
    rfp_path: str,
    profile_path: str,
    output_dir: str,
    amendment_path: str | None = None,
    history_file: str = "bidwright_history.json",
    callback_handler=None,
) -> BidJobResult:
    """Run the full BidWright pipeline for one RFP and return the result.

    Pass `amendment_path` if an amendment/addendum document has been issued
    for this RFP - the orchestrator will diff it against the extracted
    requirements and flag anything that needs a decision. Omit it (the
    default) for the common case where no amendment exists yet.

    Pass `history_file` to point at this company's persistent cross-bid
    history file (default: `bidwright_history.json` in the current working
    directory) - every run appends its compliance outcome there and checks
    it for compliance gaps that keep recurring across bids. Point every run
    for the same company at the same file so recurrence can actually be
    detected across runs.

    Pass `callback_handler` (see Strands' Agent callback_handler parameter) to
    stream tool-call/thinking events live, e.g. for a UI activity log.
    """
    job = BidJob(
        rfp_path=rfp_path,
        profile_path=profile_path,
        output_dir=output_dir,
        amendment_path=amendment_path,
        history_file=history_file,
    )
    orchestrator = build_orchestrator(job, callback_handler=callback_handler)
    result = orchestrator(TASK_PROMPT)
    return BidJobResult(job=job, summary_text=str(result))
