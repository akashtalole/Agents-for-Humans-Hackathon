"""Command-line entry point: `bidwright run --rfp ... --profile ... --out ...`"""
from __future__ import annotations

import argparse
import sys

from bidwright.config import model_status
from bidwright.pipeline import run_bid_job
from bidwright.rendering import render_decision_summary_md


def _print_stream_event(**kwargs) -> None:
    if "current_tool_use" in kwargs and kwargs["current_tool_use"].get("name"):
        print(f"  -> {kwargs['current_tool_use']['name']}", file=sys.stderr)
    if "data" in kwargs:
        print(kwargs["data"], end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bidwright", description="BidWright RFP compliance & proposal agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Process one RFP end to end")
    run_parser.add_argument("--rfp", required=True, help="Path to the RFP document (.txt/.md/.pdf/.docx)")
    run_parser.add_argument("--profile", required=True, help="Path to the company profile (.txt/.md/.json)")
    run_parser.add_argument(
        "--amendment",
        default=None,
        help="Path to an RFP amendment/addendum document, if one was issued (.txt/.md/.pdf/.docx)",
    )
    run_parser.add_argument(
        "--history-file",
        default="bidwright_history.json",
        help="Path to this company's persistent cross-bid history file, used to detect compliance "
        "gaps that recur across bids (default: ./bidwright_history.json). Point every run for the "
        "same company at the same file.",
    )
    run_parser.add_argument("--out", default="output", help="Output directory (default: ./output)")
    run_parser.add_argument("--quiet", action="store_true", help="Suppress the live activity stream")

    subparsers.add_parser("status", help="Show which model provider BidWright will use")

    args = parser.parse_args(argv)

    if args.command == "status":
        print(model_status())
        return 0

    print(f"Model provider: {model_status()}", file=sys.stderr)
    callback_handler = None if args.quiet else _print_stream_event

    result = run_bid_job(
        rfp_path=args.rfp,
        profile_path=args.profile,
        output_dir=args.out,
        amendment_path=args.amendment,
        history_file=args.history_file,
        callback_handler=callback_handler,
    )

    # The orchestrator's own free-text reply is convenient but is still an LLM
    # talking - it can occasionally misstate specifics even when every generated
    # file is correct (structured data flows through validated Pydantic models,
    # not the model's retelling of its own work). So the trusted headline here
    # is rendered straight from that structured data, the same way
    # decisions_needed.md is - the orchestrator's reply is shown after it,
    # clearly labeled, for transparency rather than as the thing to rely on.
    print("\n\n=== Decisions needed ===\n")
    print(
        render_decision_summary_md(
            result.job.requirements, result.job.compliance, result.job.amendment_impact
        )
    )
    print("=== Orchestrator's own summary (informational; see above for the verified version) ===\n")
    print(result.summary_text)
    print(f"\nFiles written to: {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
