#!/usr/bin/env bash
# Shared helpers for deploy/ecs-express/*/setup.sh and teardown.sh. Not meant
# to be run directly - sourced by each project's scripts.
#
# Mirrors the style of deploy/cloudshell/common.sh (colored logging, a
# confirm-before-billable-actions helper, AWS identity/region checks) but
# targets Amazon ECS Express Mode instead of Bedrock AgentCore Runtime.
#
# The two IAM roles ECS Express Mode needs (ecsTaskExecutionRole,
# ecsInfrastructureRoleForExpressServices) are account-global, not
# per-project - ensure_ecs_express_iam_roles() is written to be safe to call
# from every project's setup.sh (bidwright, and any future claimclarity /
# glacierwatch ECS Express setup.sh) without creating duplicates or erroring
# on a role that already exists from a sibling project's run.

set -uo pipefail

# --- output -------------------------------------------------------------

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

# --- confirmation ---------------------------------------------------------

# confirm PROMPT - returns 0 (proceed) if the user types y/yes, or if
# AUTO_YES=1 is set (the --yes flag). Returns 1 (skip) on anything else,
# including non-interactive shells with no AUTO_YES, so nothing billable
# ever runs unattended by accident.
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

# --- prerequisites --------------------------------------------------------

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not found on PATH."
}

check_aws_identity() {
    require_cmd aws
    local identity
    identity=$(aws sts get-caller-identity --output json 2>&1) || {
        log_error "aws sts get-caller-identity failed:"
        printf '%s\n' "$identity" >&2
        die "Not authenticated to AWS. Run 'aws configure' or set AWS_PROFILE, then retry."
    }
    AWS_ACCOUNT_ID=$(printf '%s' "$identity" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Account"])')
    AWS_CALLER_ARN=$(printf '%s' "$identity" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Arn"])')
    export AWS_ACCOUNT_ID AWS_CALLER_ARN
    log_ok "AWS identity: $AWS_CALLER_ARN (account $AWS_ACCOUNT_ID)"
}

# ECS Express Mode is a broadly-available Fargate feature (not the narrower
# per-region allowlist AgentCore Runtime has) - this only resolves a region,
# it doesn't warn about regional availability the way cloudshell/common.sh
# does for AgentCore.
resolve_region() {
    local region="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
    if [[ -z "$region" ]]; then
        region=$(aws configure get region 2>/dev/null || true)
    fi
    if [[ -z "$region" ]]; then
        region="us-west-2"
        log_warn "No AWS region configured; defaulting to $region."
    fi
    printf '%s' "$region"
}

require_docker() {
    require_cmd docker
    docker info >/dev/null 2>&1 || die "Docker daemon is not reachable. Start Docker Desktop (or your Docker daemon) and retry."
}

require_python310() {
    require_cmd python3
    python3 - <<'EOF' || die "Python 3.10+ is required."
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF
}

# --- repo location ----------------------------------------------------

REPO_URL="https://github.com/akashtalole/Agents-for-Humans-Hackathon.git"

# Finds (or clones) the repo and cd's into it. Sets REPO_DIR.
ensure_repo() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    if [[ -f "$here/pyproject.toml" ]] && grep -q "agents-for-humans-hackathon" "$here/pyproject.toml" 2>/dev/null; then
        REPO_DIR="$here"
    else
        REPO_DIR="$HOME/Agents-for-Humans-Hackathon"
        if [[ ! -d "$REPO_DIR/.git" ]]; then
            log_step "Cloning $REPO_URL into $REPO_DIR"
            git clone "$REPO_URL" "$REPO_DIR"
        else
            log_info "Reusing existing checkout at $REPO_DIR"
        fi
    fi
    export REPO_DIR
    cd "$REPO_DIR" || die "Could not cd into $REPO_DIR"
    log_ok "Working in $REPO_DIR"
}

# --- IAM roles (account-global, shared across every project's ECS Express
#     setup.sh) -------------------------------------------------------------

ECS_TASK_EXECUTION_ROLE="ecsTaskExecutionRole"
ECS_INFRA_ROLE="ecsInfrastructureRoleForExpressServices"

_role_exists() {
    aws iam get-role --role-name "$1" >/dev/null 2>&1
}

# Idempotent: safe to call from multiple projects' setup.sh. Skips creation
# for a role that already exists (from this run or a prior/sibling one)
# rather than erroring on "already exists".
ensure_ecs_express_iam_roles() {
    if _role_exists "$ECS_TASK_EXECUTION_ROLE"; then
        log_info "IAM role '$ECS_TASK_EXECUTION_ROLE' already exists - reusing it."
    else
        log_step "Creating IAM role '$ECS_TASK_EXECUTION_ROLE'"
        aws iam create-role --role-name "$ECS_TASK_EXECUTION_ROLE" --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}' >/dev/null
        aws iam attach-role-policy --role-name "$ECS_TASK_EXECUTION_ROLE" \
            --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
        log_ok "Created and attached AmazonECSTaskExecutionRolePolicy to '$ECS_TASK_EXECUTION_ROLE'."
    fi

    if _role_exists "$ECS_INFRA_ROLE"; then
        log_info "IAM role '$ECS_INFRA_ROLE' already exists - reusing it."
    else
        log_step "Creating IAM role '$ECS_INFRA_ROLE'"
        aws iam create-role --role-name "$ECS_INFRA_ROLE" --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{"Sid": "AllowAccessInfrastructureForECSExpressServices", "Effect": "Allow", "Principal": {"Service": "ecs.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}' >/dev/null
        aws iam attach-role-policy --role-name "$ECS_INFRA_ROLE" \
            --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
        log_ok "Created and attached AmazonECSInfrastructureRoleforExpressGatewayServices to '$ECS_INFRA_ROLE'."
    fi
}

# --- ECR ------------------------------------------------------------------

# ensure_ecr_repo NAME REGION -> prints the repository URI on stdout.
ensure_ecr_repo() {
    local name="$1" region="$2"
    local uri
    uri=$(aws ecr describe-repositories --repository-names "$name" --region "$region" \
            --query 'repositories[0].repositoryUri' --output text 2>/dev/null) || uri=""
    if [[ -n "$uri" && "$uri" != "None" ]]; then
        printf '%s' "$uri"
        return 0
    fi
    aws ecr create-repository --repository-name "$name" --region "$region" >/dev/null
    aws ecr describe-repositories --repository-names "$name" --region "$region" \
        --query 'repositories[0].repositoryUri' --output text
}

# --- deployment manifest ---------------------------------------------------

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
