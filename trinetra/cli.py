"""Command-line entry point for Trinetra.

Subcommands map directly to the three pillars:
  trinetra ask "..."               Yatri Netra - ask the pilgrim assistant
  trinetra sos "..." --location X  Kumbh Rakshak - report a safety incident
  trinetra simulate --scenario ... Bhavishya Netra - run a crowd simulation
  trinetra calibrate               Bhavishya Netra - validate against real incidents
  trinetra status                  Show which model provider will be used
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trinetra.config import model_status
from trinetra.models import IncidentType, IndianLanguage, SimulationScenario
from trinetra.orchestrator import TrinetraSession, ask_pilgrim, report_sos, run_calibration, run_simulation
from trinetra.models import SOSReport
from trinetra.rendering import (
    render_calibration_md,
    render_pilgrim_guidance_md,
    render_safety_triage_md,
    render_simulation_report_md,
)


def _write(out_dir: str, filename: str, content: str) -> Path:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / filename
    file_path.write_text(content)
    return file_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trinetra", description="Trinetra - Nashik-Trimbakeshwar Kumbh Mela 2027 agent platform")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Ask Yatri Sahayak a pilgrim question")
    ask_parser.add_argument("question", help="The pilgrim's question")
    ask_parser.add_argument("--language", default="hindi", choices=[l.value for l in IndianLanguage])
    ask_parser.add_argument("--out", default="output")

    sos_parser = subparsers.add_parser("sos", help="Report an incident to Kumbh Rakshak")
    sos_parser.add_argument("description", help="Description of what's happening")
    sos_parser.add_argument("--location", required=True)
    sos_parser.add_argument("--incident-type", default="other", choices=[t.value for t in IncidentType])
    sos_parser.add_argument("--involves-children-or-elderly", action="store_true")
    sos_parser.add_argument("--out", default="output")

    sim_parser = subparsers.add_parser("simulate", help="Run a Bhavishya Netra crowd simulation")
    sim_parser.add_argument("--name", default="Custom scenario")
    sim_parser.add_argument("--description", default="")
    sim_parser.add_argument("--pilgrims", type=int, default=500000)
    sim_parser.add_argument("--duration", type=int, default=180, help="Minutes")
    sim_parser.add_argument("--peak-multiplier", type=float, default=2.0)
    sim_parser.add_argument("--ghats", nargs="+", default=["ramkund", "kushavarta"])
    sim_parser.add_argument("--out", default="output")

    calibrate_parser = subparsers.add_parser("calibrate", help="Validate the simulator against real historical Kumbh incidents")
    calibrate_parser.add_argument("--out", default="output")

    subparsers.add_parser("status", help="Show which model provider Trinetra will use")

    args = parser.parse_args(argv)

    if args.command == "status":
        print(model_status())
        return 0

    session = TrinetraSession()

    if args.command == "ask":
        guidance = ask_pilgrim(session, args.question, language=IndianLanguage(args.language))
        md = render_pilgrim_guidance_md(guidance)
        print(md)
        _write(args.out, "pilgrim_guidance.md", md)
        return 0

    if args.command == "sos":
        report = SOSReport(
            incident_type=IncidentType(args.incident_type),
            reporter_description=args.description,
            location=args.location,
            involves_children_or_elderly=args.involves_children_or_elderly,
        )
        triage = report_sos(session, report)
        md = render_safety_triage_md(triage)
        print(md)
        _write(args.out, "safety_triage.md", md)
        return 0

    if args.command == "simulate":
        scenario = SimulationScenario(
            name=args.name, description=args.description or args.name,
            total_pilgrims=args.pilgrims, duration_minutes=args.duration,
            peak_inflow_multiplier=args.peak_multiplier, active_ghat_ids=args.ghats,
        )
        report, advisory = run_simulation(session, scenario)
        md = render_simulation_report_md(report, advisory)
        print(md)
        _write(args.out, "simulation_report.md", md)
        return 0

    if args.command == "calibrate":
        results = run_calibration(session)
        md = render_calibration_md(results)
        print(md)
        _write(args.out, "calibration_report.md", md)
        return 0 if all(r.correctly_flagged for r in results) else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
