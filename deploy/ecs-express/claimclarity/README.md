# Deploying the ClaimClarity web UI to Amazon ECS Express Mode

`setup.sh` / `teardown.sh` deploy the FastAPI + React web UI (built by
`Dockerfile.claimclarity.webapp`) to
[Amazon ECS Express Mode](https://aws.amazon.com/blogs/containers/) — a
single AWS CLI call (`aws ecs create-express-gateway-service`) that stands
up a load-balanced, autoscaled, HTTPS-fronted service without you having to
hand-assemble a VPC, ALB, target group, task definition, and service
yourself. This is separate from, and unrelated to, this repo's other AWS
deployment path — [`deploy/cloudshell/`](../../cloudshell/) puts the
*agent* itself on Bedrock AgentCore Runtime; this puts the *web UI* (which
still calls the Anthropic API directly, not Bedrock) on ECS.

> **These scripts have not been exercised against a live AWS account.** They
> were written and reviewed carefully against the ECS Express Mode CLI
> syntax verified from AWS docs at the time of writing, `bash -n` and
> `shellcheck`-clean, and dry-run-tested end to end (`--dry-run` exercises
> every code path except the actual `aws`/`docker` calls) — but this sandbox
> has no live AWS account or Docker daemon to run a real deploy against.
> Read the script before running it, and expect to debug the first live run
> against the [ECS Express Mode CLI reference](https://docs.aws.amazon.com/cli/latest/reference/ecs/)
> if AWS has changed a flag since this was written — this is a newly
> launched (Nov 2025), fast-moving feature.

## Cost warning

Running `setup.sh` creates **real, billable AWS resources**: an ECR
repository (image storage), an ECS Express Gateway Service (which
provisions an Application Load Balancer and a running Fargate task — both
billed for as long as the service exists), and CloudWatch Logs. None of
this is free-tier-guaranteed. Run `teardown.sh` when you're done.

## Prerequisites

- AWS CLI **v2.33.15 or later** — `update-express-gateway-service` in
  particular needs this; `setup.sh` checks and warns (doesn't block) if
  your CLI looks older. Older CLI versions may not recognize
  `create-express-gateway-service` at all yet.
- Docker, to build `Dockerfile.claimclarity.webapp` locally and push it to
  ECR (this path builds the image on your own machine, unlike the
  CodeBuild-based CloudShell/AgentCore path — bring a machine with a Docker
  daemon, not bare CloudShell).
- AWS credentials configured (`aws configure` or environment variables)
  with permission to create IAM roles, ECR repositories, and ECS Express
  Gateway Services.
- `ANTHROPIC_API_KEY` set in your environment — the deployed container
  calls the Anthropic API directly (not Bedrock), so it needs this to do
  anything.

## Usage

```bash
export ANTHROPIC_API_KEY=sk-ant-...
deploy/ecs-express/claimclarity/setup.sh
```

`setup.sh` will:
1. Confirm before doing anything (creating billable resources) — pass
   `--yes` to skip the prompt, or `--dry-run` to see exactly what it would
   do without touching AWS or Docker.
2. Check your AWS identity, region, and CLI version.
3. Create the two IAM roles ECS Express Mode needs
   (`ecsTaskExecutionRole`, `ecsInfrastructureRoleForExpressServices`) if
   they don't already exist — these are account-global and idempotent, and
   BidWright's/GlacierWatch's own `deploy/ecs-express/*/setup.sh` (if you
   run them too) reuse the same two roles rather than creating duplicates.
4. Create an ECR repository (`claimclarity-webui`) if needed, build
   `Dockerfile.claimclarity.webapp`, and push it.
5. Call `aws ecs create-express-gateway-service` and record the resulting
   service ARN in `~/.claimclarity-ecs-express-deployment.json` for
   `teardown.sh` to read back later.

Then check on it:

```bash
aws ecs describe-express-gateway-service --service-arn <arn-from-setup.sh-output>
```

The URL format is `https://claimclarity-webui.ecs.<region>.on.aws/` — give
the service a few minutes to finish provisioning before it responds.

To push a new image after a code change:

```bash
docker build -f Dockerfile.claimclarity.webapp -t <ecr_uri>:latest .
docker push <ecr_uri>:latest
aws ecs update-express-gateway-service --service-arn <arn> --primary-container '{"image":"<ecr_uri>:latest"}'
```

When you're done:

```bash
deploy/ecs-express/claimclarity/teardown.sh
```

Safe by default — confirms before deleting, `--dry-run` to preview only.
It deletes the ECS Express Gateway Service only; the ECR repository and the
two shared IAM roles are left in place (printed as a manual-cleanup
checklist with read-only `aws` commands) since the other two projects'
scripts may still be using the same IAM roles.

## Honest limitations

- **`minTaskCount`/`maxTaskCount` are both pinned to 1, deliberately.**
  `claimclarity/api.py`'s job store (`_jobs: dict[str, dict]`) is in-memory,
  per-process — a second concurrently-running task would have its own,
  completely separate job dictionary. A request routed to task B for
  `GET /api/runs/{job_id}` for a job that actually ran on task A would 404.
  Scaling this past one task would need a shared store (Redis, DynamoDB,
  etc.) for job state before it's safe — not implemented here. Same
  reasoning as any other in-memory job queue behind a load balancer.
- **No authentication, at all.** `claimclarity/api.py` has none by design
  (see `CLAIMCLARITY.md`'s "Web UI" section) — job ids are unguessable
  (`uuid4`), which prevents casual enumeration, but that is not access
  control. **Do not deploy this with real patient denial notices or medical
  record excerpts without adding an authentication/authorization layer in
  front of it first** (e.g. an ALB with Cognito/OIDC auth, or an API
  gateway in front of it) — this handles health-adjacent, potentially
  sensitive data, and shipping it publicly reachable with zero auth is a
  real risk, not a hypothetical one.
- **`ANTHROPIC_API_KEY` is passed as a plain container environment
  variable** in the `--primary-container` JSON (matching the exact syntax
  this was written against) — visible to anyone who can call
  `DescribeTaskDefinition`/`describe-express-gateway-service` with
  sufficient IAM permission on your account, and to anyone who can exec
  into the container. A production deployment should use AWS Secrets
  Manager or Parameter Store and reference it as a task-definition secret
  instead of a literal value — not done here, to keep this script matching
  the exact verified CLI syntax it was built from.
- This container builds the frontend and installs the backend from your
  local checkout at build time — there's no CI step verifying the pushed
  image matches what `pytest` last passed against. Run `pytest` and
  `npm run build` yourself before pushing a new image (see the repo root
  README/`CLAIMCLARITY.md`).
