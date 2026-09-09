# Deploying from AWS CloudShell

Complete instructions for every deployment path that runs from
[AWS CloudShell](https://console.aws.amazon.com/cloudshell/) — no local
install, no Docker daemon, nothing to configure on your own machine.

> **Read this first.** These scripts create **real, billable AWS resources**.
> Every one supports `--dry-run`, which prints what it would do and touches
> nothing — use it first. Run the matching `teardown.sh` when you're finished.
>
> **None of these scripts has been run against a live AWS account.** They are
> syntax-checked, shellcheck-clean, dry-runnable, and their CLI parameters come
> from the AWS CLI command reference — but no deployment has actually been
> performed. Read the script before you run it, and watch the first CodeBuild
> build's logs closely.

## What can and cannot be deployed from CloudShell

| Path | Deploys | CloudShell? |
|---|---|---|
| [`cloudshell/`](cloudshell/) | BidWright + ClaimClarity → AgentCore Runtime | ✅ yes |
| [`trinetra/`](trinetra/) | Trinetra headless action API → AgentCore Runtime | ✅ yes |
| [`ecs-express/trinetra/`](ecs-express/trinetra/) | Trinetra dashboard → ECS Express (HTTPS URL) | ✅ yes — builds on CodeBuild |
| [`ecs-express/trinetra-a2a/`](ecs-express/trinetra-a2a/) | Trinetra A2A agent → ECS Express | ✅ yes — builds on CodeBuild |
| `ecs-express/bidwright/` | BidWright web UI | ❌ **no** — runs `docker build` locally |
| `ecs-express/claimclarity/` | ClaimClarity web UI | ❌ **no** — local `docker build` |
| `ecs-express/glacierwatch/` | GlacierWatch web UI | ❌ **no** — local `docker build` |

CloudShell has no Docker daemon, so the last three need a machine with Docker.
The two Trinetra ECS paths avoid this by having **AWS CodeBuild** build the
image instead — that is the difference, and it is why they work here.

GlacierWatch has no CloudShell path at all: its only AWS deployment is the
local-Docker ECS one.

## Prerequisites

**1. A model provider.** Pick one:

- **Bedrock** (default) — needs **model access enabled for Anthropic Claude
  models in your target region**. Bedrock console → Model access. This is a
  manual, per-account/per-region opt-in with no reliable CLI toggle, and a
  missing grant is the single most common cause of a failed deployment here.
  No API key is involved; the agent's IAM execution role authorises the calls.
- **Anthropic API key** — set `ANTHROPIC_API_KEY` in your CloudShell shell
  before running, and pass `--model-provider anthropic`. See
  [the note on how the key travels](#a-note-on-the-anthropic-key) below.

**2. For the two ECS Express paths only — a one-time GitHub source credential.**
CodeBuild clones this repo over a `GITHUB` source. If your account has never
used that source type in this region, the build fails with an error mentioning
GitHub source credentials or "not connected". Link one once:

```bash
aws codebuild import-source-credentials \
  --server-type GITHUB --auth-type PERSONAL_ACCESS_TOKEN \
  --token <a GitHub PAT with public_repo scope> --region <your region>
```

Or use the CodeBuild console's "Connect to GitHub" flow once, then re-run.
The scripts deliberately do not automate this — it would mean handling your
GitHub token.

**3. Region.** AgentCore Runtime's regional availability changes over time.
`setup.sh` warns (does not block) if your region isn't on its known-good list.
Set it explicitly if CloudShell's default isn't what you want:

```bash
export AWS_REGION=us-west-2
```

## Step 1 — Open CloudShell and clone

Open the AWS Console, **switch to your target region**, then click the
CloudShell icon in the top navigation bar.

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon
```

Everything Trinetra-related currently lives on a feature branch, so check it
out if you're deploying any Trinetra path:

```bash
git checkout claude/trinetra-nashik-kumbh-2027
```

This matters for the two ECS paths beyond your local checkout: CodeBuild builds
from a **branch on the remote**, defaulting to whatever you have checked out
here. Override with `--branch <name>` if you need a different one.

Confirm your identity and region before spending anything:

```bash
aws sts get-caller-identity
echo "$AWS_REGION"
```

## Step 2 — Choose a path and deploy

Always dry-run first. Each script prints exactly what it would create.

### A. BidWright + ClaimClarity → AgentCore Runtime

```bash
cd deploy/cloudshell

./setup.sh --dry-run                 # preview, touches nothing
./setup.sh                           # deploy (Bedrock, the default)
```

With an Anthropic key instead of Bedrock:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
./setup.sh --model-provider anthropic
```

Other flags: `--yes` (skip the confirmation prompt), `--region REGION`,
`--deployment-type container|direct_code_deploy` (container is the default and
better documented).

Then exercise it:

```bash
./invoke_samples.sh                    # both agents
./invoke_samples.sh --agent bidwright  # just one
```

### B. Trinetra headless action API → AgentCore Runtime

Same pattern, different directory. This deploys `agentcore_app_trinetra.py`,
which routes `ask` / `sos` / `simulate` / `calibrate`.

```bash
cd deploy/trinetra

./setup.sh --dry-run
./setup.sh                                   # Bedrock
./setup.sh --model-provider anthropic        # or Anthropic (key must be exported)

./invoke_samples.sh                          # all four actions
./invoke_samples.sh --action calibrate       # just one
```

### C. Trinetra dashboard → ECS Express Mode (public HTTPS URL)

This is the one to pick if you want something to *show* someone — the
nine-view operator dashboard behind a managed HTTPS URL, with the image built
on CodeBuild.

```bash
cd deploy/ecs-express/trinetra

./setup.sh --dry-run
./setup.sh
```

It creates an ECR repo, a CodeBuild project and role, starts a build, polls it
to completion, then creates the Express service and prints the real URL it was
assigned. First run takes several minutes, most of it CodeBuild.

Pass `ANTHROPIC_API_KEY` through by exporting it before running — it is
injected into the service as a runtime environment variable, not baked into
the image.

### D. Trinetra A2A agent → ECS Express Mode

Publishes Trinetra as an Agent2Agent agent other organisations' agents can
discover and call.

```bash
cd deploy/ecs-express/trinetra-a2a

./setup.sh --dry-run
./setup.sh
```

This one deploys in **two phases**: create the service, poll for the real
public endpoint, then update the service so the published agent card
advertises an address peers can actually reach. That is why it takes longer
than path C and why the output mentions a second update.

**Before exposing this to the internet, read
[`ecs-express/trinetra-a2a/README.md`](ecs-express/trinetra-a2a/README.md)'s
security section.** ECS Express gives you a public HTTPS URL but *not* an
authentication layer — as shipped, anyone who finds the URL can call the agent
and spend your model budget.

Verify the card once it's up:

```bash
curl https://<service-url>/.well-known/agent-card.json | python3 -m json.tool
```

The card's `url` field should match the address you curled. If it shows a
container-internal address, phase 2 didn't finish — re-run `./setup.sh`, which
is idempotent.

## Step 3 — Tear down

**Do this when you're done.** Each path has its own teardown, and each reads
its own manifest file:

```bash
deploy/cloudshell/teardown.sh              # BidWright + ClaimClarity
deploy/trinetra/teardown.sh                # Trinetra AgentCore
deploy/ecs-express/trinetra/teardown.sh    # Trinetra dashboard
deploy/ecs-express/trinetra-a2a/teardown.sh
```

Useful flags on the AgentCore teardowns: `--yes`, `--agent NAME`, `--dry-run`,
`--keep-ecr` (ECR image storage is the main ongoing cost otherwise left
behind).

The two account-global IAM roles that ECS Express needs
(`ecsTaskExecutionRole`, `ecsInfrastructureRoleForExpressServices`) are
**never** deleted, because other services in your account may be using them.
Remove them by hand only if you're certain nothing else needs them.

### Manifests

Each deployment records what it created, so teardown knows what to remove:

| Path | Manifest | Override with |
|---|---|---|
| `cloudshell/` | `~/.agentcore-deployment.json` | `AGENTCORE_MANIFEST` |
| `trinetra/` | `~/.trinetra-agentcore-deployment.json` | `TRINETRA_AGENTCORE_MANIFEST` |
| `ecs-express/trinetra/` | `~/.trinetra-ecs-express-deployment.json` | `TRINETRA_ECS_MANIFEST` |
| `ecs-express/trinetra-a2a/` | `~/.trinetra-a2a-ecs-express-deployment.json` | `TRINETRA_A2A_ECS_MANIFEST` |

**CloudShell's home directory persists** between sessions (up to its storage
limit), so these survive a session timeout and teardown still works when you
come back. They are the only record of what was created — if you lose one,
you're deleting resources by hand in the console.

## A note on the Anthropic key

The key is never baked into an image and CodeBuild never receives it. The
scripts redact it even in `--dry-run` output.

For the **ECS Express** paths it is passed as a runtime environment variable
when the service is created or updated — a step separate from the image build.

For the **AgentCore** paths, `agentcore deploy --env KEY=VALUE` is the only
mechanism the AgentCore CLI supports: it has no native Secrets Manager or SSM
Parameter Store integration for this, so the raw value goes on the command line
for that one command. That is a real limitation of the tool, stated here rather
than hidden. If that is unacceptable for your account, use `--model-provider
bedrock`, where model calls are authorised by the agent's IAM execution role
and no key exists to leak.

## Troubleshooting

**`AccessDeniedException` / model access errors**
Bedrock model access isn't enabled for Claude in that region. Bedrock console
→ Model access. Check the region matches too.

**CodeBuild fails mentioning GitHub source credentials**
See prerequisite 2 above — one-time per account and region.

**CodeBuild fails on the build itself**
The script prints a CloudWatch Logs pointer on failure. Read the build log
before re-running; a re-run rebuilds from scratch and costs more minutes.

**The Express service is up but returns 503**
It can take a few minutes after creation to reach RUNNING and pass health
checks. Check with:

```bash
aws ecs describe-express-gateway-service --service-arn <arn> --region <region>
```

**`aws ecs ... express-gateway-service` is not a valid command**
Your AWS CLI is too old. ECS Express Mode needs **v2 ≥ 2.33.15**. CloudShell's
CLI is usually current, but check with `aws --version` — the scripts warn about
this too.

**A teardown says it can't find the deployment**
The manifest is missing (see the table above). Check whether you set an
override env var in a previous session, or pass the path explicitly.
