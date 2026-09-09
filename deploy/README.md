# Deploying to Amazon Bedrock AgentCore Runtime

> **Deploying from AWS CloudShell?** Start with
> **[CLOUDSHELL.md](CLOUDSHELL.md)** — it covers every path that works
> there end to end, and names the three that need local Docker instead.

This is optional for both projects in this repo. Each runs entirely locally
via its CLI or Streamlit demo with no AWS dependency beyond model access.
Deploying to AgentCore Runtime turns the same orchestrator into a managed,
autoscaled HTTPS endpoint.

> These steps were written against the AgentCore CLI (`bedrock-agentcore-starter-toolkit`)
> and are **not exercised by automated tests in this repo** — this sandbox
> has no AWS Bedrock access to verify a live deployment. Treat this as a
> documented, best-effort path rather than a guarantee; consult the current
> [AgentCore Runtime IAM permissions guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
> and [AgentCore CLI reference](https://github.com/aws/bedrock-agentcore-starter-toolkit/blob/main/documentation/docs/api-reference/cli.md)
> for anything that's drifted — this is a fast-moving, recently launched AWS
> service.

## The fast path: automated CloudShell scripts

**[`deploy/cloudshell/`](cloudshell/README.md)** has `setup.sh` / `invoke_samples.sh` /
`teardown.sh` that do everything below for both projects at once, meant to
run straight from [AWS CloudShell](https://aws.amazon.com/cloudshell/) with
no local install. Start there — see [`deploy/cloudshell/README.md`](cloudshell/README.md)
for the cost warning, prerequisites, and usage. What follows here is the
manual, step-by-step version of the same thing, useful if you want to
understand or customize what the scripts do.

## Prerequisites

- An AWS account with Bedrock model access enabled (Anthropic Claude models,
  in your target region) and permissions to create AgentCore Runtime
  resources — see the IAM permissions guide linked above.
- AWS credentials configured locally (`aws configure` or environment
  variables).
- `pip install ".[agentcore]"` for the runtime SDK, plus
  `pip install bedrock-agentcore-starter-toolkit` for the `agentcore` CLI
  itself (a separate package from the runtime SDK).

## BidWright

- `agentcore_app.py` (repo root) — wraps `bidwright.pipeline.run_bid_job` with
  a `BedrockAgentCoreApp` entrypoint. Payload accepts either
  `{"rfp_path": ..., "profile_path": ...}` (files already present in the
  deployment, e.g. the bundled examples) or `{"rfp_text": ..., "profile_text": ...}`
  (inline content — the shape a real remote caller has to use, since they
  have no filesystem access to the deployed container). Returns the
  compliance status, blocking gaps, and where the generated documents were
  written. See `bidwright/payload.py` for the exact resolution logic.
- `deploy/Dockerfile.bidwright` — container image, if you want to build one
  manually instead of letting the CLI's CodeBuild path do it.

```bash
pip install ".[agentcore]" bedrock-agentcore-starter-toolkit
python agentcore_app.py   # local smoke test (needs a payload posted to it)

agentcore configure --entrypoint agentcore_app.py --name bidwright --non-interactive
agentcore deploy --agent bidwright
agentcore invoke '{"rfp_text": "...", "profile_text": "..."}' --agent bidwright
```

## ClaimClarity

- `agentcore_app_claimclarity.py` (repo root) — wraps
  `claimclarity.pipeline.run_claim_case`. Payload accepts
  `{"document_paths": [...]}` and/or `{"document_texts": [...]}` (a list of
  inline document text — again, the shape a real remote caller needs).
  Returns the findings and where the generated documents were written. See
  `claimclarity/payload.py` for the exact resolution logic.
- `deploy/Dockerfile.claimclarity` — container image, for a manual build.

```bash
pip install ".[agentcore]" bedrock-agentcore-starter-toolkit
python agentcore_app_claimclarity.py   # local smoke test

agentcore configure --entrypoint agentcore_app_claimclarity.py --name claimclarity --non-interactive
agentcore deploy --agent claimclarity
agentcore invoke '{"document_texts": ["...", "...", "..."]}' --agent claimclarity
```

## Notes for either project

`agentcore deploy` builds an ARM64 container image via AWS CodeBuild (no
local Docker needed) and provisions the Runtime endpoint, auto-creating an
IAM execution role, an ECR repository, and the CodeBuild project/role if you
don't specify existing ones. `agentcore destroy --agent NAME --delete-ecr-repo`
tears the agent and its ECR repo back down — see `deploy/cloudshell/teardown.sh`
for what that command does and does not clean up automatically (IAM roles,
the CodeBuild project, and the S3 build-artifact bucket are not, as of this
writing).

For ClaimClarity specifically, also consider swapping
`claimclarity/tools/icd10.py` for a live ICD-10 API/MCP-backed lookup instead
of the bundled demo reference set if you go beyond the example scenario —
see that file's docstring.

## `ecs-express/trinetra-a2a/` — Trinetra as an A2A agent

Publishes Trinetra over the [Agent2Agent](https://a2a-protocol.org/) protocol on
Amazon ECS Express Mode, so agents operated by other organisations (railway,
hospital, irrigation) can discover and call it at a managed HTTPS URL.

Unlike the dashboard deployment beside it, this is a **machine-facing** surface
and deploys in two phases: create the service, read the real public endpoint out
of the service's `ingressPaths[]`, then update it so the published agent card
advertises an address peers can actually reach. It ships with **no
authentication** — see that directory's README before exposing it.
