"""Entrypoint for deploying Trinetra to Amazon Bedrock AgentCore Runtime.

Unlike bidwright/claimclarity/glacierwatch (one linear pipeline each),
Trinetra is a multi-service platform, so this entrypoint routes on an
`action` field in the payload to the matching direct-API function in
trinetra/orchestrator.py - the same functions the CLI calls, no logic
duplicated for deployment.

Local test:
    python agentcore_app_trinetra.py
    # then POST one of:
    #   {"action": "ask", "text": "...", "language": "hindi"}
    #   {"action": "sos", "description": "...", "location": "...", "incident_type": "lost_person"}
    #   {"action": "simulate", "name": "...", "total_pilgrims": 500000,
    #    "duration_minutes": 180, "peak_inflow_multiplier": 2.0, "active_ghat_ids": ["ramkund"]}
    #   {"action": "calibrate"}
    # to the local endpoint.

Note: this file requires the optional `bedrock-agentcore` package
(`pip install .[agentcore]`) and AWS credentials with Bedrock access. It is
not required to run Trinetra locally - see cli.py.
"""
from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from trinetra.models import IncidentType, IndianLanguage, SimulationScenario, SOSReport
from trinetra.orchestrator import TrinetraSession, ask_pilgrim, report_sos, run_calibration, run_simulation

app = BedrockAgentCoreApp()

_session = TrinetraSession()


@app.entrypoint
def invoke(payload: dict) -> dict:
    action = payload.get("action", "ask")

    if action == "ask":
        language = IndianLanguage(payload.get("language", "hindi"))
        guidance = ask_pilgrim(_session, payload["text"], language=language)
        return guidance.model_dump(mode="json")

    if action == "sos":
        report = SOSReport(
            incident_type=IncidentType(payload.get("incident_type", "other")),
            reporter_description=payload["description"],
            location=payload["location"],
            involves_children_or_elderly=payload.get("involves_children_or_elderly", False),
        )
        triage = report_sos(_session, report)
        return triage.model_dump(mode="json")

    if action == "simulate":
        scenario = SimulationScenario(
            name=payload.get("name", "Ad-hoc scenario"),
            description=payload.get("description", ""),
            total_pilgrims=payload["total_pilgrims"],
            duration_minutes=payload["duration_minutes"],
            peak_inflow_multiplier=payload.get("peak_inflow_multiplier", 1.0),
            active_ghat_ids=payload["active_ghat_ids"],
        )
        report, advisory = run_simulation(_session, scenario)
        return {"report": report.model_dump(mode="json"), "advisory": advisory.model_dump(mode="json")}

    if action == "calibrate":
        results = run_calibration(_session)
        return {"results": [r.model_dump(mode="json") for r in results]}

    return {"error": f"Unknown action '{action}'. Expected one of: ask, sos, simulate, calibrate."}


if __name__ == "__main__":
    app.run()
