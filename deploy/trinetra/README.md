# Deploying Trinetra from AWS CloudShell

One-shot scripts to spin up (and cleanly tear down) Trinetra on Amazon
Bedrock AgentCore Runtime, run entirely from
[AWS CloudShell](https://aws.amazon.com/cloudshell/) — no local install, no
Docker required. Same pattern as `deploy/cloudshell/` (BidWright +
ClaimClarity), scoped to Trinetra's single multi-action agent.

> **These scripts have not been exercised against a live AWS account.**
> Read a script before running it, and expect to debug the first live run
> against the [current AgentCore CLI docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
> if AWS has changed a flag since this was written.

## Cost warning

Running `setup.sh` creates **real, billable AWS resources**: Bedrock model
invocations (or Anthropic API usage with `--model-provider anthropic`), an
AgentCore Runtime agent, a CodeBuild project and build minutes, an ECR
repository, an S3 bucket, and CloudWatch Log groups. Run `teardown.sh` when
you're done.

## Usage

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon
git checkout claude/trinetra-nashik-kumbh-2027   # or main/whichever branch has this merged

deploy/trinetra/setup.sh
```

By default this deploys via **Amazon Bedrock** (no API key needed). To use
the Anthropic API directly instead:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
deploy/trinetra/setup.sh --model-provider anthropic
```

See `deploy/cloudshell/README.md`'s "Using the Anthropic API instead of
Bedrock" section for the full explanation of how the key gets passed (via
`agentcore deploy --env`, never through CodeBuild) — the same mechanism
applies here.

Then smoke-test it:

```bash
deploy/trinetra/invoke_samples.sh
```

This invokes all four action shapes (`ask`, `sos`, `simulate`, `calibrate`)
against the deployed agent using `agentcore invoke`, sending the payload
shapes documented in `agentcore_app_trinetra.py`'s own module docstring.

When you're done:

```bash
deploy/trinetra/teardown.sh
```

## Files

```
deploy/trinetra/
  common.sh                   Shared bash helpers (copy of deploy/cloudshell/common.sh)
  requirements-agentcore.txt  Runtime deps for agentcore_app_trinetra.py
  setup.sh                    Deploy the agent
  invoke_samples.sh           Smoke-test all four action shapes
  teardown.sh                 Clean everything up
```

## Troubleshooting

See `deploy/cloudshell/README.md`'s Troubleshooting section — the same AWS
CLI/AgentCore CLI issues and fixes apply here.
