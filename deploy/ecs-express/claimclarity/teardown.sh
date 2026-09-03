#!/usr/bin/env bash
# Tear down the ClaimClarity ECS Express Gateway Service created by
# setup.sh. Irreversible - confirms before deleting anything unless --yes
# is passed.
#
# Usage:
#   deploy/ecs-express/claimclarity/teardown.sh [--yes] [--dry-run] [--service-arn ARN]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./common.sh
source "$SCRIPT_DIR/common.sh"

AUTO_YES=0
DRY_RUN=0
SERVICE_ARN_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --service-arn) SERVICE_ARN_OVERRIDE="$2"; shift 2 ;;
        -h|--help)
            cat <<'EOF'
Usage: teardown.sh [--yes] [--dry-run] [--service-arn ARN]

  --yes              Skip the confirmation prompt.
  --dry-run          Print what would happen without touching AWS.
  --service-arn ARN  Service to delete (default: read from the manifest
                      setup.sh wrote, ~/.claimclarity-ecs-express-deployment.json).

Deletes the ECS Express Gateway Service only. The ECR repository and the
two shared IAM roles are left in place - see the printed checklist at the
end for how to remove them by hand if you want to.
EOF
            exit 0
            ;;
        *) die "Unknown argument: $1 (see --help)" ;;
    esac
done

require_cmd aws
require_cmd python3

SERVICE_ARN="$SERVICE_ARN_OVERRIDE"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
if [[ -z "$SERVICE_ARN" ]]; then
    SERVICE_ARN="$(manifest_read service_arn || true)"
fi
if [[ -z "$REGION" ]]; then
    REGION="$(manifest_read region || true)"
fi
[[ -n "$REGION" ]] || REGION="$(resolve_region)"

if [[ -z "$SERVICE_ARN" ]]; then
    die "No service ARN given and none found in $MANIFEST_PATH. Pass --service-arn explicitly, or check 'aws ecs list-services' for the ARN."
fi

log_step "This will permanently delete the ECS Express Gateway Service:"
log_info "  $SERVICE_ARN"
log_info "  (region: $REGION)"
confirm "Proceed?" || { log_info "Aborted."; exit 0; }

if [[ "$DRY_RUN" != "1" ]]; then
    aws ecs delete-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION"
    log_ok "Deleted $SERVICE_ARN"
    if [[ -s "$MANIFEST_PATH" ]]; then
        rm -f "$MANIFEST_PATH"
        log_info "Removed $MANIFEST_PATH"
    fi
else
    log_info "[dry-run] would run: aws ecs delete-express-gateway-service --service-arn $SERVICE_ARN --region $REGION"
fi

log_step "Not deleted automatically - remove by hand if you want to (read-only commands to find them):"
log_info "  ECR repository (claimclarity-webui) - still has your pushed images and storage costs:"
log_info "    aws ecr describe-repositories --repository-names claimclarity-webui --region $REGION"
log_info "    aws ecr delete-repository --repository-name claimclarity-webui --region $REGION --force"
log_info "  IAM roles (shared with BidWright's/GlacierWatch's own ECS Express deploy scripts -"
log_info "  do NOT delete these if you deployed more than one project's web UI this way):"
log_info "    aws iam get-role --role-name ecsTaskExecutionRole"
log_info "    aws iam get-role --role-name ecsInfrastructureRoleForExpressServices"

log_ok "Done."
