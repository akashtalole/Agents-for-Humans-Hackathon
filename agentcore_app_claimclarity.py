"""Entrypoint for deploying ClaimClarity's orchestrator to Amazon Bedrock AgentCore Runtime.

Wraps the same `run_claim_case` pipeline used by the CLI and Streamlit demo.
See deploy/README.md for build/launch steps and the same caveats noted there
for bidwright's AgentCore wrapper - this file requires the optional
`bedrock-agentcore` package and AWS Bedrock access, and is not exercised by
this repo's automated tests.

Local test:
    python agentcore_app_claimclarity.py
    # then POST {"document_paths": ["examples/claimclarity/denial_notice.md", ...]}
    # to the local endpoint
    # - or, the shape a real remote caller (with no filesystem access to this
    # container) would actually use -
    #            {"document_texts": ["<denial notice text>", "<plan SOB text>", ...]}
"""
from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from claimclarity.payload import resolve_document_paths
from claimclarity.pipeline import run_claim_case

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    output_dir = payload.get("output_dir", "/tmp/claimclarity_output")
    document_paths = resolve_document_paths(payload, "/tmp/claimclarity_input")

    result = run_claim_case(documents_paths=document_paths, output_dir=output_dir)

    findings = []
    if result.case.findings is not None:
        findings = [
            {
                "procedure_code": f.procedure_code,
                "classification": f.classification.value,
                "worth_appealing": f.worth_appealing,
                "recommendation": f.recommendation,
            }
            for f in result.case.findings.findings
        ]

    return {
        "summary": result.summary_text,
        "findings": findings,
        "output_dir": output_dir,
    }


if __name__ == "__main__":
    app.run()
