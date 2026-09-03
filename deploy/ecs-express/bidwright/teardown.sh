#!/usr/bin/env bash
# Tear down what deploy/ecs-express/bidwright/setup.sh created. Safe by
# default: previews what will be destroyed and asks before doing anything,
# unless --yes is passed.
#
# Usage:
#   ./teardown.sh [--yes] [--dry-run] [--delete-ecr]
#
#   --yes          Skip the confirmation prompt (for unattended/CI use).
#   --dry-run      Print what would run without touching AWS.
#   --delete-ecr   Also delete the ECR repository (and every image in it).
#                  Off by default - the repo has little ongoing cost sitting
#                  idle, and deleting it destroys every pushed image tag.
#
# What this does NOT do: it never deletes the two account-global IAM roles
# (ecsTaskExecutionRole, ecsInfrastructureRoleForExpressServices) - those are
# shared with any other project's ECS Express deployment and safe to leave
# in place. It prints a manual-cleanup checklist for them and for CloudWatch
# Logs at the end, same spirit as deploy/cloudshell/teardown.sh.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

DRY_RUN=0
AUTO_YES=0
DELETE_ECR=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --delete-ecr) DELETE_ECR=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done
export AUTO_YES

MANIFEST_PATH="${ECS_EXPRESS_MANIFEST:-$HOME/.ecs-express-bidwright.json}"

if [[ ! -s "$MANIFEST_PATH" ]]; then
    die "No manifest at $MANIFEST_PATH - nothing recorded to tear down (or setup.sh never ran, or ECS_EXPRESS_MANIFEST points elsewhere)."
fi

check_aws_identity

SERVICE_ARN="$(manifest_read service_arn 2>/dev/null || true)"
SERVICE_NAME="$(manifest_read service_name 2>/dev/null || true)"
REGION="$(manifest_read region 2>/dev/null || true)"
REGION="${REGION:-$(resolve_region)}"
ECR_REPO="$(manifest_read ecr_repo 2>/dev/null || true)"

[[ -n "$SERVICE_ARN" ]] || die "Manifest at $MANIFEST_PATH has no service_arn recorded - nothing to destroy."

log_step "This will destroy:"
log_info " - ECS Express Gateway Service: ${SERVICE_NAME:-$SERVICE_ARN} ($SERVICE_ARN)"
if [[ "$DELETE_ECR" == "1" && -n "$ECR_REPO" ]]; then
    log_info " - ECR repository (and all images in it): $ECR_REPO"
else
    log_info " - ECR repository '$ECR_REPO' is kept (pass --delete-ecr to remove it too)"
fi

if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Proceed with destroying these resources?" || { log_info "Aborted."; exit 0; }
fi

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

log_step "Deleting Express Gateway Service"
if run aws ecs delete-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION"; then
    log_ok "Service deletion requested."
else
    log_error "Failed to delete the service - check the output above (it may already be gone)."
fi

if [[ "$DELETE_ECR" == "1" && -n "$ECR_REPO" ]]; then
    log_step "Deleting ECR repository '$ECR_REPO'"
    run aws ecr delete-repository --repository-name "$ECR_REPO" --region "$REGION" --force
fi

if [[ "$DRY_RUN" != "1" ]]; then
    rm -f "$MANIFEST_PATH"
    log_ok "Removed manifest ($MANIFEST_PATH)."
fi

cat <<EOF

==> Manual cleanup checklist (read-only commands - nothing below deletes anything)

Not removed by this script, since they're either account-global and shared
with other projects' ECS Express deployments, or cost ~nothing sitting idle:

  The two account-global IAM roles (shared - do not delete unless no other
  project's ECS Express deployment is using them):
    aws iam get-role --role-name ecsTaskExecutionRole
    aws iam get-role --role-name ecsInfrastructureRoleForExpressServices

  CloudWatch Log groups for this service:
    aws logs describe-log-groups --region $REGION --log-group-name-prefix /ecs --query "logGroups[].logGroupName" --output table
EOF

if [[ "$DELETE_ECR" != "1" ]]; then
    cat <<EOF

  ECR repository (kept - re-run with --delete-ecr to remove it, or by hand):
    aws ecr describe-repositories --repository-names ${ECR_REPO:-bidwright-webui} --region $REGION
    aws ecr delete-repository --repository-name ${ECR_REPO:-bidwright-webui} --region $REGION --force
EOF
fi
