# Deploying to Amazon Bedrock AgentCore Runtime

This is optional for both projects in this repo. Each runs entirely locally
via its CLI or Streamlit demo with no AWS dependency beyond model access.
Deploying to AgentCore Runtime turns the same orchestrator into a managed,
autoscaled HTTPS endpoint.

> These steps were written against the AgentCore CLI and toolkit and are
> **not exercised by automated tests in this repo** — this sandbox has no AWS
> Bedrock access to verify a live deployment. Treat this as a documented,
> best-effort path rather than a guarantee; consult the current
> [Strands Agents Bedrock AgentCore deployment guide](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python/)
> for anything that's drifted.

## Prerequisites

- An AWS account with Bedrock model access enabled and permissions to create
  AgentCore Runtime resources.
- AWS credentials configured locally (`aws configure` or environment
  variables).
- `pip install ".[agentcore]"` to pull in the `bedrock-agentcore` package.

## BidWright

- `agentcore_app.py` (repo root) — wraps `bidwright.pipeline.run_bid_job` with
  a `BedrockAgentCoreApp` entrypoint. Takes
  `{"rfp_path": ..., "profile_path": ...}` and returns the compliance status,
  blocking gaps, and where the generated documents were written.
- `deploy/Dockerfile.bidwright` — container image for the runtime.

```bash
pip install ".[agentcore]"
python agentcore_app.py   # local smoke test

agentcore configure --entrypoint agentcore_app.py
agentcore launch
```

Example invocation payload:

```json
{
  "rfp_path": "examples/sample_rfp.md",
  "profile_path": "examples/company_profile.json"
}
```

## ClaimClarity

- `agentcore_app_claimclarity.py` (repo root) — wraps
  `claimclarity.pipeline.run_claim_case`. Takes
  `{"document_paths": [...]}` (denial notice/EOB, and optionally a plan
  summary of benefits and/or medical record excerpt) and returns the findings
  and where the generated documents were written.
- `deploy/Dockerfile.claimclarity` — container image for the runtime.

```bash
pip install ".[agentcore]"
python agentcore_app_claimclarity.py   # local smoke test

agentcore configure --entrypoint agentcore_app_claimclarity.py
agentcore launch
```

Example invocation payload:

```json
{
  "document_paths": [
    "examples/claimclarity/denial_notice.md",
    "examples/claimclarity/plan_summary_of_benefits.md",
    "examples/claimclarity/medical_record_excerpt.md"
  ]
}
```

## Notes for either project

`agentcore launch` builds the container from the matching `deploy/Dockerfile.*`
(or an auto-generated one, depending on CLI version), pushes it, and
provisions the Runtime endpoint. For a real deployment, input documents would
come from S3 or an inline payload rather than local paths — swap
`read_document` in `bidwright/tools/documents.py` /
`claimclarity/tools/documents.py` for an S3-aware version if you go this
route. For ClaimClarity specifically, also swap `claimclarity/tools/icd10.py`
for a live ICD-10 API/MCP-backed lookup instead of the bundled demo reference
set — see that file's docstring.
