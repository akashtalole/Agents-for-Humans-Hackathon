#!/usr/bin/env bash
# Build the Trinetra web UI image on AWS CodeBuild (no local Docker needed -
# runnable entirely from AWS CloudShell) and deploy it to Amazon ECS Express
# Mode - a managed, autoscaled HTTPS service with no cluster, task
# definition, load balancer, or VPC to hand-configure. Idempotent - safe to
# re-run (re-running triggers a fresh CodeBuild build and updates the
# service in place if one already exists).
#
# This is deliberately different from deploy/ecs-express/glacierwatch/'s
# setup.sh, which builds and pushes the image with a local `docker build` -
# that requires Docker running wherever you invoke it, which CloudShell
# doesn't have. This script instead has AWS CodeBuild do the build, the same
# reasoning deploy/cloudshell/'s AgentCore path already uses.
#
# Usage:
#   ./setup.sh [--yes] [--region REGION] [--branch BRANCH] [--dry-run]
#
#   --yes            Skip the confirmation prompt (for unattended/CI use).
#   --region REGION  Override the detected AWS region.
#   --branch BRANCH  Git branch/ref for CodeBuild to build from (default:
#                     the currently checked-out branch in this repo).
#   --dry-run        Print what would run without touching AWS.
#
# What it does:
#   1. Confirms before doing anything (creating billable resources).
#   2. Checks AWS identity/region and the AWS CLI version.
#   3. Creates the two account-global IAM roles ECS Express Mode needs (if
#      they don't already exist), plus a Trinetra-specific CodeBuild
#      service role (ECR push + CloudWatch Logs write).
#   4. Creates an ECR repository if needed.
#   5. Creates or updates a CodeBuild project (source: this repo's public
#      GitHub URL, at --branch) and starts a build - CodeBuild builds
#      Dockerfile.trinetra.webapp and pushes it to ECR (see buildspec.yml
#      in this directory). Polls until the build finishes, printing a
#      CloudWatch Logs pointer on failure. CodeBuild never sees
#      ANTHROPIC_API_KEY or any model credential - see buildspec.yml's own
#      comment on why.
#   6. Creates (first run) or updates (subsequent runs) the
#      "trinetra-webui" Express Gateway Service, passing ANTHROPIC_API_KEY
#      and (if set) THINGSBOARD_URL/USERNAME/PASSWORD/API_KEY and
#      TRINETRA_WEBHOOK_SECRET from your local environment/.env into the
#      container as runtime environment variables - a separate step from
#      the CodeBuild image build above. Re-running this after editing .env
#      updates the running service's environment too, not just the image.
#   7. Writes a deployment manifest (default
#      ~/.trinetra-ecs-express-deployment.json) recording the service ARN
#      and CodeBuild project name, for teardown.sh and future re-runs.
#
# COST WARNING: this creates real, billable AWS resources - CodeBuild build
# minutes, an ECS Express Gateway Service (Fargate compute + a managed load
# balancer), an ECR repository, and CloudWatch Logs. Run teardown.sh when
# you're done. Nothing here has been exercised against a live AWS account
# during development - read through this script before running it, and
# watch the CodeBuild build's own logs closely on the first run. See
# README.md in this directory for a troubleshooting note on a one-time
# per-account/region GitHub source-credentials prerequisite CodeBuild may
# need before it can clone a GitHub source for the first time.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

SERVICE_NAME="trinetra-webui"
ECR_REPO_NAME="trinetra-webui"
CODEBUILD_PROJECT_NAME="trinetra-webui-build"
CODEBUILD_ROLE_NAME="trinetra-codebuild-webui-role"
REGION_OVERRIDE=""
BRANCH_OVERRIDE=""
DRY_RUN=0
AUTO_YES=0

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --region) REGION_OVERRIDE="${2:?--region needs a value}"; shift 2 ;;
        --branch) BRANCH_OVERRIDE="${2:?--branch needs a value}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done
export AUTO_YES

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

# Runs a command and captures stdout even in --dry-run (for values later
# steps need, like a build ID or an ECR repo URI) - prints what it would do
# either way.
capture() {
    if [[ "$DRY_RUN" == "1" ]]; then
        printf '[dry-run] %s\n' "$*" >&2
        printf '%s' "dry-run-placeholder"
    else
        "$@"
    fi
}

log_step "Trinetra web UI -> AWS CodeBuild + Amazon ECS Express Mode setup"
log_warn "This creates BILLABLE AWS resources (CodeBuild build minutes, ECS Express"
log_warn "Gateway Service, ECR, CloudWatch Logs). Run teardown.sh when you're done."
if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Continue?" || { log_info "Aborted."; exit 0; }
fi

require_cmd git
require_python310
check_aws_identity
check_aws_cli_version
REGION="${REGION_OVERRIDE:-$(resolve_region)}"
log_ok "Using region: $REGION"

ensure_repo

BRANCH="${BRANCH_OVERRIDE:-$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
log_ok "CodeBuild will build from branch: $BRANCH (push your changes first if you just edited something)"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ -f "$REPO_DIR/.env" ]]; then
    # shellcheck disable=SC1091
    ANTHROPIC_API_KEY=$(grep -E '^ANTHROPIC_API_KEY=' "$REPO_DIR/.env" | head -1 | cut -d= -f2-)
fi
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    log_warn "ANTHROPIC_API_KEY is not set (checked environment and $REPO_DIR/.env)."
    log_warn "The deployed service will start but report 'No credentials found' at /api/status until you set it."
fi

# Same pattern as ANTHROPIC_API_KEY above, for the optional live-ThingsBoard
# integration (Kshetra Netra's live signals, the alarm webhook, Anukaran
# Netra's seeding) and the webhook's shared secret - see TRINETRA.md's
# Kshetra Netra / Anukaran Netra sections. All optional: unset means those
# features report "not configured" rather than failing, same as locally.
for _var in THINGSBOARD_URL THINGSBOARD_USERNAME THINGSBOARD_PASSWORD THINGSBOARD_API_KEY TRINETRA_WEBHOOK_SECRET; do
    if [[ -z "${!_var:-}" ]] && [[ -f "$REPO_DIR/.env" ]]; then
        # shellcheck disable=SC1091
        printf -v "$_var" '%s' "$(grep -E "^${_var}=" "$REPO_DIR/.env" | head -1 | cut -d= -f2-)"
    fi
done
unset _var
if [[ -z "${THINGSBOARD_USERNAME:-}${THINGSBOARD_API_KEY:-}" ]]; then
    log_warn "No THINGSBOARD_USERNAME/PASSWORD or THINGSBOARD_API_KEY set - live ThingsBoard features will report 'not configured' on the deployed service, same as they do locally without credentials."
fi
if [[ -z "${TRINETRA_WEBHOOK_SECRET:-}" ]]; then
    log_warn "TRINETRA_WEBHOOK_SECRET is not set - /api/webhooks/thingsboard-alarm will reject every request (503) on the deployed service until it is."
fi

# --- IAM roles --------------------------------------------------------

TASK_EXEC_TRUST='{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}'
INFRA_TRUST='{
  "Version": "2012-10-17",
  "Statement": [{"Sid": "AllowAccessInfrastructureForECSExpressServices", "Effect": "Allow", "Principal": {"Service": "ecs.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}'
CODEBUILD_TRUST='{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "codebuild.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}'

log_step "Ensuring required IAM roles exist"
log_info "(ecsTaskExecutionRole / ecsInfrastructureRoleForExpressServices are account-global -"
log_info " shared with any other project's ECS Express setup; $CODEBUILD_ROLE_NAME is Trinetra-specific)"
ensure_role_exists "ecsTaskExecutionRole" "$TASK_EXEC_TRUST" \
    "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
ensure_role_exists "ecsInfrastructureRoleForExpressServices" "$INFRA_TRUST" \
    "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
# Two policies on the same role - ensure_role_exists is safe to call twice
# for the same role_name (it only creates the role on the first call, then
# just attaches whichever policy_arn it was given, idempotently).
ensure_role_exists "$CODEBUILD_ROLE_NAME" "$CODEBUILD_TRUST" \
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
ensure_role_exists "$CODEBUILD_ROLE_NAME" "$CODEBUILD_TRUST" \
    "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"

EXECUTION_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole"
INFRASTRUCTURE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsInfrastructureRoleForExpressServices"
CODEBUILD_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${CODEBUILD_ROLE_NAME}"

if [[ "$DRY_RUN" != "1" ]]; then
    log_info "Waiting a few seconds for IAM role propagation..."
    sleep 8
fi

# --- ECR: create repo if needed --------------------------------------------

log_step "Ensuring ECR repository $ECR_REPO_NAME exists in $REGION"
if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$REGION" >/dev/null 2>&1; then
    log_info "ECR repository already exists."
else
    run aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$REGION" >/dev/null
    log_ok "Created ECR repository $ECR_REPO_NAME"
fi
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}"

# --- CodeBuild: create/update the project, then build ----------------------

CODEBUILD_SOURCE="{\"type\":\"GITHUB\",\"location\":\"$REPO_URL\",\"buildspec\":\"deploy/ecs-express/trinetra/buildspec.yml\"}"
CODEBUILD_ENV="{\"type\":\"LINUX_CONTAINER\",\"image\":\"aws/codebuild/standard:7.0\",\"computeType\":\"BUILD_GENERAL1_SMALL\",\"privilegedMode\":true,\"environmentVariables\":[{\"name\":\"ECR_REPO_URI\",\"value\":\"$ECR_URI\"},{\"name\":\"AWS_ACCOUNT_ID\",\"value\":\"$AWS_ACCOUNT_ID\"}]}"

if aws codebuild batch-get-projects --names "$CODEBUILD_PROJECT_NAME" --region "$REGION" \
        --query "projects[0].name" --output text 2>/dev/null | grep -qx "$CODEBUILD_PROJECT_NAME"; then
    log_step "Updating existing CodeBuild project '$CODEBUILD_PROJECT_NAME'"
    run aws codebuild update-project \
        --name "$CODEBUILD_PROJECT_NAME" \
        --source "$CODEBUILD_SOURCE" \
        --source-version "$BRANCH" \
        --environment "$CODEBUILD_ENV" \
        --service-role "$CODEBUILD_ROLE_ARN" \
        --region "$REGION" >/dev/null
else
    log_step "Creating CodeBuild project '$CODEBUILD_PROJECT_NAME'"
    run aws codebuild create-project \
        --name "$CODEBUILD_PROJECT_NAME" \
        --source "$CODEBUILD_SOURCE" \
        --source-version "$BRANCH" \
        --artifacts '{"type":"NO_ARTIFACTS"}' \
        --environment "$CODEBUILD_ENV" \
        --service-role "$CODEBUILD_ROLE_ARN" \
        --region "$REGION" >/dev/null
fi
log_ok "CodeBuild project ready"

log_step "Starting CodeBuild build (branch: $BRANCH)"
BUILD_ID=$(capture aws codebuild start-build --project-name "$CODEBUILD_PROJECT_NAME" --region "$REGION" \
    --query "build.id" --output text)

if [[ "$DRY_RUN" != "1" ]]; then
    log_info "Build ID: $BUILD_ID"
    log_info "Polling for completion (builds a Docker image - can take several minutes on first run)..."
    while true; do
        BUILD_INFO=$(aws codebuild batch-get-builds --ids "$BUILD_ID" --region "$REGION" \
            --query "builds[0].[buildStatus,currentPhase]" --output text)
        STATUS=$(printf '%s' "$BUILD_INFO" | cut -f1)
        PHASE=$(printf '%s' "$BUILD_INFO" | cut -f2)
        log_info "  status=$STATUS phase=$PHASE"
        case "$STATUS" in
            SUCCEEDED) break ;;
            FAILED|FAULT|STOPPED|TIMED_OUT)
                LOG_GROUP=$(aws codebuild batch-get-builds --ids "$BUILD_ID" --region "$REGION" --query "builds[0].logs.groupName" --output text)
                LOG_STREAM=$(aws codebuild batch-get-builds --ids "$BUILD_ID" --region "$REGION" --query "builds[0].logs.streamName" --output text)
                log_error "Build $STATUS. View logs with:"
                log_error "  aws logs tail '$LOG_GROUP' --log-stream-names '$LOG_STREAM' --region $REGION"
                die "CodeBuild build did not succeed - fix the issue and re-run this script."
                ;;
            *) sleep 15 ;;
        esac
    done
    log_ok "Build succeeded - ${ECR_URI}:latest pushed to ECR"
else
    log_ok "[dry-run] Would poll build $BUILD_ID until completion."
fi

# --- ECS Express Gateway Service: create or update -------------------------

PRIMARY_CONTAINER=$(
    ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    THINGSBOARD_URL="${THINGSBOARD_URL:-}" \
    THINGSBOARD_USERNAME="${THINGSBOARD_USERNAME:-}" \
    THINGSBOARD_PASSWORD="${THINGSBOARD_PASSWORD:-}" \
    THINGSBOARD_API_KEY="${THINGSBOARD_API_KEY:-}" \
    TRINETRA_WEBHOOK_SECRET="${TRINETRA_WEBHOOK_SECRET:-}" \
    ECR_URI="$ECR_URI" python3 -c "
import json, os

env = []
key = os.environ.get('ANTHROPIC_API_KEY', '')
if key:
    # Pinned explicitly rather than relying on config.py's auto-detection, so
    # the deployed service's provider is auditable from the service definition
    # instead of inferred at runtime. Only set when a key actually exists - a
    # pin with no key makes get_model() raise on startup.
    env.append({'name': 'TRINETRA_MODEL_PROVIDER', 'value': 'anthropic'})
    env.append({'name': 'ANTHROPIC_API_KEY', 'value': key})

# Optional live-ThingsBoard integration - each one only added if actually
# set, so an unconfigured deploy behaves exactly like an unconfigured local
# run (an honest 'not configured', never a startup failure).
for name in ('THINGSBOARD_URL', 'THINGSBOARD_USERNAME', 'THINGSBOARD_PASSWORD',
             'THINGSBOARD_API_KEY', 'TRINETRA_WEBHOOK_SECRET'):
    value = os.environ.get(name, '')
    if value:
        env.append({'name': name, 'value': value})

print(json.dumps({
    'image': os.environ['ECR_URI'] + ':latest',
    'containerPort': 8000,
    'environment': env,
}))
")

EXISTING_ARN=$(manifest_read service_arn || true)

if [[ -n "$EXISTING_ARN" ]] && aws ecs describe-express-gateway-service --service-arn "$EXISTING_ARN" --region "$REGION" >/dev/null 2>&1; then
    log_step "Updating existing Express Gateway Service ($EXISTING_ARN) with the new image"
    run aws ecs update-express-gateway-service \
        --service-arn "$EXISTING_ARN" \
        --primary-container "{\"image\":\"${ECR_URI}:latest\"}" \
        --region "$REGION"
    SERVICE_ARN="$EXISTING_ARN"
else
    log_step "Creating Express Gateway Service '$SERVICE_NAME'"
    log_info "minTaskCount=1, maxTaskCount=1 - see README.md's Honest limitations for why."
    CREATE_OUTPUT=$(capture aws ecs create-express-gateway-service \
        --execution-role-arn "$EXECUTION_ROLE_ARN" \
        --infrastructure-role-arn "$INFRASTRUCTURE_ROLE_ARN" \
        --primary-container "$PRIMARY_CONTAINER" \
        --service-name "$SERVICE_NAME" \
        --cpu 1024 --memory 2048 \
        --health-check-path "/api/status" \
        --scaling-target '{"minTaskCount":1,"maxTaskCount":1}' \
        --region "$REGION")
    if [[ "$DRY_RUN" != "1" ]]; then
        SERVICE_ARN=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['service']['serviceArn'])" "$CREATE_OUTPUT" 2>/dev/null || echo "")
        [[ -n "$SERVICE_ARN" ]] || { log_error "Could not parse serviceArn from create-express-gateway-service output:"; printf '%s\n' "$CREATE_OUTPUT" >&2; die "See the raw output above."; }
    else
        SERVICE_ARN="dry-run-placeholder"
    fi
fi

if [[ "$DRY_RUN" != "1" ]]; then
    manifest_write \
        "service_arn=$SERVICE_ARN" \
        "service_name=$SERVICE_NAME" \
        "region=$REGION" \
        "ecr_repo_uri=$ECR_URI" \
        "codebuild_project=$CODEBUILD_PROJECT_NAME" \
        "codebuild_role=$CODEBUILD_ROLE_NAME" \
        "repo_dir=$REPO_DIR" \
        "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log_ok "Manifest written to $MANIFEST_PATH"

    log_step "Service status"
    aws ecs describe-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION" || true

    log_info ""
    SERVICE_URL=$(describe_service_url "$SERVICE_ARN" "$REGION")
    if [[ -n "$SERVICE_URL" ]]; then
        log_ok "Service URL: $SERVICE_URL"
        manifest_write "service_url=$SERVICE_URL"
    else
        log_warn "No public ingress endpoint reported yet - the service is still provisioning."
        log_info "Read it later with:"
        log_info "  aws ecs describe-express-gateway-service --service-arn $SERVICE_ARN --region $REGION \\"
        log_info "    --query 'service.activeConfigurations[].ingressPaths[?accessType==\`PUBLIC\`].endpoint' --output text"
    fi
    log_info "(the service can take a few minutes to reach RUNNING/healthy after first creation)"
else
    log_ok "Dry run complete - nothing was created, built, or pushed."
fi

log_info ""
log_info "Next steps:"
log_info "  - Check status any time:  aws ecs describe-express-gateway-service --service-arn <arn>"
log_info "  - Re-run this script after a code change (git push it first!) to rebuild via"
log_info "    CodeBuild and update the service in place."
log_info "  - Tear everything down:   deploy/ecs-express/trinetra/teardown.sh"
