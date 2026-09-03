# Deploying the BidWright web UI to Amazon ECS Express Mode

One-shot scripts to deploy the FastAPI + React web UI (`bidwright/api.py` +
`webapp/bidwright/`, packaged by `Dockerfile.bidwright.webapp`) to
[Amazon ECS Express Mode](https://aws.amazon.com/blogs/containers/) — a
single `aws ecs create-express-gateway-service` call that provisions
Fargate compute, a load balancer/gateway, and a public HTTPS URL together,
without hand-wiring a VPC, target group, or ALB yourself.

This is a different, newer AWS path than
[`deploy/cloudshell/`](../../cloudshell/), which deploys the *agent* (no web
UI, invoked as a Bedrock AgentCore Runtime agent) — this directory deploys
the *web app* container as an ordinary HTTP service on ECS instead.

> **These scripts have not been exercised against a live AWS account.** This
> project was built in a sandbox with no working AWS credentials, so
> everything here is verified as far as offline testing can reach — bash
> syntax (`shellcheck`-clean), the idempotency/manifest logic, and that
> `docker build -f Dockerfile.bidwright.webapp .` actually produces a
> working image whose FastAPI app imports cleanly and serves the built
> frontend (see the main session's verification notes) — but not a real
> `aws ecs create-express-gateway-service` run. Read a script before running
> it, and expect to double-check the exact CLI flags against
> `aws ecs create-express-gateway-service help` if AWS has changed anything
> since this was written — ECS Express Mode was announced in November 2025
> and is a fast-moving, recently launched feature.

## Cost warning

Running `setup.sh` creates **real, billable AWS resources**: an ECS Express
Gateway Service (Fargate compute for the container, plus its managed
gateway/load balancer), an ECR repository (image storage), and CloudWatch
Log groups. None of this is free-tier-guaranteed. Run `teardown.sh` when
you're done — see its `--help` for exactly what it does and does not remove
automatically.

## Prerequisites

- An AWS account with permission to create ECS services, IAM roles, and ECR
  repositories.
- **AWS CLI ≥ 2.33.15.** `aws ecs create-express-gateway-service` and
  `aws ecs update-express-gateway-service` are new subcommands — an older
  CLI won't recognize them at all ("Invalid choice" / "unknown command").
  Run `aws --version` and `pip install --upgrade awscli` /
  `brew upgrade awscli` (or reinstall the CLI v2 package) if needed.
- Docker, running locally (`docker info` must succeed) — `setup.sh` builds
  the image itself; there's no CodeBuild path here like
  `deploy/cloudshell/` uses for AgentCore.
- An `ANTHROPIC_API_KEY` in your shell environment before running
  `setup.sh`, if you want the deployed service to actually be able to run
  bids (otherwise it deploys with `status_text` reporting "No credentials
  found" until you update it — see "Updating credentials later" below).

## Usage

```bash
cd Agents-for-Humans-Hackathon   # or wherever this repo is checked out

export ANTHROPIC_API_KEY=sk-...   # so the deployed service can actually run bids
deploy/ecs-express/bidwright/setup.sh
```

`setup.sh` will:
1. Confirm before doing anything (creating billable resources) — pass
   `--yes` to skip the prompt for unattended runs, or `--dry-run` to see
   exactly what it would do without touching AWS or Docker.
2. Check your AWS identity and resolve a region.
3. Build `Dockerfile.bidwright.webapp` for `linux/amd64` (what Fargate
   runs) and push it to an ECR repository named `bidwright-webui`,
   creating the repository if it doesn't exist yet.
4. Ensure the two IAM roles ECS Express Mode needs exist
   (`ecsTaskExecutionRole`, `ecsInfrastructureRoleForExpressServices`) —
   these are account-global, not per-project, so this step is idempotent
   and safe to run again from a sibling project's `setup.sh` later without
   erroring on "role already exists".
5. Create (or, on a re-run, update in place) an Express Gateway Service
   named `bidwright-webui`, healthchecked against `/api/status`.
6. Write a small manifest (default `~/.ecs-express-bidwright.json`)
   recording the service ARN, for `teardown.sh` to read.

The service URL is printed by `setup.sh` at the end (also visible any time
via `aws ecs describe-express-gateway-service --service-arn <arn>`), in the
form:

```
https://bidwright-webui.ecs.<region>.on.aws/
```

When you're done:

```bash
deploy/ecs-express/bidwright/teardown.sh
```

Safe by default — previews what it's about to destroy and asks first. Use
`--yes` for unattended teardown, `--dry-run` to preview only, `--delete-ecr`
to also remove the ECR repository and every image in it (kept by default).
It never deletes the two shared IAM roles — see its `--help`.

## Updating to a new image

Re-running `setup.sh` (after committing a code change) rebuilds, re-pushes,
and calls `aws ecs update-express-gateway-service` against the service ARN
recorded in the manifest, rather than creating a duplicate service. This is
also the way to rotate `ANTHROPIC_API_KEY` after the fact — `setup.sh`
always sends the current value of that environment variable in the
container's `environment` block, so `export ANTHROPIC_API_KEY=<new value>`
then re-run.

## Honest limitations

**`--scaling-target` defaults to `minTaskCount=1,maxTaskCount=1` — not
autoscaled — on purpose.** `bidwright/api.py`'s job store (`_jobs`, the dict
tracking run status/results) is an ordinary in-memory Python dict, scoped
to one running process, exactly like the rest of this repo's "keep it
correct rather than add a database for a hackathon demo" approach. If ECS
scaled this to two concurrent tasks, a browser polling `GET
/api/runs/{job_id}` after the gateway routed its `POST /api/runs` to task A
could have that poll land on task B instead — which has never heard of that
`job_id` — and get a spurious 404. Running exactly one task avoids this
entirely. If you want real autoscaling, the job store needs to move to
something shared across tasks first (DynamoDB or Redis/ElastiCache are the
obvious choices, checkpointing `status`/`result`/`error` the same way the
in-memory dict does now) — that's real follow-up work, not done here.

**Secrets on the command line.** `setup.sh` passes `ANTHROPIC_API_KEY` to
`aws ecs create-express-gateway-service`/`update-express-gateway-service` as
a literal value in the `--primary-container` JSON argument (matching the
exact CLI shape ECS Express Mode documents for container environment
variables). That value is visible in your shell history and in process
listings (`ps`) while the command runs. For anything beyond a hackathon demo,
prefer AWS Secrets Manager or SSM Parameter Store with a `secrets` block
instead of a literal `environment` value — not done here to keep this script
matching the exact, minimal CLI shape this project was asked to use.

**No custom domain / TLS cert.** The `*.ecs.<region>.on.aws` URL ECS Express
Mode provisions is HTTPS out of the box, which is enough for a hackathon
demo; putting a custom domain in front of it (Route 53 + ACM) is out of
scope here.

## Files

```
deploy/ecs-express/
  common.sh                Shared bash helpers (logging, confirm prompts,
                            AWS identity/region checks, ECR repo helper, the
                            two shared IAM roles, manifest read/write) - used
                            by bidwright/setup.sh and teardown.sh, written to
                            be reusable by a future claimclarity/glacierwatch
                            ECS Express setup.sh too.
  bidwright/
    setup.sh                Build, push, and deploy the BidWright web UI.
    teardown.sh              Tear it back down.
    README.md                This file.
```

## Troubleshooting

- **"Invalid choice: 'create-express-gateway-service'"**: your AWS CLI is
  too old. See the AWS CLI ≥ 2.33.15 prerequisite above.
- **`docker: Cannot connect to the Docker daemon`**: start Docker Desktop
  (or your local Docker daemon) and retry — `setup.sh` checks this up front
  via `docker info` and fails fast with a clear message if it's not
  running.
- **Health check failing / service stuck provisioning**: confirm the
  container is actually listening on port 8000 (`docker run -p 8000:8000
  ...` locally and hit `curl localhost:8000/api/status` before troubleshooting
  on AWS) and that `/api/status` returns 200 even with no model credentials
  set (it does — `ready: false`, not an error status).
- **A CLI flag doesn't exist / behaves differently than documented here**:
  ECS Express Mode is new and under active development. Run
  `aws ecs create-express-gateway-service help` /
  `aws ecs update-express-gateway-service help` to check current flags
  against what `setup.sh` passes, and adjust the script to match.
