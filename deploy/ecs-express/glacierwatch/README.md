# Deploying GlacierWatch's web UI to Amazon ECS Express Mode

One-shot scripts to build the GlacierWatch web UI container (FastAPI +
React, `Dockerfile.glacierwatch.webapp` at the repo root) and deploy it to
[Amazon ECS Express Mode](https://aws.amazon.com/blogs/aws/), a managed
service type announced in November 2025 that runs a container behind a
public HTTPS endpoint without you hand-configuring a cluster, task
definition, load balancer, or VPC.

This is **GlacierWatch's first AWS deployment path of any kind** — unlike
BidWright and ClaimClarity, which already have an Amazon Bedrock AgentCore
Runtime path (`deploy/cloudshell/`), GlacierWatch previously only ran
locally (CLI or Streamlit). ECS Express Mode was chosen here instead of
AgentCore because this is a full web application (API + a built React
frontend served from the same container), not a single agent-invocation
endpoint — Express Mode is a better fit for "run this container, give me a
URL" than AgentCore's agent-runtime abstraction.

> **These scripts have not been exercised against a live AWS account.**
> Every command here is the exact, verified-against-current-AWS-docs syntax
> for ECS Express Mode as of when this was written (see the CLI reference
> under [Prerequisites](#prerequisites)) — including a real, offline
> simulation of the Dockerfile's Python install step (see
> `Dockerfile.glacierwatch.webapp`'s stage 2, verified by installing
> `glacierwatch` alone with `pip install -e ".[api]"` into a fresh
> venv containing only the files that stage actually copies) — but the
> scripts themselves have not run against a real AWS account, in the same
> spirit as `deploy/cloudshell/README.md`'s equivalent warning for
> BidWright/ClaimClarity. Read a script before running it, and expect to
> check the [ECS Express Mode CLI reference](https://docs.aws.amazon.com/cli/latest/reference/ecs/)
> if AWS has changed a flag since this was written.

## Cost warning

Running `setup.sh` creates **real, billable AWS resources**: an ECS Express
Gateway Service (Fargate compute behind a managed load balancer), an ECR
repository (image storage), and CloudWatch Log groups. None of this is
free-tier-guaranteed. Run `teardown.sh` when you're done — see its
`--help` for exactly what it does and does not remove automatically.

## Prerequisites

- An AWS account with permission to create ECS services, ECR repositories,
  and (on first use in the account) the two IAM roles ECS Express Mode
  needs — see [IAM roles](#iam-roles-created-once-account-wide) below.
- **AWS CLI ≥ 2.33.15.** `aws ecs update-express-gateway-service` (used by
  re-running `setup.sh` to push a new image to an existing service) needs
  this version or newer; `create`/`describe`/`delete` work on somewhat
  older CLIs. `setup.sh` checks and warns, but can't upgrade the CLI for
  you — see the [AWS CLI install/update guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
- Docker installed and running locally (the image is built and pushed from
  wherever you run `setup.sh`, unlike the AgentCore path in
  `deploy/cloudshell/`, which can build remotely on CodeBuild).
- An `ANTHROPIC_API_KEY`, either exported in your shell or present in the
  repo's `.env` file — `setup.sh` reads it and passes it into the
  container's environment. Without it, the service still starts, but
  `/api/status` reports "No credentials found" until you set it and
  re-run `setup.sh` (which updates the running service in place).

## Usage

From a checkout of this repo, with Docker running and AWS credentials
configured:

```bash
deploy/ecs-express/glacierwatch/setup.sh
```

`setup.sh` will:
1. Confirm before doing anything (creating billable resources) — pass
   `--yes` to skip the prompt for unattended runs, or `--dry-run` to see
   exactly what it would do without touching AWS or Docker.
2. Check your AWS identity, resolve a region, and check your AWS CLI
   version.
3. Create the two required IAM roles if they don't already exist in this
   account (see below) — safe to re-run, and shared with any other
   project in this repo that also deploys via ECS Express Mode.
4. Create an ECR repository if needed, then build and push
   `Dockerfile.glacierwatch.webapp`.
5. Create the `glacierwatch-webui` Express Gateway Service (first run) or
   update it in place with the freshly pushed image (subsequent runs).
6. Write a small deployment manifest (default
   `~/.glacierwatch-ecs-express-deployment.json`) recording the service
   ARN, for `teardown.sh` to read.

Once it's done, the service is reachable at:

```
https://glacierwatch-webui.ecs.<region>.on.aws/
```

(it can take a few minutes after first creation to reach a healthy state —
check with `aws ecs describe-express-gateway-service --service-arn <arn>`).

Made a code change? Just re-run `setup.sh` — it rebuilds, re-pushes, and
calls `update-express-gateway-service` on the existing service.

When you're done:

```bash
deploy/ecs-express/glacierwatch/teardown.sh
```

Safe by default — previews what it's about to destroy and asks first. Use
`--yes` for unattended teardown, `--dry-run` to preview only, and
`--delete-ecr-repo` to also remove the ECR repository and every image tag
in it (off by default, since that also destroys every previously pushed
image, not just the current one).

## IAM roles (created once, account-wide)

ECS Express Mode needs two IAM roles that `setup.sh` creates automatically
if they don't already exist — these are **account-global**, not specific to
GlacierWatch, so if another project in this repo also deploys via ECS
Express Mode in the same account, both setup scripts share (not duplicate)
these roles:

- `ecsTaskExecutionRole` — lets the running task pull the image and write
  logs (`AmazonECSTaskExecutionRolePolicy`).
- `ecsInfrastructureRoleForExpressServices` — lets ECS manage the load
  balancer and networking behind the service
  (`AmazonECSInfrastructureRoleforExpressGatewayServices`).

`teardown.sh` never deletes these roles, since another deployment in the
account might still depend on them — remove them manually via the IAM
console/CLI only if you're certain nothing else uses them.

## Honest limitations

- **`minTaskCount` and `maxTaskCount` are both pinned to 1, on purpose.**
  `glacierwatch/api.py`'s job store (`_jobs`, tracking each run's status,
  activity-log queue, and output directory) is a plain in-memory Python
  dict, scoped to a single process — the same convenient-for-a-hackathon
  choice `app_glacierwatch.py` makes with Streamlit's `st.session_state`.
  A second concurrently-running task behind the same load balancer would
  not share that state: a request routed to task B for a job created on
  task A would 404. Running exactly one task avoids this entirely. Scaling
  this to multiple tasks for real production use would need the job store
  moved to something shared (Redis, DynamoDB, etc.) — out of scope for
  this hackathon submission, but worth knowing before raising
  `maxTaskCount`.
- **Not yet run against a live AWS account** — see the warning at the top
  of this file.
- **The image is built and pushed from wherever you run `setup.sh`**,
  unlike `deploy/cloudshell/`'s AgentCore path, which can build remotely on
  AWS CodeBuild with no local Docker. If you want a CodeBuild-based image
  build for ECS Express Mode too, that's a reasonable future improvement,
  not something these scripts do today.
- **`ANTHROPIC_API_KEY` is passed as a plain environment variable** on the
  container definition (matching the shape AWS's own `create-express-gateway-service`
  examples use) rather than pulled from AWS Secrets Manager/SSM Parameter
  Store at deploy time — fine for a hackathon demo, not a production
  secrets-handling pattern. Swap `--primary-container`'s `environment`
  entry for a `secrets` entry pointing at a Secrets Manager ARN if you take
  this further.

## Files

```
deploy/ecs-express/glacierwatch/
  common.sh     Shared bash helpers: logging, confirm prompts, AWS identity/
                region/CLI-version checks, IAM role idempotency, and the
                deployment manifest read/write functions
  setup.sh      Build + push the image, create/update the Express Gateway
                Service
  teardown.sh   Delete the service (and optionally the ECR repository)
```
