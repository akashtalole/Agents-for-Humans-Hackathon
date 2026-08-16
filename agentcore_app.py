"""Entrypoint for deploying BidWright's orchestrator to Amazon Bedrock AgentCore Runtime.

This wraps the same `run_bid_job` pipeline used by the CLI and Streamlit demo —
no logic is duplicated for deployment. See deploy/README.md for how to build
and launch this with the AgentCore CLI.

Local test:
    python agentcore_app.py
    # then POST {"rfp_path": "examples/sample_rfp.md",
    #            "profile_path": "examples/company_profile.json"} to the local endpoint

Note: this file requires the optional `bedrock-agentcore` package
(`pip install .[agentcore]`) and AWS credentials with Bedrock access, neither
of which is available in every environment. It is not required to run
BidWright locally or in the Streamlit demo — see cli.py / app_streamlit.py.
"""
from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from bidwright.pipeline import run_bid_job

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    rfp_path = payload["rfp_path"]
    profile_path = payload["profile_path"]
    output_dir = payload.get("output_dir", "/tmp/bidwright_output")

    result = run_bid_job(rfp_path=rfp_path, profile_path=profile_path, output_dir=output_dir)

    blocking_gaps = []
    if result.job.compliance is not None:
        blocking_gaps = [
            {"requirement": g.requirement, "detail": g.detail, "recommendation": g.recommendation}
            for g in result.job.compliance.gaps
            if g.severity.value == "blocking"
        ]

    return {
        "summary": result.summary_text,
        "overall_status": result.job.compliance.overall_status if result.job.compliance else "unknown",
        "blocking_gaps": blocking_gaps,
        "output_dir": output_dir,
    }


if __name__ == "__main__":
    app.run()
