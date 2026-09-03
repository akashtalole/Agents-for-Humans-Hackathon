"""Command-line entry point: `claimclarity run --document ... [--document ...] --out ...`"""
from __future__ import annotations

import argparse
import sys

from claimclarity.config import model_status
from claimclarity.pipeline import run_claim_case
from claimclarity.rendering import render_decision_summary_md


def _print_stream_event(**kwargs) -> None:
    if "current_tool_use" in kwargs and kwargs["current_tool_use"].get("name"):
        print(f"  -> {kwargs['current_tool_use']['name']}", file=sys.stderr)
    if "data" in kwargs:
        print(kwargs["data"], end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claimclarity", description="ClaimClarity insurance denial & appeal agent"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Process one claim denial end to end")
    run_parser.add_argument(
        "--document",
        dest="documents",
        action="append",
        required=True,
        help="Path to a source document (.txt/.md/.pdf/.docx): the denial notice/EOB, and "
        "optionally a plan summary of benefits and/or medical record excerpt. Repeat for "
        "multiple files.",
    )
    run_parser.add_argument("--out", default="output", help="Output directory (default: ./output)")
    run_parser.add_argument(
        "--history-file",
        default="claimclarity_history.json",
        help=(
            "Path to the persistent cross-run insurer accountability history JSON file "
            "(default: ./claimclarity_history.json). Kept independent of --out on purpose so history "
            "keeps accumulating across cases even if --out changes case to case; point separate --out "
            "runs at the same --history-file to build up pattern history, or a fresh path to start over. "
            "A missing file just means this is the first case recorded - it is created automatically, not "
            "an error."
        ),
    )
    run_parser.add_argument("--quiet", action="store_true", help="Suppress the live activity stream")

    subparsers.add_parser("status", help="Show which model provider ClaimClarity will use")

    args = parser.parse_args(argv)

    if args.command == "status":
        print(model_status())
        return 0

    print(f"Model provider: {model_status()}", file=sys.stderr)
    callback_handler = None if args.quiet else _print_stream_event

    result = run_claim_case(
        documents_paths=args.documents,
        output_dir=args.out,
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
            result.case.claim,
            result.case.findings,
            result.case.escalation,
            result.case.physician_evidence_request,
        )
    )
    print("=== Orchestrator's own summary (informational; see above for the verified version) ===\n")
    print(result.summary_text)
    print(f"\nFiles written to: {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
