# Deploying from AWS CloudShell

One-shot scripts to spin up (and cleanly tear down) both BidWright and
ClaimClarity on Amazon Bedrock AgentCore Runtime, run entirely from
[AWS CloudShell](https://aws.amazon.com/cloudshell/) — no local install, no
Docker required (the default deployment path builds the ARM64 container
image on AWS CodeBuild, which is exactly what CloudShell needs since it has
no Docker daemon of its own).

> **These scripts have not been exercised against a live AWS account.** This
> project was built in a sandbox with no working Bedrock/AgentCore access, so
> everything here is verified as far as offline testing can reach — bash
> syntax, the prerequisite/region/manifest logic, and the exact payload
> shapes sent to each agent (see `tests/test_bidwright_payload.py` and
> `tests/test_claimclarity_payload.py`) — but not a real `agentcore deploy`
> run. Read a script before running it, and expect to debug the first live
> run against the [current AgentCore CLI docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
> if AWS has changed a flag since this was written.

## Cost warning

Running `setup.sh` creates **real, billable AWS resources**: Bedrock model
invocations, an AgentCore Runtime agent per project, a CodeBuild project and
build minutes, an ECR repository (image storage), an S3 bucket (build
artifacts), and CloudWatch Log groups. None of this is free-tier-guaranteed.
Run `teardown.sh` when you're done — see its `--help` for exactly what it
does and does not remove automatically.

## Prerequisites

- An AWS account with **Bedrock model access enabled for Anthropic Claude
  models** in your target region (Bedrock console → Model access). This is a
  manual, per-account/region step AWS doesn't expose a reliable CLI toggle
  for — `setup.sh` checks and warns if it looks unavailable, but can't
  enable it for you.
- Enough IAM permission to run the AgentCore CLI — attach the
  `BedrockAgentCoreFullAccess` AWS managed policy, or a custom policy scoped
  to what the CLI actually needs (see
  [IAM Permissions for AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html) →
  "Use the AgentCore CLI"). CloudShell's default role usually needs this
  attached explicitly — it's not automatic.
- AgentCore Runtime's regional availability changes over time; `setup.sh`
  checks against a list that's current as of when this was written and warns
  (not blocks) if your region isn't on it.

## Usage

Open [AWS CloudShell](https://console.aws.amazon.com/cloudshell/) in your
target region, then:

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon
git checkout claude/aws-cloudshell-deploy   # or main/whichever branch has this merged

deploy/cloudshell/setup.sh
```

(If you run one of these scripts from inside an already-cloned checkout, it
detects that and uses it in place — no need to `cd` anywhere special first.)

`setup.sh` will:
1. Confirm before doing anything (creating billable resources) — pass
   `--yes` to skip the prompt for unattended runs, or `--dry-run` to see
   exactly what it would do without touching AWS.
2. Set up a Python virtualenv and install the AgentCore starter toolkit.
3. Check your AWS identity, region, and (for the default `--model-provider
   bedrock`) Bedrock reachability.
4. Configure and deploy both `bidwright` and `claimclarity` agents.
5. Write a small manifest (`~/.agentcore-deployment.json`) recording what it
   created, for the other two scripts to read.

## Using the Anthropic API instead of Bedrock

By default both agents are deployed to call Claude **through Amazon
Bedrock** — the deployed container's IAM execution role is what's
authorized to invoke the model, so no API key is needed anywhere. Pass
`--model-provider anthropic` to `setup.sh` instead if you'd rather call the
**Anthropic API directly** (useful if you don't have Bedrock model access
enabled, or specifically want Anthropic-platform billing/usage instead of
Bedrock's):

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # your key, kept only in this shell session
deploy/cloudshell/setup.sh --model-provider anthropic
```

**How the key gets to the deployed agent — and why CodeBuild is not
involved:** `agentcore deploy` accepts a repeatable `--env KEY=VALUE` flag
(the AgentCore CLI's only supported way to pass configuration/secrets into
the deployed runtime — there is no built-in AWS Secrets Manager or SSM
Parameter Store integration for this). `setup.sh` reads `ANTHROPIC_API_KEY`
from your shell environment and passes it straight through as `--env
ANTHROPIC_API_KEY=... --env BIDWRIGHT_MODEL_PROVIDER=anthropic` (and the
`CLAIMCLARITY_MODEL_PROVIDER` equivalent for the second agent) on the
`agentcore deploy` command line. That's a **separate step from the
CodeBuild image build** that happens earlier in the same deploy: CodeBuild
only compiles the ARM64 container image from this repo's entrypoint file
and `requirements-agentcore.txt` — it has no access to your API key and
never runs any code that calls a model. The key only exists as a runtime
environment variable inside the already-built container, set when
`agentcore deploy` launches it, which is what `bidwright/config.py` and
`claimclarity/config.py`'s `get_model()` read (via
`BIDWRIGHT_MODEL_PROVIDER=anthropic` / `CLAIMCLARITY_MODEL_PROVIDER=anthropic`)
to pick the direct Anthropic client over the Bedrock client. So: **no**,
nothing about the Anthropic key is automated through CodeBuild — it's a
plain container-runtime env var set by the `agentcore deploy` CLI call
itself, not something CodeBuild builds, bakes into the image, or ever sees.

The key is never written to disk in this repo and `--dry-run` output
redacts it. It's still visible in your shell history and to anything with
`agentcore deploy`'s process arguments while it runs — treat it like any
other secret passed on a CLI, and rotate it if you ever paste it somewhere
less trusted than your own CloudShell session.

Then smoke-test both agents with the repo's bundled example data:

```bash
deploy/cloudshell/invoke_samples.sh
```

This sends the example RFP/company-profile and denial-notice/plan/medical-record
documents as **inline text** in the invoke payload — the shape a real caller
has to use, since they have no filesystem access to the deployed container
(see `rfp_text`/`profile_text` and `document_texts` in `bidwright/payload.py`
/ `claimclarity/payload.py`).

When you're done:

```bash
deploy/cloudshell/teardown.sh
```

Safe by default — previews what it's about to destroy and asks first. Use
`--yes` for unattended teardown, `--dry-run` to preview only, `--agent NAME`
to tear down just one agent. It prints a manual-cleanup checklist for the
handful of resource kinds `agentcore destroy` doesn't remove on its own
(IAM roles, the CodeBuild project, the S3 build-artifact bucket) — read-only
`aws` commands to find them, nothing auto-deleted there.

## Files

```
deploy/cloudshell/
  common.sh                   Shared bash helpers: logging, confirm prompts,
                              AWS identity/region checks, the deployment
                              manifest read/write functions
  requirements-agentcore.txt  Runtime deps passed to `agentcore configure
                              --requirements-file` (kept in sync with
                              pyproject.toml's [project.dependencies])
  setup.sh                    Spin up both agents
  invoke_samples.sh           Smoke-test both deployed agents
  teardown.sh                 Clean everything up
```

## Troubleshooting

- **"aws sts get-caller-identity failed"**: open a fresh CloudShell tab (its
  credentials occasionally need a refresh), or you're not actually in
  CloudShell / don't have AWS CLI credentials configured.
- **Bedrock access errors on deploy/invoke**: almost always means Anthropic
  model access isn't enabled in that region yet — Bedrock console → Model
  access → enable, then re-run.
- **`agentcore` command not found**: `setup.sh` installs
  `bedrock-agentcore-starter-toolkit` into `.venv` — make sure you've
  `source .venv/bin/activate`d if running commands manually outside the
  scripts.
- **A CLI flag doesn't exist / behaves differently than documented here**:
  the AgentCore CLI is new and under active development. Run
  `agentcore configure --help` / `agentcore deploy --help` to check current
  flags against what `setup.sh` passes, and open an issue or adjust the
  script to match.
