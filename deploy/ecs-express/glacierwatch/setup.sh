#!/usr/bin/env bash
# Build the GlacierWatch web UI image and deploy it to Amazon ECS Express
# Mode - a managed, autoscaled HTTPS service with no cluster, task
# definition, load balancer, or VPC to hand-configure. Idempotent - safe to
# re-run (re-running rebuilds+pushes the image and updates the service in
# place if one already exists).
#
# Usage:
#   ./setup.sh [--yes] [--region REGION] [--dry-run]
#
#   --yes            Skip the confirmation prompt (for unattended/CI use).
#   --region REGION  Override the detected AWS region.
#   --dry-run        Print what would run without touching AWS or Docker.
#
# What it does:
#   1. Confirms before doing anything (creating billable resources).
#   2. Checks AWS identity/region and the AWS CLI version (ECS Express
#      Mode's update command needs AWS CLI >= 2.33.15).
#   3. Creates the two account-global IAM roles ECS Express Mode needs, if
#      they don't already exist (ecsTaskExecutionRole and
#      ecsInfrastructureRoleForExpressServices - shared across any other
#      project in this repo that also deploys this way).
#   4. Creates an ECR repository (if needed), builds
#      Dockerfile.glacierwatch.webapp, and pushes it.
#   5. Creates (first run) or updates (subsequent runs) the
#      "glacierwatch-webui" Express Gateway Service, passing
#      ANTHROPIC_API_KEY from your local environment/.env into the
#      container.
#   6. Writes a small deployment manifest (default
#      ~/.glacierwatch-ecs-express-deployment.json) recording the service
#      ARN, for teardown.sh and future re-runs to read.
#
# COST WARNING: this creates real, billable AWS resources - an ECS Express
# Gateway Service (Fargate compute + a managed load balancer), an ECR
# repository (image storage), and CloudWatch Logs. Run teardown.sh when
# you're done. This is GlacierWatch's first AWS deployment path (unlike
# BidWright/ClaimClarity's existing AgentCore scripts) and, like those, has
# not been exercised against a live AWS account during development - read
# through this script before running it. See README.md in this directory
# for the honest limitations (in particular: minTaskCount/maxTaskCount are
# both pinned to 1, since the API's job store is in-memory per-process).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

SERVICE_NAME="glacierwatch-webui"
ECR_REPO_NAME="glacierwatch-webui"
REGION_OVERRIDE=""
DRY_RUN=0
AUTO_YES=0

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --region) REGION_OVERRIDE="${2:?--region needs a value}"; shift 2 ;;
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
# steps need, like an ECR repo URI) - prints what it would do either way.
capture() {
    if [[ "$DRY_RUN" == "1" ]]; then
        printf '[dry-run] %s\n' "$*" >&2
        printf '%s' "dry-run-placeholder"
    else
        "$@"
    fi
}

log_step "GlacierWatch web UI -> Amazon ECS Express Mode setup"
log_warn "This creates BILLABLE AWS resources (ECS Express Gateway Service, ECR, CloudWatch Logs)."
log_warn "Run teardown.sh when you're done."
if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Continue?" || { log_info "Aborted."; exit 0; }
fi

require_cmd docker
require_python310
check_aws_identity
check_aws_cli_version
REGION="${REGION_OVERRIDE:-$(resolve_region)}"
log_ok "Using region: $REGION"

ensure_repo

if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ -f "$REPO_DIR/.env" ]]; then
    # shellcheck disable=SC1091
    ANTHROPIC_API_KEY=$(grep -E '^ANTHROPIC_API_KEY=' "$REPO_DIR/.env" | head -1 | cut -d= -f2-)
fi
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    log_warn "ANTHROPIC_API_KEY is not set (checked environment and $REPO_DIR/.env)."
    log_warn "The deployed service will start but report 'No credentials found' at /api/status until you set it."
fi

# --- IAM roles (skip creation if these already exist - see common.sh) -----

TASK_EXEC_TRUST='{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}'
INFRA_TRUST='{
  "Version": "2012-10-17",
  "Statement": [{"Sid": "AllowAccessInfrastructureForECSExpressServices", "Effect": "Allow", "Principal": {"Service": "ecs.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}'

log_step "Ensuring required IAM roles exist (account-global - shared with any other project's ECS Express setup)"
ensure_role_exists "ecsTaskExecutionRole" "$TASK_EXEC_TRUST" \
    "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
ensure_role_exists "ecsInfrastructureRoleForExpressServices" "$INFRA_TRUST" \
    "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"

EXECUTION_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole"
INFRASTRUCTURE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsInfrastructureRoleForExpressServices"

# --- ECR: create repo if needed, build, push -------------------------------

log_step "Ensuring ECR repository $ECR_REPO_NAME exists in $REGION"
if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$REGION" >/dev/null 2>&1; then
    log_info "ECR repository already exists."
else
    run aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$REGION" >/dev/null
    log_ok "Created ECR repository $ECR_REPO_NAME"
fi
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}"

log_step "Logging in to ECR"
run bash -c "aws ecr get-login-password --region '$REGION' | docker login --username AWS --password-stdin '${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com'"

log_step "Building $ECR_URI:latest from Dockerfile.glacierwatch.webapp"
run docker build -f "$REPO_DIR/Dockerfile.glacierwatch.webapp" -t "$ECR_URI:latest" "$REPO_DIR"

log_step "Pushing $ECR_URI:latest"
run docker push "$ECR_URI:latest"

# --- ECS Express Gateway Service: create or update -------------------------

PRIMARY_CONTAINER=$(python3 -c "
import json
print(json.dumps({
    'image': '${ECR_URI}:latest',
    'containerPort': 8000,
    'environment': [{'name': 'ANTHROPIC_API_KEY', 'value': '''${ANTHROPIC_API_KEY:-}'''}],
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
        --cpu 1 --memory 2 \
        --health-check-path "/api/status" \
        --scaling-target '{"minTaskCount":1,"maxTaskCount":1}' \
        --monitor-resources \
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
        "repo_dir=$REPO_DIR" \
        "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log_ok "Manifest written to $MANIFEST_PATH"

    log_step "Service status"
    aws ecs describe-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION" || true

    log_info ""
    log_info "URL format: https://${SERVICE_NAME}.ecs.${REGION}.on.aws/"
    log_info "(the service can take a few minutes to reach RUNNING/healthy after first creation)"
else
    log_ok "Dry run complete - nothing was created or pushed."
fi

log_info ""
log_info "Next steps:"
log_info "  - Check status any time:  aws ecs describe-express-gateway-service --service-arn <arn>"
log_info "  - Re-run this script after a code change to build+push+update in place."
log_info "  - Tear everything down:   deploy/ecs-express/glacierwatch/teardown.sh"
