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
from datetime import datetime
from pathlib import Path

from trinetra.config import model_status
from trinetra.models import (
    CrowdSignal,
    IncidentType,
    IndianLanguage,
    MobilityProfile,
    SimulationScenario,
)
from trinetra.agents.scenario_director import decide_scenario
from trinetra.orchestrator import (
    command_incident,
    TrinetraSession,
    ask_pilgrim,
    assess_flood_risk,
    monitor_live,
    report_sos,
    run_calibration,
    run_simulation,
    triage_rumor,
)
from trinetra.models import RumorReport, SOSReport
from trinetra.rendering import (
    render_incident_command_md,
    render_peer_consultation_md,
    render_calibration_md,
    render_compound_risk_md,
    render_monitoring_brief_md,
    render_pilgrim_guidance_md,
    render_rumor_assessment_md,
    render_safety_triage_md,
    render_seeding_run_summary_md,
    render_simulation_report_md,
)
from trinetra.tools.thingsboard_seed import run_seeding_cycle


def _parse_occupancy(pairs: list[str]) -> dict[str, int] | None:
    """Parse GHAT_ID=COUNT arguments. Returns None (after printing why) on bad
    input, so callers can exit 2 rather than guessing at a number."""
    occupancy: dict[str, int] = {}
    for pair in pairs:
        if "=" not in pair:
            print(f"--occupancy entries must look like GHAT_ID=COUNT, got '{pair}'", file=sys.stderr)
            return None
        ghat_id, _, count = pair.partition("=")
        try:
            occupancy[ghat_id] = int(count)
        except ValueError:
            print(f"'{count}' is not a valid occupancy count for '{ghat_id}'", file=sys.stderr)
            return None
    return occupancy


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

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Kshetra Netra: live-monitor one ghat (live ThingsBoard telemetry + a lookahead simulation). "
        "Requires ANTHROPIC_API_KEY/Bedrock creds (it is a tool-calling agent, unlike calibrate) and, for a "
        "live signal rather than an honest 'unavailable', THINGSBOARD_USERNAME/PASSWORD or THINGSBOARD_API_KEY.",
    )
    monitor_parser.add_argument("--ghat", required=True, help="Ghat id, e.g. ramkund")
    monitor_parser.add_argument("--question", default=None, help="Optional free-text focus for the agent")
    monitor_parser.add_argument("--out", default="output")

    seed_parser = subparsers.add_parser(
        "seed-thingsboard",
        help="Anukaran Netra: push reproducible, documented synthetic telemetry onto KumbhDigiTwin's real "
        "ThingsBoard ghat entities (all 7, not just the ones Trinetra's own sites.json knows about). Requires "
        "ANTHROPIC_API_KEY/Bedrock creds AND THINGSBOARD_USERNAME/PASSWORD or THINGSBOARD_API_KEY - this is the "
        "one Trinetra command that writes to an external system rather than only reading or computing.",
    )
    seed_parser.add_argument("--request", required=True, help='Free-text scenario, e.g. "buildup to an Amrit Snan peak"')
    seed_parser.add_argument("--tick-minutes", type=int, default=5, help="Simulated minutes between pushed points")
    seed_parser.add_argument("--out", default="output")

    flood_parser = subparsers.add_parser(
        "flood-risk",
        help="Assess a Gangapur Dam release against current ghat occupancy (can each ghat be cleared in time?)",
    )
    flood_parser.add_argument("--discharge", type=int, required=True, help="Gangapur Dam discharge in cusecs")
    flood_parser.add_argument(
        "--occupancy",
        nargs="+",
        required=True,
        metavar="GHAT_ID=COUNT",
        help="Current occupancy per ghat, e.g. ramkund=8000 panchavati_godavari=5000",
    )
    flood_parser.add_argument(
        "--elderly-share",
        type=float,
        default=0.4,
        help="Share of the crowd that is elderly/mobility-limited (default 0.4 - Kumbh crowds skew elderly)",
    )
    flood_parser.add_argument("--no-rainfall", action="store_true", help="Skip the live Open-Meteo rainfall lookup")
    flood_parser.add_argument("--out", default="output")

    rumor_parser = subparsers.add_parser(
        "rumor", help="Assess a rumor spreading in the crowd and draft a guardrail-checked counter-message"
    )
    rumor_parser.add_argument("text", help="What is being said in the crowd")
    rumor_parser.add_argument("--location", required=True)
    rumor_parser.add_argument("--spreading-fast", action="store_true")
    rumor_parser.add_argument("--reported-by", default="field staff")
    rumor_parser.add_argument("--out", default="output")

    cmd_parser = subparsers.add_parser(
        "command",
        help="Sankat Nirnay: reconcile every live hazard against the finite responder pool",
    )
    cmd_parser.add_argument("--discharge", type=int, help="Gangapur Dam discharge in cusecs, if the river is a factor")
    cmd_parser.add_argument(
        "--occupancy", nargs="+", default=[], metavar="GHAT_ID=COUNT",
        help="Current occupancy per ghat, e.g. ramkund=8000 panchavati_godavari=4800",
    )
    cmd_parser.add_argument("--elderly-share", type=float, default=0.4)
    cmd_parser.add_argument("--sos", nargs="*", default=[], metavar="LOCATION::DESCRIPTION",
                            help="Open SOS incidents, e.g. 'Ramkund::elderly man collapsed'")
    cmd_parser.add_argument("--rumor", help="A rumour currently circulating, if any")
    cmd_parser.add_argument("--rumor-location", default="")
    cmd_parser.add_argument("--no-rainfall", action="store_true")
    cmd_parser.add_argument("--no-red-team", action="store_true", help="Skip the adversarial plan review")
    cmd_parser.add_argument("--out", default="output")

    subparsers.add_parser("a2a-peers", help="List the registered A2A peer agents (the allowlist)")

    consult_parser = subparsers.add_parser(
        "a2a-ask", help="Ask registered third-party A2A agents a question"
    )
    consult_parser.add_argument("question")
    consult_parser.add_argument("--peer", action="append", default=None, dest="peers",
                                help="Restrict to these peer ids (repeatable)")
    consult_parser.add_argument("--capability", help="Route to peers declaring this capability")
    consult_parser.add_argument("--timeout", type=float, default=20.0)
    consult_parser.add_argument("--out", default="output")

    serve_parser = subparsers.add_parser(
        "a2a-serve", help="Expose Trinetra to third-party agents over the A2A protocol"
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=9100)
    serve_parser.add_argument("--http-url", default=None,
                              help="Public URL to advertise in the agent card, if behind a proxy")

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

    if args.command == "monitor":
        brief = monitor_live(session, args.ghat, question=args.question)
        md = render_monitoring_brief_md(brief)
        print(md)
        _write(args.out, "monitoring_brief.md", md)
        return 0

    if args.command == "seed-thingsboard":
        directive = decide_scenario(args.request)
        summary = run_seeding_cycle(directive, tick_minutes=args.tick_minutes)
        md = render_seeding_run_summary_md(summary)
        print(md)
        _write(args.out, "seeding_run.md", md)
        return 0 if not summary.errors else 1

    if args.command == "flood-risk":
        occupancy = _parse_occupancy(args.occupancy)
        if occupancy is None:
            return 2

        elderly = max(0.0, min(1.0, args.elderly_share))
        mobility_mix = {
            MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: elderly,
            MobilityProfile.STANDARD: 1.0 - elderly,
        }
        assessment, advisory = assess_flood_risk(
            session,
            discharge_cusecs=args.discharge,
            occupancy_by_ghat=occupancy,
            mobility_mix=mobility_mix,
            fetch_rainfall=not args.no_rainfall,
        )
        md = render_compound_risk_md(assessment, advisory)
        print(md)
        _write(args.out, "compound_flood_risk.md", md)
        # Non-zero exit when a ghat genuinely cannot be cleared in time, so
        # this is usable as a check in an operational script, not just a
        # report to read.
        return 0 if assessment.overall_risk.value != "critical" else 1

    if args.command == "rumor":
        report = RumorReport(
            text=args.text,
            location=args.location,
            reported_by=args.reported_by,
            spreading_fast=args.spreading_fast,
        )
        assessment, guardrail = triage_rumor(session, report)
        md = render_rumor_assessment_md(assessment, guardrail)
        print(md)
        _write(args.out, "rumor_assessment.md", md)
        return 0 if guardrail.passed else 1

    if args.command == "command":
        occupancy = _parse_occupancy(args.occupancy)
        if occupancy is None:
            return 2

        signals = [
            CrowdSignal(
                ghat_id=ghat_id,
                timestamp=datetime.utcnow(),
                estimated_occupancy=count,
                # Without a live feed we cannot know the flow rates, so this
                # models a steady-state crowd rather than inventing a surge.
                inflow_rate_per_min=0,
                outflow_rate_per_min=0,
            )
            for ghat_id, count in occupancy.items()
            if ghat_id in session.ghats
        ]

        sos_reports = []
        for entry in args.sos:
            location, _, description = entry.partition("::")
            if not description:
                print(f"--sos entries must look like LOCATION::DESCRIPTION, got '{entry}'", file=sys.stderr)
                return 2
            sos_reports.append(SOSReport(incident_type=IncidentType.OTHER,
                                         reporter_description=description, location=location))

        rumor = (
            RumorReport(text=args.rumor, location=args.rumor_location or "unspecified")
            if args.rumor
            else None
        )

        elderly = max(0.0, min(1.0, args.elderly_share))
        plan, allocation, conflicts, critique = command_incident(
            session,
            signals=signals or None,
            flood_discharge_cusecs=args.discharge,
            flood_occupancy=occupancy or None,
            sos_reports=sos_reports or None,
            rumor=rumor,
            mobility_mix={
                MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: elderly,
                MobilityProfile.STANDARD: 1.0 - elderly,
            },
            fetch_rainfall=not args.no_rainfall,
            run_red_team=not args.no_red_team,
        )
        md = render_incident_command_md(plan, allocation, conflicts, critique)
        print(md)
        _write(args.out, "incident_command.md", md)
        # Non-zero when the plan carries a call a human must make - an
        # unresolved critical conflict or an unfillable critical demand.
        return 1 if (conflicts.has_critical or allocation.unmet_critical) else 0

    if args.command == "a2a-peers":
        from trinetra.a2a.registry import load_peers

        peers = load_peers()
        print(f"{len(peers)} registered A2A peer(s). Trinetra will not call a URL that is not listed here.\n")
        for peer in peers.values():
            print(f"  {peer.peer_id}  [{peer.trust.value}]")
            print(f"    {peer.name} — {peer.operator}")
            print(f"    {peer.base_url}")
            print(f"    capabilities: {', '.join(peer.capabilities) or '(none declared)'}")
            if peer.note:
                print(f"    note: {peer.note}")
            print()
        return 0

    if args.command == "a2a-ask":
        from trinetra.a2a.client import consult_peers
        from trinetra.a2a.registry import peers_for_capability

        peer_ids = args.peers
        if args.capability:
            matched = [p.peer_id for p in peers_for_capability(args.capability)]
            if not matched:
                print(f"No registered peer declares a capability matching '{args.capability}'.",
                      file=sys.stderr)
                return 2
            peer_ids = matched

        consultation = consult_peers(args.question, peer_ids=peer_ids, timeout=args.timeout)
        md = render_peer_consultation_md(consultation)
        print(md)
        _write(args.out, "peer_consultation.md", md)
        # Non-zero when nothing usable came back, so this is scriptable as a
        # check rather than only a report to read.
        return 0 if any(r.usable for r in consultation.responses) else 1

    if args.command == "a2a-serve":
        from trinetra.a2a.server import build_a2a_server

        server = build_a2a_server(host=args.host, port=args.port, http_url=args.http_url)
        print(f"Trinetra A2A agent card: {server.agent_card_url}")
        print("Serving. Third-party agents can now discover and call Trinetra. Ctrl-C to stop.")
        server.serve()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
