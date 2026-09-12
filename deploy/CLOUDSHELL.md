# Deploying from AWS CloudShell

Complete instructions for every deployment path that runs from
[AWS CloudShell](https://console.aws.amazon.com/cloudshell/) — no local
install, no Docker daemon, nothing to configure on your own machine.

> **Read this first.** These scripts create **real, billable AWS resources**.
> Every one supports `--dry-run`, which prints what it would do and touches
> nothing — use it first. Run the matching `teardown.sh` when you're finished.
>
> **Deployment status, per path.** The **dashboard** path
> (`ecs-express/trinetra/`) **has been deployed successfully** and is live at
> <https://tr-f84a1a73e8154b1c88e4d700c96ccb64.ecs.us-east-1.on.aws> — CodeBuild built the image, ECS Express provisioned the service, and
> the Anthropic provider pin came through correctly.
>
> The other three paths (`ecs-express/trinetra-a2a/`, `cloudshell/`,
> `trinetra/`) have **not** been run against a live account. They are
> syntax-checked, shellcheck-clean, dry-runnable, and their CLI parameters come
> from the AWS CLI command reference — but no deployment has been performed.
> Read the script before running one, and watch the first CodeBuild log closely.

## What can and cannot be deployed from CloudShell

| Path | Deploys | CloudShell? |
|---|---|---|
| [`cloudshell/`](cloudshell/README.md) | BidWright + ClaimClarity → AgentCore Runtime | ✅ yes |
| [`trinetra/`](trinetra/README.md) | Trinetra headless action API → AgentCore Runtime | ✅ yes |
| [`ecs-express/trinetra/`](ecs-express/trinetra/README.md) | Trinetra dashboard → ECS Express (HTTPS URL) | ✅ yes — builds on CodeBuild |
| [`ecs-express/trinetra-a2a/`](ecs-express/trinetra-a2a/README.md) | Trinetra A2A agent → ECS Express | ✅ yes — builds on CodeBuild |
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
  [Deploying Trinetra with the Anthropic API](#deploying-trinetra-with-the-anthropic-api-no-bedrock)
  below.

**2. For the two ECS Express paths only — possibly a one-time GitHub source
credential.** CodeBuild clones this repo over a `GITHUB` source. The repo is
**public**, so CodeBuild can usually clone it with no credential at all. But if
your account has never used a `GITHUB` source in this region, the build can
still fail with an error mentioning source credentials or "not connected". If
that happens, link one once — it is per account and region, not per build:

```bash
aws codebuild import-source-credentials \
  --server-type GITHUB --auth-type PERSONAL_ACCESS_TOKEN \
  --token <a GitHub PAT with public_repo scope> --region <your region>
```

Or use the CodeBuild console's "Connect to GitHub" flow once, then re-run.
The scripts deliberately do not automate this — it would mean handling your
GitHub token. Try the deploy first; only do this if it actually complains.

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

### E. Everything Trinetra, in one command

Paths C and D in a single run, both built on CodeBuild:

```bash
cd deploy/ecs-express

./deploy_trinetra_all.sh --dry-run
./deploy_trinetra_all.sh
```

It runs the dashboard first, then the A2A agent, and prints both real URLs at
the end. A failure in one does **not** abort the other — if the dashboard
deploys and the A2A agent does not, you keep the thing that worked and get told
plainly which failed. Use `--only dashboard` or `--only a2a` to run just one.

**The frontend is already included.** `Dockerfile.trinetra.webapp` is a
multi-stage build: Node compiles the React app, and the built bundle is copied
into the Python image where FastAPI serves it from the same process. There is
no separate frontend deployment, and no CORS configuration, because the API and
the static bundle share one origin. CodeBuild does the Node build for you —
you do not need `npm` anywhere.

Tear both down together:

```bash
./teardown_trinetra_all.sh
```

## Deploying Trinetra with the Anthropic API (no Bedrock)

If you have an Anthropic API key and would rather not enable Bedrock model
access, all three Trinetra paths support it. The mechanics differ slightly, so
they are collected here.

**Set the key once in your CloudShell session.** Everything below reads it
from the environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The two ECS scripts also fall back to reading `ANTHROPIC_API_KEY` from a `.env`
in the repo root if the variable is unset, which is convenient locally but
means you should check what is actually picked up before deploying.

### The dashboard (what most people want)

```bash
cd deploy/ecs-express/trinetra
./setup.sh --dry-run
./setup.sh
```

No flag needed — the script detects the key and pins
`TRINETRA_MODEL_PROVIDER=anthropic` on the service, so the provider is visible
in the ECS service definition rather than inferred at runtime. If no key is
found it warns and continues; the service then starts but reports
`No credentials found` at `/api/status`.

**Re-running `./setup.sh` after a code change updates the running service in
place** (a fresh CodeBuild build from `--branch`, then
`update-express-gateway-service`) — this is how you deploy the latest commit
to an already-live dashboard, not a separate command. It also picks up the
same environment/`.env` variables again, so editing `.env` and re-running
updates the live service's environment too.

The same `.env`-fallback pattern also covers `THINGSBOARD_URL`/`_USERNAME`/
`_PASSWORD`/`_API_KEY` (Kshetra Netra's live signals, Anukaran Netra's
seeding, the alarm webhook — see TRINETRA.md) and `TRINETRA_WEBHOOK_SECRET`
(the alarm webhook's shared secret — required for that one endpoint to
accept anything; unset means it returns 503 for every request). All are
optional: unset, the deployed service behaves exactly like an unconfigured
local run for those features, not a startup failure.

### The A2A agent

```bash
cd deploy/ecs-express/trinetra-a2a
./setup.sh --dry-run
./setup.sh
```

Same detection. Note this path updates the service twice (see path D above),
and the key is re-applied on the second update along with the public URL.

### The headless action API (AgentCore)

This one needs an explicit flag, because it defaults to Bedrock:

```bash
cd deploy/trinetra
./setup.sh --model-provider anthropic
```

### Verifying which provider a deployment actually used

For the dashboard, the status endpoint answers directly:

```bash
curl https://<service-url>/api/status
# {"status_text":"Anthropic API direct (claude-sonnet-4-5-20250929)","ready":true}
```

Or read it back off the service definition without any model call:

```bash
aws ecs describe-express-gateway-service --service-arn <arn> --region <region> \
  --query 'service.activeConfigurations[].primaryContainer.environment[?name==`TRINETRA_MODEL_PROVIDER`].value' \
  --output text
```

### How the key travels, and where it is visible

- **CodeBuild never receives it.** The image is built with no credential baked
  in; the key is applied only when the ECS service is created or updated.
- **On ECS** it is a plain environment variable on the service definition, so
  anyone with `ecs:DescribeExpressGatewayService` in your account can read it.
  That is normal for this pattern but worth knowing — for anything beyond a
  demo, move it to Secrets Manager and reference it via the container
  definition's `secrets` field instead of `environment`.
- **On AgentCore** the key goes on the command line of a single
  `agentcore deploy --env` invocation. The AgentCore CLI has no Secrets
  Manager or SSM integration for this, so that is the only mechanism available.
- **Nothing prints it.** The scripts redact the value in dry-run output.

If passing a raw key is unacceptable for your account, use Bedrock instead —
there the agent's IAM execution role authorises the model calls and no key
exists to leak.

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
