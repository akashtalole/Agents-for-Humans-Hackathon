"""Command-line entry point: `glacierwatch run --out ...`"""
from __future__ import annotations

import argparse
import sys

from glacierwatch.config import model_status
from glacierwatch.pipeline import run_watchlist
from glacierwatch.rendering import render_watchlist_report_md


def _print_stream_event(**kwargs) -> None:
    if "current_tool_use" in kwargs and kwargs["current_tool_use"].get("name"):
        print(f"  -> {kwargs['current_tool_use']['name']}", file=sys.stderr)
    if "data" in kwargs:
        print(kwargs["data"], end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="glacierwatch", description="GlacierWatch hazard triage agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run this week's watchlist end to end")
    run_parser.add_argument("--out", default="output", help="Output directory (default: ./output)")
    run_parser.add_argument(
        "--history-file",
        default="glacierwatch_history.json",
        help=(
            "Path to the persistent run-history JSON file used for trend early-warning detection "
            "(default: ./glacierwatch_history.json). Kept independent of --out on purpose so history "
            "keeps accumulating across runs even if --out changes week to week; point separate --out "
            "runs at the same --history-file to build up trend history, or a fresh path to start over. "
            "A missing file just means this is the first run - it is created automatically, not an error."
        ),
    )
    run_parser.add_argument("--quiet", action="store_true", help="Suppress the live activity stream")

    subparsers.add_parser("status", help="Show which model provider GlacierWatch will use")

    args = parser.parse_args(argv)

    if args.command == "status":
        print(model_status())
        return 0

    print(f"Model provider: {model_status()}", file=sys.stderr)
    callback_handler = None if args.quiet else _print_stream_event

    result = run_watchlist(output_dir=args.out, history_file=args.history_file, callback_handler=callback_handler)

    # Same discipline as bidwright/cli.py and claimclarity/cli.py: the
    # deterministic, code-rendered report is the trusted headline. The
    # orchestrator's own reply is shown after it, clearly labeled.
    print("\n\n=== Weekly watchlist report ===\n")
    if result.run.report is not None:
        print(render_watchlist_report_md(result.run.report))
    else:
        print("_Run did not complete - no report was produced._")
    print("=== Orchestrator's own summary (informational; see above for the verified version) ===\n")
    print(result.summary_text)
    print(f"\nFiles written to: {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
