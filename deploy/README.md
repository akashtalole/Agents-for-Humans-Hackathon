# Deploying BidWright to Amazon Bedrock AgentCore Runtime

This is optional. BidWright runs entirely locally via the CLI (`bidwright run`)
or the Streamlit demo (`streamlit run app_streamlit.py`) with no AWS
dependency beyond model access. Deploying to AgentCore Runtime turns the same
orchestrator into a managed, autoscaled HTTPS endpoint.

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

## What's here

- `agentcore_app.py` (repo root) — wraps `bidwright.pipeline.run_bid_job` with
  a `BedrockAgentCoreApp` entrypoint. It takes `{"rfp_path": ..., "profile_path": ...}`
  and returns the compliance status, blocking gaps, and where the generated
  documents were written.
- `deploy/Dockerfile` — container image for the runtime.

## Steps

```bash
# from the repo root
pip install ".[agentcore]"

# local smoke test of the AgentCore wrapper
python agentcore_app.py

# using the AgentCore CLI (see the official docs linked above for the
# current install method and command names, which have changed across
# preview releases)
agentcore configure --entrypoint agentcore_app.py
agentcore launch
```

`agentcore launch` builds the container from `deploy/Dockerfile` (or an
auto-generated one, depending on CLI version), pushes it, and provisions the
Runtime endpoint. Once deployed, invoke it with a payload like:

```json
{
  "rfp_path": "examples/sample_rfp.md",
  "profile_path": "examples/company_profile.json"
}
```

For a real deployment, the RFP and profile would come from S3 or an inline
payload rather than local paths — swap `read_document` in
`bidwright/tools/documents.py` for an S3-aware version if you go this route.
