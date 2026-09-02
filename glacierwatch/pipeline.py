"""Top-level convenience wrapper used by both the CLI and the Streamlit demo."""
from __future__ import annotations

from dataclasses import dataclass

from glacierwatch.orchestrator import WatchRun, build_orchestrator

TASK_PROMPT = (
    "Run this week's watchlist end to end: load the reference sites, fetch live "
    "conditions for every active_watch site, assess every site's priority level, "
    "and draft the final report. Then give me the summary."
)


@dataclass
class WatchRunResult:
    run: WatchRun
    summary_text: str


def run_watchlist(output_dir: str, callback_handler=None) -> WatchRunResult:
    """Run the full GlacierWatch pipeline for the bundled reference watchlist
    and return the result.

    Pass `callback_handler` (see Strands' Agent callback_handler parameter) to
    stream tool-call events live, e.g. for a UI activity log.
    """
    run = WatchRun(output_dir=output_dir)
    orchestrator = build_orchestrator(run, callback_handler=callback_handler)
    result = orchestrator(TASK_PROMPT)
    return WatchRunResult(run=run, summary_text=str(result))
