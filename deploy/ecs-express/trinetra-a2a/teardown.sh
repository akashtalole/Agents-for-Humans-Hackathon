#!/usr/bin/env bash
# Tears down the Trinetra A2A agent deployment. Note that removing this
# service makes Trinetra unreachable to every peer that has its URL
# registered - tell them before you run it, or their next consultation
# simply times out with no explanation.
# Tear down Trinetra's ECS Express Gateway Service and (by default) its
# CodeBuild project + CodeBuild-specific IAM role. Safe by default -
# previews what it's about to destroy and asks first.
#
# Usage:
#   ./teardown.sh [--yes] [--dry-run] [--delete-ecr-repo] [--keep-codebuild]
#
#   --yes               Skip the confirmation prompt (for unattended/CI use).
#   --dry-run           Print what would run without touching AWS.
#   --delete-ecr-repo   Also delete the ECR repository (and every image tag
#                        in it). Off by default - deleting it also destroys
#                        every previously pushed image, not just the latest.
#   --keep-codebuild    Don't delete the CodeBuild project or its
#                        Trinetra-specific IAM role. Off by default (unlike
#                        --delete-ecr-repo) because, unlike the ECR image
#                        history, the CodeBuild project and its role are
#                        single-purpose to this deployment and cheap to
#                        recreate - see setup.sh, which recreates both if
#                        missing.
#
# What this does NOT remove automatically (same spirit as
# deploy/cloudshell/teardown.sh's manual-cleanup list): the two
# account-global IAM roles (ecsTaskExecutionRole,
# ecsInfrastructureRoleForExpressServices) - these may be in use by another
# project's ECS Express deployment in this same account, so this script
# never deletes them.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Reuses the sibling deployment's helper library rather than duplicating it.
# shellcheck source=../trinetra/common.sh
source "$SCRIPT_DIR/../trinetra/common.sh"

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

DRY_RUN=0
AUTO_YES=0
DELETE_ECR_REPO=0
KEEP_CODEBUILD=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --delete-ecr-repo) DELETE_ECR_REPO=1; shift ;;
        --keep-codebuild) KEEP_CODEBUILD=1; shift ;;
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
CODEBUILD_PROJECT=$(manifest_read codebuild_project || true)
CODEBUILD_ROLE=$(manifest_read codebuild_role || true)

[[ -n "$SERVICE_ARN" ]] || die "No service_arn found in $MANIFEST_PATH - nothing to tear down (or set TRINETRA_ECS_MANIFEST to point at the right manifest)."
[[ -n "$REGION" ]] || REGION="$(resolve_region)"

log_step "This will delete:"
log_info "  - ECS Express Gateway Service: $SERVICE_ARN (region $REGION)"
if [[ "$DELETE_ECR_REPO" == "1" ]]; then
    log_info "  - ECR repository: ${ECR_URI:-<unknown - see manifest>} (--delete-ecr-repo passed - ALL image tags in it)"
else
    log_info "  - ECR repository ${ECR_URI:-<unknown>} is NOT deleted (pass --delete-ecr-repo to also remove it)"
fi
if [[ "$KEEP_CODEBUILD" == "1" ]]; then
    log_info "  - CodeBuild project ${CODEBUILD_PROJECT:-<unknown>} and role ${CODEBUILD_ROLE:-<unknown>} are NOT deleted (--keep-codebuild passed)"
else
    log_info "  - CodeBuild project: ${CODEBUILD_PROJECT:-<unknown - see manifest>}"
    log_info "  - CodeBuild IAM role: ${CODEBUILD_ROLE:-<unknown - see manifest>} (Trinetra-specific, not account-global)"
fi
log_info "  - The two account-global IAM roles (ecsTaskExecutionRole,"
log_info "    ecsInfrastructureRoleForExpressServices) are NEVER deleted by this script - remove"
log_info "    them manually via the IAM console/CLI only if certain nothing else uses them."

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

if [[ "$KEEP_CODEBUILD" != "1" ]]; then
    if [[ -n "$CODEBUILD_PROJECT" ]]; then
        log_step "Deleting CodeBuild project $CODEBUILD_PROJECT"
        run aws codebuild delete-project --name "$CODEBUILD_PROJECT" --region "$REGION"
        log_ok "CodeBuild project deleted"
    else
        log_warn "No codebuild_project recorded in $MANIFEST_PATH - skipping. Remove it manually if needed."
    fi
    if [[ -n "$CODEBUILD_ROLE" ]]; then
        log_step "Detaching policies and deleting CodeBuild IAM role $CODEBUILD_ROLE"
        for policy_arn in \
            "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser" \
            "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"; do
            run aws iam detach-role-policy --role-name "$CODEBUILD_ROLE" --policy-arn "$policy_arn" 2>/dev/null || true
        done
        run aws iam delete-role --role-name "$CODEBUILD_ROLE" 2>/dev/null || \
            log_warn "Could not delete role $CODEBUILD_ROLE - it may already be gone, or still have policies attached; check manually with 'aws iam list-attached-role-policies --role-name $CODEBUILD_ROLE'."
        log_ok "CodeBuild IAM role removed (or was already gone)"
    else
        log_warn "No codebuild_role recorded in $MANIFEST_PATH - skipping. Remove it manually if needed."
    fi
fi

if [[ "$DRY_RUN" != "1" ]]; then
    manifest_write "service_arn=" "torn_down_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log_ok "Manifest updated at $MANIFEST_PATH"
else
    log_ok "Dry run complete - nothing was deleted."
fi
