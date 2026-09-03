#!/usr/bin/env bash
# Tear down the GlacierWatch web UI's ECS Express Gateway Service. Safe by
# default - previews what it's about to destroy and asks first.
#
# Usage:
#   ./teardown.sh [--yes] [--dry-run] [--delete-ecr-repo]
#
#   --yes               Skip the confirmation prompt (for unattended/CI use).
#   --dry-run           Print what would run without touching AWS.
#   --delete-ecr-repo   Also delete the ECR repository (and every image tag
#                        in it). Off by default - deleting it also destroys
#                        every previously pushed image, not just the latest.
#
# What it does NOT remove automatically (same spirit as
# deploy/cloudshell/teardown.sh's manual-cleanup list): the two IAM roles
# (ecsTaskExecutionRole, ecsInfrastructureRoleForExpressServices) - these are
# account-global and may be in use by another project's ECS Express
# deployment in this same account, so this script never deletes them. The
# ECR repository is also left in place unless you pass --delete-ecr-repo.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

DRY_RUN=0
AUTO_YES=0
DELETE_ECR_REPO=0

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --delete-ecr-repo) DELETE_ECR_REPO=1; shift ;;
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

require_cmd aws
check_aws_identity

SERVICE_ARN=$(manifest_read service_arn || true)
REGION=$(manifest_read region || true)
ECR_URI=$(manifest_read ecr_repo_uri || true)

[[ -n "$SERVICE_ARN" ]] || die "No service_arn found in $MANIFEST_PATH - nothing to tear down (or set GLACIERWATCH_ECS_MANIFEST to point at the right manifest)."
[[ -n "$REGION" ]] || REGION="$(resolve_region)"

log_step "This will delete:"
log_info "  - ECS Express Gateway Service: $SERVICE_ARN (region $REGION)"
if [[ "$DELETE_ECR_REPO" == "1" ]]; then
    log_info "  - ECR repository: ${ECR_URI:-<unknown - see manifest>} (--delete-ecr-repo passed - ALL image tags in it)"
else
    log_info "  - ECR repository ${ECR_URI:-<unknown>} is NOT deleted (pass --delete-ecr-repo to also remove it)"
fi
log_info "  - The two IAM roles (ecsTaskExecutionRole, ecsInfrastructureRoleForExpressServices) are"
log_info "    NEVER deleted by this script - they're account-global and may be shared with another"
log_info "    project's ECS Express deployment. Remove them manually via the IAM console/CLI if you"
log_info "    are certain nothing else in this account uses them."

if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Proceed with deletion?" || { log_info "Aborted - nothing deleted."; exit 0; }
fi

log_step "Deleting Express Gateway Service"
run aws ecs delete-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION"
log_ok "Delete requested (the service and its managed infrastructure are torn down asynchronously - check with 'aws ecs describe-express-gateway-service --service-arn $SERVICE_ARN' if you want to confirm it finished)."

if [[ "$DELETE_ECR_REPO" == "1" ]]; then
    if [[ -n "$ECR_URI" ]]; then
        REPO_NAME="${ECR_URI##*/}"
        log_step "Deleting ECR repository $REPO_NAME and all its images"
        run aws ecr delete-repository --repository-name "$REPO_NAME" --region "$REGION" --force
        log_ok "ECR repository deleted"
    else
        log_warn "No ecr_repo_uri recorded in $MANIFEST_PATH - skipping ECR deletion. Remove it manually if needed."
    fi
fi

if [[ "$DRY_RUN" != "1" ]]; then
    manifest_write "service_arn=" "torn_down_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log_ok "Manifest updated at $MANIFEST_PATH"
else
    log_ok "Dry run complete - nothing was deleted."
fi
