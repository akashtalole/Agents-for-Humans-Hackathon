#!/usr/bin/env bash
# Tear down everything deploy/cloudshell/setup.sh created. Safe by default:
# previews what will be destroyed and asks before doing anything, unless
# --yes is passed.
#
# Usage:
#   ./teardown.sh [--yes] [--agent bidwright|claimclarity] [--dry-run] [--keep-ecr]
#
#   --yes          Skip confirmation prompts (for unattended/CI use).
#   --agent NAME   Tear down only this agent (default: both, from the manifest).
#   --dry-run      Pass --dry-run through to `agentcore destroy` (preview only).
#   --keep-ecr     Don't delete the ECR repository (kept by default deletes it,
#                  since image storage is the main ongoing cost left behind).
#
# What this does NOT do: `agentcore destroy` removes the AgentCore Runtime
# agent and (with --delete-ecr-repo, the default here) its ECR repository.
# It is not documented to also remove the IAM execution/CodeBuild roles, the
# CodeBuild project, or the S3 bucket used for build artifacts that
# `agentcore configure`/`deploy` auto-created. Those have little to no
# ongoing cost on their own, but this script prints a checklist at the end
# with read-only `aws` commands to find and, if you want, remove them by
# hand - it will not delete them for you, since matching them by naming
# convention risks catching something you didn't create with this script.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

ONLY_AGENT=""
DRY_RUN=0
AUTO_YES=0
DELETE_ECR=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --agent) ONLY_AGENT="${2:?--agent needs a value}"; shift 2 ;;
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

if [[ ! -s "$MANIFEST_PATH" ]]; then
    log_warn "No deployment manifest at $MANIFEST_PATH."
    log_warn "Falling back to the default agent names 'bidwright' and 'claimclarity'."
fi

AGENTS_TO_DESTROY=()
if [[ -n "$ONLY_AGENT" ]]; then
    AGENTS_TO_DESTROY=("$ONLY_AGENT")
else
    for key in bidwright claimclarity; do
        name="$(manifest_read "${key}_agent" 2>/dev/null || true)"
        AGENTS_TO_DESTROY+=("${name:-$key}")
    done
fi

log_step "This will destroy the following AgentCore Runtime agent(s):"
for a in "${AGENTS_TO_DESTROY[@]}"; do
    log_info " - $a$( [[ "$DELETE_ECR" == "1" ]] && echo ' (and its ECR repository)' )"
done
log_warn "This does not remove the auto-created IAM roles, CodeBuild project, or S3"
log_warn "build-artifact bucket - see the checklist this script prints at the end."

if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Proceed with destroying these agents?" || { log_info "Aborted."; exit 0; }
fi

DESTROY_FLAGS=()
[[ "$DRY_RUN" == "1" ]] && DESTROY_FLAGS+=(--dry-run)
[[ "$AUTO_YES" == "1" ]] && DESTROY_FLAGS+=(--force)
[[ "$DELETE_ECR" == "1" ]] && DESTROY_FLAGS+=(--delete-ecr-repo)

overall_status=0
for a in "${AGENTS_TO_DESTROY[@]}"; do
    log_step "Destroying '$a'"
    if agentcore destroy --agent "$a" "${DESTROY_FLAGS[@]}"; then
        log_ok "'$a' destroyed."
    else
        log_error "Failed to destroy '$a' - check output above."
        overall_status=1
    fi
done

if [[ "$DRY_RUN" != "1" && "$overall_status" == "0" ]]; then
    rm -f "$MANIFEST_PATH"
    log_ok "Removed deployment manifest ($MANIFEST_PATH)."
fi

REGION="$(manifest_read region 2>/dev/null || true)"
REGION="${REGION:-$(resolve_region)}"

cat <<EOF

==> Manual cleanup checklist (read-only commands - nothing below deletes anything)

These are the resource kinds AgentCore CLI auto-creates that 'agentcore destroy'
is not documented to remove. Most cost little or nothing sitting idle, but if
you want a fully clean account, check for and remove them yourself:

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
command once you've confirmed it's actually from this deployment and not
something else in your account using the same prefix.
EOF

exit "$overall_status"
