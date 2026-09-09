#!/usr/bin/env bash
# Tear down everything deploy/trinetra/setup.sh created. Safe by default:
# previews what will be destroyed and asks before doing anything, unless
# --yes is passed.
#
# Usage:
#   ./teardown.sh [--yes] [--dry-run] [--keep-ecr]
#
#   --yes          Skip confirmation prompts (for unattended/CI use).
#   --dry-run      Pass --dry-run through to `agentcore destroy` (preview only).
#   --keep-ecr     Don't delete the ECR repository (kept by default deletes it,
#                  since image storage is the main ongoing cost left behind).
#
# What this does NOT do: see deploy/cloudshell/teardown.sh's comment block -
# same caveats apply (IAM roles, CodeBuild project, S3 build-artifact bucket
# are not removed automatically; this script prints a manual-cleanup
# checklist at the end instead of guessing at what's safe to delete).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

DRY_RUN=0
AUTO_YES=0
DELETE_ECR=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --keep-ecr) DELETE_ECR=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done
export AUTO_YES

ensure_repo

if [[ ! -d .venv ]]; then
    die "No .venv found in $REPO_DIR - nothing to tear down from here (or setup.sh never ran)."
fi
# shellcheck disable=SC1091
source .venv/bin/activate
require_cmd agentcore

AGENT_NAME="$(manifest_read trinetra_agent 2>/dev/null || true)"
AGENT_NAME="${AGENT_NAME:-trinetra}"

log_step "This will destroy the AgentCore Runtime agent '$AGENT_NAME'$( [[ "$DELETE_ECR" == "1" ]] && echo ' (and its ECR repository)' )."
log_warn "This does not remove the auto-created IAM roles, CodeBuild project, or S3"
log_warn "build-artifact bucket - see the checklist this script prints at the end."

if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Proceed with destroying '$AGENT_NAME'?" || { log_info "Aborted."; exit 0; }
fi

DESTROY_FLAGS=()
[[ "$DRY_RUN" == "1" ]] && DESTROY_FLAGS+=(--dry-run)
[[ "$AUTO_YES" == "1" ]] && DESTROY_FLAGS+=(--force)
[[ "$DELETE_ECR" == "1" ]] && DESTROY_FLAGS+=(--delete-ecr-repo)

status=0
log_step "Destroying '$AGENT_NAME'"
if agentcore destroy --agent "$AGENT_NAME" "${DESTROY_FLAGS[@]}"; then
    log_ok "'$AGENT_NAME' destroyed."
else
    log_error "Failed to destroy '$AGENT_NAME' - check output above."
    status=1
fi

if [[ "$DRY_RUN" != "1" && "$status" == "0" ]]; then
    rm -f "$MANIFEST_PATH"
    log_ok "Removed deployment manifest ($MANIFEST_PATH)."
fi

REGION="$(manifest_read region 2>/dev/null || true)"
REGION="${REGION:-$(resolve_region)}"

cat <<EOF

==> Manual cleanup checklist (read-only commands - nothing below deletes anything)

  IAM roles (execution + CodeBuild):
    aws iam list-roles --query "Roles[?contains(RoleName, 'BedrockAgentCore')].RoleName" --output table

  CodeBuild projects:
    aws codebuild list-projects --region $REGION --query "projects[?starts_with(@, 'bedrock-agentcore-')]" --output table

  S3 buckets used for build artifacts:
    aws s3api list-buckets --query "Buckets[?starts_with(Name, 'bedrock-agentcore-')].Name" --output table

  CloudWatch Log groups:
    aws logs describe-log-groups --region $REGION --log-group-name-prefix /aws/bedrock-agentcore --query "logGroups[].logGroupName" --output table
    aws logs describe-log-groups --region $REGION --log-group-name-prefix /aws/codebuild --query "logGroups[].logGroupName" --output table

Delete anything you find above with the matching 'aws iam delete-role' /
'aws codebuild delete-project' / 'aws s3 rb --force' / 'aws logs delete-log-group'
command once you've confirmed it's actually from this deployment.
EOF

exit "$status"
