#!/usr/bin/env bash
# Deploy the ClaimClarity web UI (FastAPI + React, one container) to Amazon
# ECS Express Mode - a real, current AWS feature (announced Nov 2025) for
# standing up a single-service, load-balanced, autoscaled HTTPS endpoint
# without hand-building a VPC/ALB/target-group/service/task-definition
# stack yourself.
#
# THESE SCRIPTS HAVE NOT BEEN EXERCISED AGAINST A LIVE AWS ACCOUNT. See
# README.md in this directory for exactly what that means and what to
# expect on a first real run.
#
# Usage:
#   deploy/ecs-express/claimclarity/setup.sh [--yes] [--dry-run] [--region REGION]
#
# Requires ANTHROPIC_API_KEY to be set in the environment (the deployed
# container needs it to call the Anthropic API - see README.md's "Honest
# limitations" for why it's passed as a plain environment variable here,
# not a secret, and what that means).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./common.sh
source "$SCRIPT_DIR/common.sh"

AUTO_YES=0
DRY_RUN=0
REGION_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --region) REGION_OVERRIDE="$2"; shift 2 ;;
        -h|--help)
            cat <<'EOF'
Usage: setup.sh [--yes] [--dry-run] [--region REGION]

  --yes            Skip confirmation prompts (for unattended/CI runs).
  --dry-run        Print what would happen without touching AWS or Docker.
  --region REGION  AWS region to deploy into (default: your configured
                    AWS region, or us-east-1 if none is configured).

Requires: aws CLI (>= 2.33.15 recommended), docker, python3, and
ANTHROPIC_API_KEY set in the environment.
EOF
            exit 0
            ;;
        *) die "Unknown argument: $1 (see --help)" ;;
    esac
done

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[dry-run] $*"
    else
        "$@"
    fi
}

log_step "ClaimClarity - Amazon ECS Express Mode setup"
log_warn "This creates real, billable AWS resources (ECR storage, an Application"
log_warn "Load Balancer, and a running Fargate task, billed while the service exists)."
log_warn "Run teardown.sh when you're done. See README.md for the full cost picture."

[[ -n "${ANTHROPIC_API_KEY:-}" ]] || die "ANTHROPIC_API_KEY is not set. Export it first: export ANTHROPIC_API_KEY=sk-ant-..."

require_cmd aws
require_cmd docker
require_cmd python3
require_min_cli_version
ensure_repo

if [[ "$DRY_RUN" != "1" ]]; then
    check_aws_identity
else
    log_info "[dry-run] would run: aws sts get-caller-identity"
    AWS_ACCOUNT_ID="123456789012"
fi

REGION="${REGION_OVERRIDE:-$(resolve_region)}"
log_ok "Region: $REGION"

confirm "Proceed with deploying ClaimClarity to ECS Express Mode in $REGION?" || { log_info "Aborted."; exit 0; }

# --- IAM roles (idempotent, account-global, shared with the other two
# projects' own deploy/ecs-express/*/setup.sh) --------------------------

log_step "Ensuring required IAM roles exist"
if [[ "$DRY_RUN" != "1" ]]; then
    ensure_ecs_task_execution_role
    ensure_ecs_infrastructure_role
else
    log_info "[dry-run] would ensure IAM roles: $ECS_TASK_EXECUTION_ROLE_NAME, $ECS_INFRA_ROLE_NAME"
fi

EXECUTION_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ECS_TASK_EXECUTION_ROLE_NAME}"
INFRA_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ECS_INFRA_ROLE_NAME}"

# --- ECR repository + image build/push -------------------------------------

ECR_REPO_NAME="claimclarity-webui"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_URI="${ECR_REGISTRY}/${ECR_REPO_NAME}"

log_step "Ensuring ECR repository $ECR_REPO_NAME exists"
if [[ "$DRY_RUN" != "1" ]]; then
    if ! aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$REGION" >/dev/null 2>&1; then
        aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$REGION" >/dev/null
        log_ok "Created ECR repository $ECR_REPO_NAME"
    else
        log_ok "ECR repository $ECR_REPO_NAME already exists - reusing it."
    fi
else
    log_info "[dry-run] would create/reuse ECR repository $ECR_REPO_NAME"
fi

log_step "Building the container image (Dockerfile.claimclarity.webapp)"
run docker build -f Dockerfile.claimclarity.webapp -t "${ECR_URI}:latest" .

log_step "Pushing the image to ECR"
if [[ "$DRY_RUN" != "1" ]]; then
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
fi
run docker push "${ECR_URI}:latest"

# --- ECS Express Gateway Service --------------------------------------------

SERVICE_NAME="claimclarity-webui"

PRIMARY_CONTAINER=$(python3 -c "
import json
print(json.dumps({
    'image': '${ECR_URI}:latest',
    'containerPort': 8000,
    'environment': [{'name': 'ANTHROPIC_API_KEY', 'value': '''${ANTHROPIC_API_KEY}'''}],
}))
")

log_step "Creating ECS Express Gateway Service ($SERVICE_NAME)"
log_warn "Note: minTaskCount/maxTaskCount are both pinned to 1 - see README.md's"
log_warn "'Honest limitations' for why (in-memory per-process job store, not shared"
log_warn "across tasks) before changing that."

if [[ "$DRY_RUN" != "1" ]]; then
    CREATE_OUTPUT=$(aws ecs create-express-gateway-service \
        --execution-role-arn "$EXECUTION_ROLE_ARN" \
        --infrastructure-role-arn "$INFRA_ROLE_ARN" \
        --primary-container "$PRIMARY_CONTAINER" \
        --service-name "$SERVICE_NAME" \
        --cpu 1 --memory 2 \
        --health-check-path "/api/status" \
        --scaling-target '{"minTaskCount":1,"maxTaskCount":1}' \
        --monitor-resources \
        --region "$REGION" \
        --output json)
    SERVICE_ARN=$(printf '%s' "$CREATE_OUTPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("service",{}).get("serviceArn") or d.get("serviceArn",""))')
    [[ -n "$SERVICE_ARN" ]] || { printf '%s\n' "$CREATE_OUTPUT" >&2; die "Could not parse serviceArn from create-express-gateway-service output - see raw output above."; }

    manifest_write "service_arn=$SERVICE_ARN" "service_name=$SERVICE_NAME" \
        "region=$REGION" "ecr_repo=$ECR_REPO_NAME" "account_id=$AWS_ACCOUNT_ID"

    log_ok "Created service: $SERVICE_ARN"
    log_info "Recorded in $MANIFEST_PATH for teardown.sh."
    log_info "Public URL (once the service finishes provisioning - can take a few minutes):"
    log_info "  https://${SERVICE_NAME}.ecs.${REGION}.on.aws/"
    log_info "Check status with:"
    log_info "  aws ecs describe-express-gateway-service --service-arn $SERVICE_ARN --region $REGION"
else
    log_info "[dry-run] would run: aws ecs create-express-gateway-service --service-name $SERVICE_NAME ..."
fi

log_ok "Done."
