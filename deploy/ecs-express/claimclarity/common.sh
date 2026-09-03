#!/usr/bin/env bash
# Shared helpers for setup.sh / teardown.sh in this directory. Not meant to
# be run directly. Deliberately self-contained (not shared with
# deploy/cloudshell/common.sh or the other two projects' deploy/ecs-express
# scripts) so three independent hackathon submissions' deploy scripts never
# collide on one shared file.

set -uo pipefail

# --- output -----------------------------------------------------------

if [[ -t 1 ]]; then
    COLOR_RESET=$'\033[0m'
    COLOR_BLUE=$'\033[1;34m'
    COLOR_YELLOW=$'\033[1;33m'
    COLOR_RED=$'\033[1;31m'
    COLOR_GREEN=$'\033[1;32m'
else
    COLOR_RESET=""; COLOR_BLUE=""; COLOR_YELLOW=""; COLOR_RED=""; COLOR_GREEN=""
fi

log_step()  { printf '%s\n' "${COLOR_BLUE}==>${COLOR_RESET} $*"; }
log_info()  { printf '%s\n' "    $*"; }
log_warn()  { printf '%s\n' "${COLOR_YELLOW}WARNING:${COLOR_RESET} $*" >&2; }
log_error() { printf '%s\n' "${COLOR_RED}ERROR:${COLOR_RESET} $*" >&2; }
log_ok()    { printf '%s\n' "${COLOR_GREEN}OK:${COLOR_RESET} $*"; }

die() { log_error "$*"; exit 1; }

# --- confirmation -------------------------------------------------------

# confirm PROMPT - returns 0 (proceed) if the user types y/yes, or if
# AUTO_YES=1 is set (the --yes flag). Returns 1 (skip) on anything else,
# including non-interactive shells with no --yes, so nothing billable or
# destructive ever runs unattended by accident.
confirm() {
    local prompt="$1"
    if [[ "${AUTO_YES:-0}" == "1" ]]; then
        log_info "(--yes) $prompt -> proceeding"
        return 0
    fi
    if [[ ! -t 0 ]]; then
        log_warn "$prompt -- no terminal to prompt on and --yes not set, skipping."
        return 1
    fi
    read -r -p "$prompt [y/N] " reply
    case "$reply" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# --- prerequisites -------------------------------------------------------

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not found on PATH."
}

check_aws_identity() {
    require_cmd aws
    local identity
    identity=$(aws sts get-caller-identity --output json 2>&1) || {
        log_error "aws sts get-caller-identity failed:"
        printf '%s\n' "$identity" >&2
        die "Not authenticated to AWS. Run 'aws configure' or set AWS credentials, then retry."
    }
    AWS_ACCOUNT_ID=$(printf '%s' "$identity" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Account"])')
    AWS_CALLER_ARN=$(printf '%s' "$identity" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Arn"])')
    export AWS_ACCOUNT_ID AWS_CALLER_ARN
    log_ok "AWS identity: $AWS_CALLER_ARN (account $AWS_ACCOUNT_ID)"
}

resolve_region() {
    local region="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
    if [[ -z "$region" ]]; then
        region=$(aws configure get region 2>/dev/null || true)
    fi
    if [[ -z "$region" ]]; then
        region="us-east-1"
        log_warn "No AWS region configured; defaulting to $region."
    fi
    printf '%s' "$region"
}

require_min_cli_version() {
    # ECS Express Mode is new (Nov 2025); update-express-gateway-service in
    # particular needs AWS CLI >= 2.33.15. Warn, don't hard-fail, since the
    # version-string format has changed across CLI releases before.
    require_cmd aws
    local version
    version=$(aws --version 2>&1 | sed -n 's/^aws-cli\/\([0-9.]*\).*/\1/p')
    if [[ -z "$version" ]]; then
        log_warn "Could not parse 'aws --version' output to check the minimum CLI version (>= 2.33.15 recommended for ECS Express Mode)."
        return 0
    fi
    log_info "AWS CLI version: $version"
    python3 - "$version" <<'EOF' || log_warn "AWS CLI $version may be older than the 2.33.15 minimum recommended for ECS Express Mode - 'aws ecs create-express-gateway-service' etc. may not exist yet. Upgrade if commands below fail with 'Invalid choice'."
import sys
def parts(v):
    return tuple(int(x) for x in v.split(".")[:3])
try:
    sys.exit(0 if parts(sys.argv[1]) >= (2, 33, 15) else 1)
except ValueError:
    sys.exit(0)
EOF
}

# --- repo location --------------------------------------------------------

# Finds the repo root (this script's grandparent-of-grandparent directory)
# and cd's into it. Sets REPO_DIR.
ensure_repo() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
    if [[ ! -f "$here/pyproject.toml" ]] || ! grep -q "agents-for-humans-hackathon" "$here/pyproject.toml" 2>/dev/null; then
        die "Could not find the repo root above $here - run this script from inside a checkout of the repo."
    fi
    REPO_DIR="$here"
    export REPO_DIR
    cd "$REPO_DIR" || die "Could not cd into $REPO_DIR"
    log_ok "Working in $REPO_DIR"
}

# --- deployment manifest ---------------------------------------------------
# A small local JSON file recording what setup.sh created, so teardown.sh
# can find it later without the caller having to note the service ARN down
# by hand. Scoped to this project only (separate manifest file per project).

MANIFEST_PATH_DEFAULT="$HOME/.claimclarity-ecs-express-deployment.json"
MANIFEST_PATH="${CLAIMCLARITY_ECS_MANIFEST:-$MANIFEST_PATH_DEFAULT}"

manifest_write() {
    python3 - "$MANIFEST_PATH" "$@" <<'EOF'
import json, sys
path = sys.argv[1]
data = {}
try:
    with open(path) as f:
        content = f.read().strip()
    if content:
        data = json.loads(content)
except (FileNotFoundError, json.JSONDecodeError):
    pass
for kv in sys.argv[2:]:
    k, _, v = kv.partition("=")
    data[k] = v
with open(path, "w") as f:
    json.dump(data, f, indent=2)
EOF
}

manifest_read() {
    local key="$1"
    [[ -s "$MANIFEST_PATH" ]] || return 1
    python3 -c "
import json
with open('$MANIFEST_PATH') as f:
    content = f.read().strip()
data = json.loads(content) if content else {}
print(data.get('$key', ''))
"
}

# --- IAM roles (account-global, shared with BidWright's/GlacierWatch's own
# deploy/ecs-express/*/setup.sh - idempotent, safe to call from any of them)

ECS_TASK_EXECUTION_ROLE_NAME="ecsTaskExecutionRole"
ECS_INFRA_ROLE_NAME="ecsInfrastructureRoleForExpressServices"

role_exists() {
    aws iam get-role --role-name "$1" >/dev/null 2>&1
}

ensure_ecs_task_execution_role() {
    if role_exists "$ECS_TASK_EXECUTION_ROLE_NAME"; then
        log_ok "IAM role $ECS_TASK_EXECUTION_ROLE_NAME already exists - reusing it."
        return 0
    fi
    log_step "Creating IAM role $ECS_TASK_EXECUTION_ROLE_NAME"
    aws iam create-role --role-name "$ECS_TASK_EXECUTION_ROLE_NAME" --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    }' >/dev/null
    aws iam attach-role-policy --role-name "$ECS_TASK_EXECUTION_ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
    log_ok "Created $ECS_TASK_EXECUTION_ROLE_NAME"
}

ensure_ecs_infrastructure_role() {
    if role_exists "$ECS_INFRA_ROLE_NAME"; then
        log_ok "IAM role $ECS_INFRA_ROLE_NAME already exists - reusing it."
        return 0
    fi
    log_step "Creating IAM role $ECS_INFRA_ROLE_NAME"
    aws iam create-role --role-name "$ECS_INFRA_ROLE_NAME" --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{"Sid": "AllowAccessInfrastructureForECSExpressServices", "Effect": "Allow", "Principal": {"Service": "ecs.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    }' >/dev/null
    aws iam attach-role-policy --role-name "$ECS_INFRA_ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
    log_ok "Created $ECS_INFRA_ROLE_NAME"
}
