# Deploying Trinetra as an A2A agent on Amazon ECS Express Mode

Publishes Trinetra as an [Agent2Agent](https://a2a-protocol.org/) agent that
third-party agents can discover and call, on [Amazon ECS Express
Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)
— a managed Fargate service that provisions its own load balancer, TLS
certificate, public HTTPS URL and autoscaling from three inputs: a container
image, a task execution role, and an infrastructure role.

The image is built by **AWS CodeBuild**, not locally, so the whole path runs
from AWS CloudShell with no Docker daemon — the same reasoning as the sibling
[`../trinetra/`](../trinetra/) dashboard deployment and
[`../../cloudshell/`](../../cloudshell/)'s AgentCore path.

```bash
./setup.sh --dry-run          # see what it would do, touching nothing
./setup.sh                    # deploy
./teardown.sh                 # remove the service, ECR repo and CodeBuild project
```

## Read this before pointing it at the internet

This is a **machine-facing** surface. The dashboard next door is for a control
room behind whatever access control NTKMA puts in front of it; this one is
designed to be called by agents you do not operate.

- **ECS Express Mode gives you a public HTTPS URL, not authentication.** As
  written, `setup.sh` creates a service with a `PUBLIC` ingress path and no
  authorization on it. Anyone who finds the URL can call the agent and spend
  your model budget. Before any real deployment, either put the service behind
  a private ingress and reach it over PrivateLink/VPC peering, or add
  authentication and declare it in the agent card's `security` field. Trinetra
  does not ship an opinion about which, because that depends on who NTKMA
  actually wants to federate with.
- **Nothing here executes an action.** Every skill in the published card
  returns decision support. No Trinetra reply closes a gate, dispatches a unit,
  or authorises anything, and the card says so in its own description. A peer
  treating a reply as an instruction has misread it.
- **The incident-command flow is deliberately NOT exposed over A2A.**
  Reconciling live hazards against a finite responder pool is a decision made
  inside one authority's control room with a named human accountable for it.
  It is not a thing to answer for an anonymous caller over a network. See
  `trinetra/a2a/server.py` for the declared skill list.
- **CodeBuild never sees a model credential.** The built image has no key baked
  in; `ANTHROPIC_API_KEY` is injected only when the Express service is created
  or updated, a separate step from the build. Same principle as every other
  deploy path in this repo.

## Why this deploys in two phases

An A2A agent card advertises the URL peers should call back on. A container has
no way to know the address a load balancer answers on, so:

1. **Create** the Express service from the built image.
2. **Discover** the real endpoint. Express Mode returns it in
   `service.activeConfigurations[].ingressPaths[]`, each entry tagged `PUBLIC`
   or `PRIVATE`. `setup.sh` polls for it (it is not published the instant the
   service is created).
3. **Update** the service with `TRINETRA_A2A_PUBLIC_URL` set to that endpoint,
   so `server_trinetra_a2a.py` publishes a card advertising the address peers
   can actually reach.

**Do not shortcut step 2 by guessing a hostname from the service name.** A card
that advertises a wrong URL is worse than one that advertises none: a peer will
resolve it, fail, and have no way to tell a bad address from a service that is
merely down. An earlier version of the sibling dashboard script printed a
guessed `https://<service>.ecs.<region>.on.aws/` pattern; that has been replaced
with a real `describe-express-gateway-service` query in
[`../trinetra/common.sh`](../trinetra/common.sh)'s `describe_service_url`.

## What gets created

| Resource | Name | Notes |
|---|---|---|
| ECR repository | `trinetra-a2a` | holds the built image |
| CodeBuild project | `trinetra-a2a-build` | builds `Dockerfile.trinetra.a2a` via [`buildspec.yml`](buildspec.yml) |
| CodeBuild service role | `trinetra-codebuild-a2a-role` | ECR push + CloudWatch Logs write |
| ECS Express service | `trinetra-a2a` | Fargate + managed ALB + HTTPS, port 9100 |
| IAM roles (account-global) | `ecsTaskExecutionRole`, `ecsInfrastructureRoleForExpressServices` | shared with every Express service in the account; **never deleted** by `teardown.sh` |
| Manifest | `~/.trinetra-a2a-ecs-express-deployment.json` | separate from the dashboard's, so the two deployments never clobber each other |

Health checks hit `/.well-known/agent-card.json` — the card is a plain `GET`
that returns 200 when the agent is up, so it doubles as a liveness probe with
no extra endpoint to maintain.

## Verifying a deployment

```bash
SERVICE_URL=$(aws ecs describe-express-gateway-service \
  --service-arn "$(python3 -c 'import json;print(json.load(open("'"$HOME"'/.trinetra-a2a-ecs-express-deployment.json"))["service_arn"])')" \
  --query 'service.activeConfigurations[].ingressPaths[?accessType==`PUBLIC`].endpoint' \
  --output text)

curl "https://$SERVICE_URL/.well-known/agent-card.json" | python3 -m json.tool
```

The card's `url` field should be the same HTTPS address you just curled. If it
is a `0.0.0.0` or container-internal address, phase 2 did not complete — re-run
`./setup.sh`, which is idempotent and will re-apply it.

To let another agent use Trinetra, give its operator that agent-card URL. To let
Trinetra call *them*, add an entry to
[`trinetra/data/a2a_peers.json`](../../../trinetra/data/a2a_peers.json) — the
allowlist; Trinetra will not call a URL that is not in it.

## Honest limitations

- **Nothing here has been run against a live AWS account.** The scripts are
  syntax-checked, shellcheck-clean, and dry-runnable, and the CLI parameters
  are taken from the AWS CLI command reference — but no deployment has actually
  been performed. Read `setup.sh` before running it and watch the first
  CodeBuild build's logs closely.
- **`minTaskCount=1, maxTaskCount=1`.** Fixed at one task, matching the sibling
  deployment. The A2A server holds task state in memory, so scaling out would
  need a shared `TaskStore` (the Strands `A2AServer` constructor accepts one)
  before more than one replica is correct. Raising the max without doing that
  would produce intermittent "task not found" errors as requests land on
  different replicas.
- **No authentication, as shipped.** See the security section above.
- **`setup.sh` is derived from the sibling dashboard script** rather than
  sharing its body, so the two duplicate a few hundred lines of CodeBuild and
  IAM bootstrapping. They share `common.sh` but not the main flow. A fix would
  be to parameterise one script over both services; that refactor was not worth
  the risk of breaking a working deployment path in the same change that
  introduced this one.
