# Agents for Humans: building a CloudShell-only deployment path on ECS Express Mode

*Draft for publication on [builder.aws](https://builder.aws/). Keep "Agents for
Humans" in the title — that is the bonus-content rule. Suggested tags: `ecs`,
`fargate`, `codebuild`, `cloudshell`, `bedrock`, `generative-ai`, `agents`.*

---

**It's live:** <https://tr-f84a1a73e8154b1c88e4d700c96ccb64.ecs.us-east-1.on.aws>

That is a nine-view React dashboard and a FastAPI backend running eight Strands
agents, in one container on Amazon ECS Express Mode, with the image built by AWS
CodeBuild — deployed entirely from a browser tab. No Docker daemon was involved
at any point.

This post is about how that path was built, and about three bugs the AWS CLI
command reference found in my own scripts before I ever spent money running
them.

---

## The constraint that shaped everything

I built [Trinetra](https://github.com/akashtalole/Agents-for-Humans-Hackathon),
a multi-agent platform for the Nashik-Trimbakeshwar Kumbh Mela 2027, on the
Strands Agents SDK. Two services need to reach the internet: a React + FastAPI
operator dashboard, and an [Agent2Agent](https://a2a-protocol.org/) endpoint that
other agencies' agents can discover and call.

I gave myself one rule: **the whole deployment must run from AWS CloudShell.**

Not because CloudShell is glamorous, but because of who this is for. If NTKMA or
a municipal IT team ever wants to stand this up, "install Docker, configure
credentials, hope your laptop's architecture matches" is a real barrier. A
browser tab and an AWS login is not.

CloudShell has no Docker daemon. That single fact drives the entire design.

## Amazon ECS Express Mode, and why it fits

[ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)
takes three inputs — a container image, a task execution role, an infrastructure
role — and provisions the rest: a Fargate service, an Application Load Balancer
with TLS, a public HTTPS URL, autoscaling, CloudWatch logs and networking.

For a hackathon project that needs a URL to show someone, that is close to
ideal. The alternative is a cluster, a task definition, a target group, a
listener, security groups and a certificate — each of which is a thing to get
wrong before anyone sees your agent work.

Two details worth knowing up front:

- **It shares Application Load Balancers** across Express services using the
  same networking configuration, which keeps cost down when you run more than
  one.
- **All the underlying resources stay in your account**, visible and
  manageable. It is a convenience layer, not a black box.

## Solving "no Docker" with CodeBuild

If CloudShell cannot build an image, something else must. That something is
**AWS CodeBuild**, pointed at the public GitHub repo, with `privilegedMode`
enabled for docker-in-docker:

```yaml
# deploy/ecs-express/trinetra/buildspec.yml
version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region "$AWS_DEFAULT_REGION" \
          | docker login --username AWS --password-stdin \
            "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
  build:
    commands:
      - docker build -f Dockerfile.trinetra.webapp -t "${ECR_REPO_URI}:latest" .
  post_build:
    commands:
      - docker push "${ECR_REPO_URI}:latest"
```

The setup script creates the ECR repo and CodeBuild project, starts a build,
polls it to completion, and only then creates the Express service. From
CloudShell, with nothing installed locally.

This also solves a problem I did not set out to solve. The dashboard image is a
multi-stage build: Node compiles the React frontend, then the built bundle is
copied into the Python image where FastAPI serves it from the same process.

```dockerfile
FROM node:20-slim AS frontend-build
WORKDIR /app/webapp/trinetra
COPY webapp/trinetra/package.json webapp/trinetra/package-lock.json ./
RUN npm ci
COPY webapp/trinetra/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY pyproject.toml README.md ./
COPY trinetra/ ./trinetra/
COPY server_trinetra.py ./
RUN pip install --no-cache-dir -e ".[api]"
COPY --from=frontend-build /app/webapp/trinetra/dist ./webapp/trinetra/dist
EXPOSE 8000
CMD ["python", "server_trinetra.py"]
```

One container, one origin, no CORS configuration — and **CodeBuild runs the
`npm` build**, so nobody deploying this needs Node either. Someone reviewing my
work later assumed the frontend needed a separate deployment. It does not, and
that was worth writing down in the scripts themselves.

## Three bugs the CLI reference found in my own scripts

Here is the part I would want to read.

I had written the ECS Express deployment from a general understanding of the
service. Later I went back and read the AWS CLI command reference for
`create-express-gateway-service` line by line. It found three real bugs.

### 1. I was printing a URL I had invented

My script ended with a friendly line:

```bash
log_info "URL format: https://${SERVICE_NAME}.ecs.${REGION}.on.aws/"
```

That hostname pattern was a guess. The reference is explicit: the endpoint comes
back in the service response, under `activeConfigurations[].ingressPaths[]`, each
entry tagged `PUBLIC` or `PRIVATE`:

```bash
aws ecs describe-express-gateway-service \
  --service-arn "$SERVICE_ARN" --region "$REGION" \
  --query 'service.activeConfigurations[].ingressPaths[?accessType==`PUBLIC`].endpoint' \
  --output text
```

**The live deployment settled this decisively.** The real URL is:

```
https://tr-f84a1a73e8154b1c88e4d700c96ccb64.ecs.us-east-1.on.aws
```

That `tr-f84a1a73e8154b1c88e4d700c96ccb64` prefix is a generated hash. My guessed
pattern would have produced `https://trinetra-webui.ecs.us-east-1.on.aws/` —
confidently wrong, and wrong in a way that looks plausible enough to ship.

A guessed URL is worse than no URL, and much worse for an A2A agent than for a
dashboard. An agent card *advertises* the address peers should call back on. If
that address is wrong, a peer resolves it, fails, and has **no way to distinguish
a bad address from a service that is merely down**. It will look like your agent
is offline, forever, to everyone.

### 2. My CPU and memory values were off by a factor of a thousand

I had written:

```bash
--cpu 1 --memory 2        # "one vCPU, two gigs", I thought
```

The reference documents `--cpu` as **CPU units** (default 256 = 0.25 vCPU) and
`--memory` as **MiB** (default 512). So I had asked for one CPU unit and two
mebibytes. Now:

```bash
--cpu 1024 --memory 2048
```

### 3. A flag passed without its value

I had `--monitor-resources` as a bare flag. It takes a value. Passed bare, the
CLI would have consumed the *next* argument — `--region` — as its value. It is
optional, so I removed it rather than guess at the right enum.

**The lesson generalises past ECS:** reading the CLI reference for a service you
think you know is one of the cheapest reviews available. All three of these
would have surfaced as confusing runtime failures *after* paying for a CodeBuild
run.

One caution on how you check. I first tried fetching an AWS docs page through a
summarising tool. The page came back essentially empty, and the summariser
confidently told me `create-express-gateway-service` **does not exist** and
suggested `create-service` instead. That was fabrication from an empty page. The
command is real; the CLI reference has its full parameter list. If a summary
tells you something surprising, go and look at the primary source.

## The two-phase deploy an agent card needs

The A2A service has a genuine chicken-and-egg problem, and it is the most
interesting piece of AWS plumbing here.

An A2A agent card is JSON at `/.well-known/agent-card.json` that tells other
agents where to call you. But a container has no way to know the address a load
balancer answers on. The URL does not exist until the service is created — and
the service is created *from* the container.

So the deploy runs in two phases:

1. **Create** the Express service from the built image. The card is published,
   but advertising the container's own bind address — useless externally.
2. **Discover** the real endpoint from `ingressPaths[]`. It is not published the
   instant the service is created, so poll rather than reading once:

   ```bash
   for attempt in $(seq 1 30); do
       SERVICE_URL=$(describe_service_url "$SERVICE_ARN" "$REGION")
       [[ -n "$SERVICE_URL" ]] && break
       sleep 20
   done
   ```

3. **Update** the service with `TRINETRA_A2A_PUBLIC_URL` set to that endpoint,
   so the republished card advertises an address peers can actually reach.

The health check is a small piece of elegance: `--health-check-path` defaults to
`/ping`, but the agent card itself is a plain `GET` returning 200 whenever the
agent is up. Pointing the health check at
`/.well-known/agent-card.json` means the liveness probe and the thing peers
consume are the same endpoint — one less thing to maintain and drift.

## Two manifest collisions that would have orphaned billable resources

Each deployment writes a small JSON manifest recording what it created, so
teardown knows what to remove. I had four deployment paths. Two pairs of them
defaulted to the **same manifest file**.

- The Trinetra AgentCore path and the BidWright/ClaimClarity AgentCore path both
  used `~/.agentcore-deployment.json`.
- The A2A ECS path sourced the dashboard's `common.sh` and never overrode
  `MANIFEST_PATH`, so both wrote `~/.trinetra-ecs-express-deployment.json`.

Both teardown scripts *delete the manifest they read*. So deploying the second
of a pair silently overwrote the first's record — leaving real resources running
with nothing left that knew how to remove them. For the ECS pair that means an
orphaned Fargate task **and a share of a load balancer**, billing indefinitely.
The load balancer is the part people forget.

The fix is trivial once seen — distinct defaults, each overridable:

```bash
MANIFEST_PATH_DEFAULT="$HOME/.trinetra-a2a-ecs-express-deployment.json"
MANIFEST_PATH="${TRINETRA_A2A_ECS_MANIFEST:-$MANIFEST_PATH_DEFAULT}"
```

If you write deployment scripts that clean up after themselves, **the cleanup
state is as load-bearing as the deployment state.** Give every path its own, and
check for collisions when you copy a script to make a sibling — which is exactly
how I introduced the second one.

## Where the model credential goes, and where it does not

Trinetra runs on either Amazon Bedrock or the Anthropic API. The credential
handling differs, and one of them has a limitation worth stating plainly.

**No build step ever receives a model credential.** CodeBuild builds an image
with no key baked in. For ECS, the key is injected only when the service is
created or updated — a separate step from the build. The scripts redact it even
in `--dry-run` output.

I also made the provider explicit rather than inferred. The container's config
auto-detects a provider from the environment, which is convenient locally but
means a deployed service's provider is a runtime inference rather than something
you can read off the service definition. So when a key is present the scripts now
pin it:

```python
env = []
key = os.environ.get('ANTHROPIC_API_KEY', '')
if key:
    env.append({'name': 'TRINETRA_MODEL_PROVIDER', 'value': 'anthropic'})
    env.append({'name': 'ANTHROPIC_API_KEY', 'value': key})
```

Conditional on purpose: pinning the provider with no key present would make the
config raise on startup and crash-loop the task.

That snippet also fixes a small security bug. The key was previously
interpolated into the Python source *through the shell*, so a key containing a
quote would have broken out of the string literal. It now travels through the
process environment. I tested with a key containing both quote types.

**Two honest caveats:**

- On ECS the key is a plain environment variable on the service definition.
  Anyone with `ecs:DescribeExpressGatewayService` in your account can read it.
  That is normal for this pattern and fine for a demo — beyond that, move it to
  Secrets Manager and reference it from the container definition's `secrets`
  field instead of `environment`.
- On **Bedrock AgentCore Runtime**, `agentcore deploy --env KEY=VALUE` is the
  only mechanism the AgentCore CLI supports for this. There is no native Secrets
  Manager or SSM Parameter Store integration, so the raw value goes on the
  command line for that one command. That is a real limitation of the tool, and
  I would rather write it down than let someone discover it. If it is
  unacceptable for your account, use Bedrock — there the model calls are
  authorised by the agent's IAM execution role and no key exists to leak.

## What I would tell someone starting tomorrow

**Pick your deployment constraint first.** "Must run from CloudShell" sounds
limiting and turned out to be clarifying — it forced CodeBuild, which removed a
whole class of "works on my machine" problems and made the frontend build
somebody else's job.

**Read the CLI reference for the service you are automating.** Not the overview
page — the parameter list. It cost me twenty minutes and found three bugs.

**Never guess a URL, a hostname, or an ARN that an API will tell you.** The API
knows. `--query` it out.

**Treat teardown state as production state.** An orphaned load balancer bills
quietly for a long time.

**And `--dry-run` everything.** Every script here supports it and prints exactly
what it would create. It is also the only way I could validate any of this
without an AWS account attached — which brings me back to where I started.

## Honest scorecard

**Verified live.** The dashboard path is deployed and serving:

```console
$ curl -s https://tr-f84a1a73e8154b1c88e4d700c96ccb64.ecs.us-east-1.on.aws/api/status
{"status_text":"Anthropic API direct (claude-sonnet-4-5-20250929)","ready":true}

$ curl -s https://tr-f84a1a73e8154b1c88e4d700c96ccb64.ecs.us-east-1.on.aws/api/calibration
Nashik Kumbh stampede, Kalaram Mandir  -> critical  (real deaths: 39)
Prayagraj Maha Kumbh stampede, Sangam  -> critical  (real deaths: 30)
```

That second call is the one I care about. It runs the deterministic crowd
simulator against two documented disasters and requires both to come back
CRITICAL — in the deployed container, not on my laptop. The provider pin came
through correctly, the multi-stage React build is being served, and the deployed
JavaScript bundle hash matches my local build exactly.

**Not verified.** The A2A service, and both Amazon Bedrock AgentCore paths, have
**not** been run against a live account. They are syntax-checked,
shellcheck-clean and dry-runnable, and their parameters come from the command
reference — but unproven is unproven, and I would rather scope the claim than
let one successful deployment vouch for three others.

---

**Live:** <https://tr-f84a1a73e8154b1c88e4d700c96ccb64.ecs.us-east-1.on.aws>

**Code:** <https://github.com/akashtalole/Agents-for-Humans-Hackathon>
(MIT). The deployment path is in `deploy/ecs-express/`, with a full CloudShell
walkthrough in [`deploy/CLOUDSHELL.md`](../../deploy/CLOUDSHELL.md).

Built with the Strands Agents SDK, Amazon ECS Express Mode, AWS CodeBuild,
Amazon ECR, AWS Fargate, AWS CloudShell, and Amazon Bedrock.
