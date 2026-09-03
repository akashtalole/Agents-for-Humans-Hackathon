#!/usr/bin/env bash
# Deploy the BidWright web UI (FastAPI + React, Dockerfile.bidwright.webapp)
# to Amazon ECS Express Mode. Idempotent where AWS lets it be - re-running
# after a failure resumes rather than duplicating resources.
#
# Usage:
#   ./setup.sh [--yes] [--region REGION] [--image-tag TAG] [--dry-run]
#
#   --yes            Skip the confirmation prompt (for unattended/CI use).
#   --region REGION  Override the detected AWS region.
#   --image-tag TAG  Tag to build/push/deploy (default: latest).
#   --dry-run        Print what would run without touching AWS or Docker.
#
# What it does:
#   1. Builds Dockerfile.bidwright.webapp locally (needs Docker) and pushes
#      it to an ECR repository (created if it doesn't exist).
#   2. Ensures the two account-global IAM roles ECS Express Mode needs exist
#      (ecsTaskExecutionRole, ecsInfrastructureRoleForExpressServices) -
#      shared with any other project's ECS Express setup.sh, created once.
#   3. Runs `aws ecs create-express-gateway-service` to stand up a public
#      HTTPS endpoint running the image.
#   4. Writes a manifest (default ~/.ecs-express-bidwright.json) recording
#      the service ARN/name for teardown.sh to read.
#
# COST WARNING: this creates billable AWS resources - an ECS Express Gateway
# Service (Fargate compute + its managed load balancer/gateway), an ECR
# repository (image storage), and CloudWatch Logs. Run teardown.sh when
# you're done with the demo.
#
# NOT EXERCISED AGAINST A LIVE AWS ACCOUNT - see deploy/ecs-express/bidwright/README.md.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

IMAGE_TAG="latest"
REGION_OVERRIDE=""
DRY_RUN=0
AUTO_YES=0
SERVICE_NAME="bidwright-webui"
REPO_NAME="bidwright-webui"

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --region) REGION_OVERRIDE="${2:?--region needs a value}"; shift 2 ;;
        --image-tag) IMAGE_TAG="${2:?--image-tag needs a value}"; shift 2 ;;
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

MANIFEST_PATH="${ECS_EXPRESS_MANIFEST:-$HOME/.ecs-express-bidwright.json}"

log_step "BidWright web UI -> Amazon ECS Express Mode setup"
log_warn "This creates BILLABLE AWS resources (ECS Express Gateway Service,"
log_warn "ECR image storage, CloudWatch Logs). Run teardown.sh when you're done."
if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Continue?" || { log_info "Aborted."; exit 0; }
fi

check_aws_identity
REGION="${REGION_OVERRIDE:-$(resolve_region)}"
log_ok "Using region: $REGION"

require_docker
ensure_repo

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    log_warn "ANTHROPIC_API_KEY is not set in this shell - the deployed service will"
    log_warn "start with no model credentials until you set it and re-run"
    log_warn "'aws ecs update-express-gateway-service' with a --primary-container"
    log_warn "environment block that includes it (see README.md)."
fi

log_step "Ensuring ECR repository '$REPO_NAME' exists in $REGION"
ECR_URI=$(run ensure_ecr_repo "$REPO_NAME" "$REGION")
if [[ "$DRY_RUN" == "1" ]]; then
    ECR_URI="<account>.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"
fi
log_ok "ECR repository: $ECR_URI"

log_step "Building $REPO_NAME:$IMAGE_TAG from Dockerfile.bidwright.webapp (linux/amd64, for Fargate)"
run docker build --platform linux/amd64 -f Dockerfile.bidwright.webapp -t "$ECR_URI:$IMAGE_TAG" .

log_step "Logging in to ECR and pushing the image"
run bash -c "aws ecr get-login-password --region '$REGION' | docker login --username AWS --password-stdin '${ECR_URI%%/*}'"
run docker push "$ECR_URI:$IMAGE_TAG"

log_step "Ensuring account-global IAM roles for ECS Express Mode exist"
run ensure_ecs_express_iam_roles

EXECUTION_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID:-<account>}:role/$ECS_TASK_EXECUTION_ROLE"
INFRA_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID:-<account>}:role/$ECS_INFRA_ROLE"

# --scaling-target defaults to 1/1 (not autoscaled) - see README.md's
# "Honest limitations" section: the job store in bidwright/api.py is an
# in-memory dict per process, so a second concurrently-running task would
# not share job state with the first (a browser polling job status could
# hit either task behind the gateway and get "job not found"). Pass
# --scaling-target minTaskCount=N,maxTaskCount=M yourself if you've changed
# the backend to use shared state (e.g. DynamoDB/Redis) instead.
CONTAINER_ENV="[{\"name\":\"ANTHROPIC_API_KEY\",\"value\":\"${ANTHROPIC_API_KEY:-}\"}]"
PRIMARY_CONTAINER="{\"image\":\"$ECR_URI:$IMAGE_TAG\",\"containerPort\":8000,\"environment\":$CONTAINER_ENV}"

log_step "Checking this script's own manifest for a previously-created service"
# The AWS CLI reference for ECS Express Mode only documents looking a
# service up *by ARN* (--service-arn), not by name - so re-run idempotency
# here relies on the ARN this script itself recorded last time in
# $MANIFEST_PATH, not on querying AWS for "does a service named X exist".
# If you've lost the manifest (a different machine, a deleted file), this
# will create a second, differently-ARN'd service with the same
# --service-name; check the ECS console/CLI by hand before re-running in
# that situation.
PRIOR_ARN=$(manifest_read service_arn 2>/dev/null || true)
EXISTING_ARN=""
if [[ -n "$PRIOR_ARN" ]]; then
    if aws ecs describe-express-gateway-service --service-arn "$PRIOR_ARN" --region "$REGION" >/dev/null 2>&1; then
        EXISTING_ARN="$PRIOR_ARN"
    else
        log_warn "Manifest points at $PRIOR_ARN but it no longer describes successfully - treating as gone, creating fresh."
    fi
fi

if [[ -n "$EXISTING_ARN" ]]; then
    log_info "Service already exists ($EXISTING_ARN) - updating it to the new image instead of creating a duplicate."
    log_info "(Requires AWS CLI >= 2.33.15 for 'aws ecs update-express-gateway-service' - upgrade if this errors as 'unknown command'.)"
    run aws ecs update-express-gateway-service --service-arn "$EXISTING_ARN" \
        --region "$REGION" \
        --primary-container "{\"image\":\"$ECR_URI:$IMAGE_TAG\"}"
    SERVICE_ARN="$EXISTING_ARN"
else
    log_step "Creating Express Gateway Service '$SERVICE_NAME'"
    CREATE_OUTPUT=$(run aws ecs create-express-gateway-service \
        --region "$REGION" \
        --execution-role-arn "$EXECUTION_ROLE_ARN" \
        --infrastructure-role-arn "$INFRA_ROLE_ARN" \
        --primary-container "$PRIMARY_CONTAINER" \
        --service-name "$SERVICE_NAME" \
        --cpu 1 --memory 2 \
        --health-check-path "/api/status" \
        --scaling-target minTaskCount=1,maxTaskCount=1 \
        --monitor-resources \
        --output json)
    if [[ "$DRY_RUN" != "1" ]]; then
        printf '%s\n' "$CREATE_OUTPUT"
        SERVICE_ARN=$(printf '%s' "$CREATE_OUTPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["service"]["serviceArn"])')
    else
        SERVICE_ARN="<dry-run-service-arn>"
    fi
fi

if [[ "$DRY_RUN" != "1" ]]; then
    manifest_write \
        "service_name=$SERVICE_NAME" \
        "service_arn=$SERVICE_ARN" \
        "region=$REGION" \
        "ecr_repo=$REPO_NAME" \
        "ecr_uri=$ECR_URI" \
        "image_tag=$IMAGE_TAG" \
        "repo_dir=$REPO_DIR" \
        "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log_ok "Manifest written to $MANIFEST_PATH"

    log_step "Fetching service URL"
    aws ecs describe-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION"
    log_info ""
    log_info "The URL is printed above (serviceUrl / a similar field in the JSON) -"
    log_info "format: https://$SERVICE_NAME.ecs.$REGION.on.aws/"
else
    log_ok "Dry run complete - nothing was created or pushed."
fi

log_info ""
log_info "Next steps:"
log_info "  - Check status any time: aws ecs describe-express-gateway-service --service-arn $SERVICE_ARN --region $REGION"
log_info "  - Redeploy a new image:  re-run this script (it updates in place)"
log_info "  - Tear everything down:  deploy/ecs-express/bidwright/teardown.sh"
