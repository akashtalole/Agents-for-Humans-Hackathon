# Deploying Trinetra's web UI to Amazon ECS Express Mode (via AWS CodeBuild)

One-shot scripts to build Trinetra's web UI image on **AWS CodeBuild** and
deploy it to **Amazon ECS Express Mode** — a managed, autoscaled HTTPS
service with no cluster, task definition, load balancer, or VPC to
hand-configure. Runnable entirely from [AWS CloudShell](https://aws.amazon.com/cloudshell/)
or any shell with the AWS CLI configured — **no local Docker required**,
because CodeBuild does the image build, not your machine.

This is the CodeBuild-based sibling of `deploy/ecs-express/glacierwatch/`,
which builds and pushes its image locally (`docker build` + `docker push`
from wherever you run its `setup.sh`) — that project's own README names the
CodeBuild gap explicitly as "a reasonable future improvement." This
directory is that improvement, applied to Trinetra.

> **These scripts have not been exercised against a live AWS account.**
> Read a script before running it, and watch the CodeBuild build's own logs
> closely on the first run.

## How this differs from `deploy/cloudshell/trinetra`

This repo now has **two** AWS deployment paths for Trinetra:

| | `deploy/cloudshell/` (AgentCore) | `deploy/ecs-express/trinetra/` (this directory) |
|---|---|---|
| Deploys | `agentcore_app_trinetra.py` — the action-routed JSON entrypoint (`ask`/`sos`/`simulate`/`calibrate`) | `trinetra/api.py` + the built React dashboard (`webapp/trinetra/`) — the full web UI |
| Runtime | Amazon Bedrock AgentCore Runtime | Amazon ECS Express Mode (Fargate) |
| Image build | AgentCore CLI's own managed CodeBuild integration | AWS CodeBuild, explicitly configured here (`buildspec.yml`) |
| Invoke via | `agentcore invoke` / the AgentCore CLI | A public HTTPS URL, straight to the dashboard |

Pick this directory if you want the actual dashboard (digital twin, pilgrim
chat, admin brief) reachable at a URL. Pick `deploy/cloudshell/` if you
want the headless action API instead.

## Cost warning

Running `setup.sh` creates **real, billable AWS resources**: AWS CodeBuild
build minutes, an ECS Express Gateway Service (Fargate compute + a managed
load balancer), an ECR repository, and CloudWatch Log groups. Run
`teardown.sh` when you're done.

## Prerequisites

- An AWS account with permission to create CodeBuild projects, ECS
  services, ECR repositories, and (on first use in the account) the two
  IAM roles ECS Express Mode needs — see
  [IAM roles](#iam-roles) below.
- **AWS CLI ≥ 2.33.15.** `aws ecs update-express-gateway-service` (used
  when re-running `setup.sh` to push a new image to an existing service)
  needs this version or newer. `setup.sh` checks and warns, but can't
  upgrade the CLI for you.
- **No Docker required.** AWS CodeBuild builds the image; you never need a
  local Docker daemon, which is exactly why this path exists.
- An `ANTHROPIC_API_KEY`, either exported in your shell or present in the
  repo's `.env` file — `setup.sh` reads it and passes it into the
  container's environment when creating/updating the ECS service. **This
  key never reaches CodeBuild or the built image** — see
  [How the CodeBuild build works](#how-the-codebuild-build-works) below.
- **A one-time-per-account/region GitHub source prerequisite CodeBuild may
  need.** This repo is public, so CodeBuild can usually clone it with no
  credentials configured at all. If `setup.sh` fails at the CodeBuild step
  with an error mentioning GitHub source credentials or "not connected,"
  your AWS account has never used a `GITHUB` source type with CodeBuild in
  this region before — link one (a personal access token is simplest):
  ```bash
  aws codebuild import-source-credentials \
    --server-type GITHUB --auth-type PERSONAL_ACCESS_TOKEN \
    --token <a GitHub PAT with public_repo scope> --region <your region>
  ```
  or use the CodeBuild console's "Connect to GitHub" flow once, then re-run
  `setup.sh`. This is an AWS account-level, one-time step — not something
  this script can safely automate (it would mean handling a GitHub token
  inside this repo's own scripts), and not every account needs it.

## Usage

From a checkout of this repo, with AWS credentials configured (no Docker
needed):

```bash
deploy/ecs-express/trinetra/setup.sh
```

`setup.sh` will:
1. Confirm before doing anything (creating billable resources) — pass
   `--yes` to skip the prompt, or `--dry-run` to preview without touching
   AWS.
2. Check your AWS identity, resolve a region, and check your AWS CLI
   version.
3. Create the two account-global ECS Express IAM roles if they don't
   already exist, plus a Trinetra-specific CodeBuild service role.
4. Create an ECR repository if needed.
5. Create or update a CodeBuild project pointed at this repo's GitHub URL
   (branch: the one currently checked out, or `--branch NAME`), start a
   build, and poll until it finishes — CodeBuild builds
   `Dockerfile.trinetra.webapp` and pushes the image to ECR.
6. Create (first run) or update (subsequent runs) the `trinetra-webui`
   Express Gateway Service, injecting `ANTHROPIC_API_KEY` as a runtime
   environment variable.
7. Write a deployment manifest (default
   `~/.trinetra-ecs-express-deployment.json`) for `teardown.sh` to read.

Once it's done, the service is reachable at:

```
https://trinetra-webui.ecs.<region>.on.aws/
```

(it can take a few minutes after first creation to reach a healthy state —
check with `aws ecs describe-express-gateway-service --service-arn <arn>`).

**Made a code change?** Push it to the branch you're deploying from, then
just re-run `setup.sh` — it triggers a fresh CodeBuild build from the
latest commit on that branch, then updates the service in place once the
build succeeds.

When you're done:

```bash
deploy/ecs-express/trinetra/teardown.sh
```

Safe by default — previews what it's about to destroy and asks first. Use
`--yes` for unattended teardown, `--dry-run` to preview only,
`--delete-ecr-repo` to also remove the ECR repository and every image tag
in it (off by default), and `--keep-codebuild` to leave the CodeBuild
project and its IAM role in place (they're deleted by default, since —
unlike the ECR image history — they're single-purpose to this deployment
and `setup.sh` recreates both cheaply if missing).

## How the CodeBuild build works

`buildspec.yml` in this directory does exactly three things: log in to ECR,
`docker build -f Dockerfile.trinetra.webapp`, then `docker push`. Nothing
in that file — or anywhere in the CodeBuild project `setup.sh` creates —
references `ANTHROPIC_API_KEY` or any model credential. The built image has
no secret baked into it. The key is injected only when `setup.sh` calls
`create-express-gateway-service` / `update-express-gateway-service`, a
separate step that runs *after* the CodeBuild build completes — the same
"CodeBuild only builds the image, credentials are injected later as a
runtime environment variable" principle `deploy/cloudshell/README.md`
documents for the AgentCore path.

## IAM roles

Three roles, two of them shared with any other project in this repo that
also deploys via ECS Express Mode:

- `ecsTaskExecutionRole` **(account-global)** — lets the running task pull
  the image and write logs.
- `ecsInfrastructureRoleForExpressServices` **(account-global)** — lets ECS
  manage the load balancer and networking behind the service.
- `trinetra-codebuild-webui-role` **(Trinetra-specific)** — lets CodeBuild
  push to ECR and write its own build logs to CloudWatch. `teardown.sh`
  deletes this one by default (pass `--keep-codebuild` to keep it).

`teardown.sh` never deletes the two account-global roles, since another
deployment in the account might still depend on them.

## Honest limitations

- **`minTaskCount` and `maxTaskCount` are both pinned to 1, on purpose.**
  `trinetra/api.py`'s job store (`_jobs`, tracking each simulation's status
  and SSE event queue) is a plain in-memory Python dict, scoped to a single
  process — same reasoning as `deploy/ecs-express/glacierwatch/README.md`'s
  identical limitation. A second concurrently-running task behind the same
  load balancer would not share that state. Scaling this to multiple tasks
  would need the job store moved to something shared (Redis, DynamoDB,
  etc.) — out of scope for this submission.
- **Not yet run against a live AWS account** — see the warning at the top
  of this file.
- **`ANTHROPIC_API_KEY` is passed as a plain environment variable** on the
  container definition rather than pulled from AWS Secrets Manager/SSM
  Parameter Store at deploy time — fine for a demo, not a production
  secrets-handling pattern. Swap `--primary-container`'s `environment`
  entry in `setup.sh` for a `secrets` entry pointing at a Secrets Manager
  ARN if you take this further.
- **CodeBuild builds are triggered manually by re-running `setup.sh`**,
  not on every git push. Wiring a GitHub webhook (`aws codebuild
  create-webhook`) for real CI/CD is a reasonable next step, not something
  this script does today.
- **The GitHub source-credentials prerequisite** (see above) can't be
  automated by this script without asking for a GitHub token to be handled
  inside repo code, which this project avoids on principle — it's a
  one-time, per-account manual step instead.

## Files

```
deploy/ecs-express/trinetra/
  common.sh       Shared bash helpers: logging, confirm prompts, AWS identity/
                  region/CLI-version checks, IAM role idempotency, and the
                  deployment manifest read/write functions
  buildspec.yml   The CodeBuild build steps (ECR login, docker build, docker push)
  setup.sh        Build via CodeBuild, create/update the Express Gateway Service
  teardown.sh     Delete the service, CodeBuild project/role, and optionally the ECR repository
```
