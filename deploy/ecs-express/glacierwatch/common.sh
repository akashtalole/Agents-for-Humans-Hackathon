#!/usr/bin/env bash
# Shared helpers for deploy/ecs-express/glacierwatch/*.sh. Not meant to be run
# directly - sourced by setup.sh and teardown.sh.
#
# These scripts create and destroy real, billable AWS resources (an ECR
# repository, an ECS Express Gateway Service, and - only if not already
# present - two account-global IAM roles). Every function here that touches
# AWS is written to be verbose about what it's about to do, and destructive
# actions default to asking first - see confirm() below.

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
# AUTO_YES=1 is set (the --yes flag on setup.sh/teardown.sh). Returns 1
# (skip) on anything else, including non-interactive shells with no
# AUTO_YES, so nothing destructive/billable ever runs unattended by accident.
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
        region="us-west-2"
        log_warn "No AWS region configured; defaulting to $region."
    fi
    printf '%s' "$region"
}

require_python310() {
    require_cmd python3
    python3 - <<'EOF' || die "Python 3.10+ is required."
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF
}

check_aws_cli_version() {
    # `aws ecs update-express-gateway-service` needs AWS CLI >= 2.33.15 -
    # create/describe/delete work on somewhat older CLIs, but this repo only
    # documents the version that supports the full command set. A version
    # check here can't cover every CLI build string, so this only warns.
    require_cmd aws
    local version
    version=$(aws --version 2>&1 | grep -oE 'aws-cli/[0-9]+\.[0-9]+\.[0-9]+' | head -1 | cut -d/ -f2)
    if [[ -z "$version" ]]; then
        log_warn "Could not detect AWS CLI version - ECS Express Mode needs a recent CLI (>= 2.33.15 for update-express-gateway-service)."
        return
    fi
    log_info "Detected AWS CLI version $version."
    python3 - "$version" <<'EOF'
import sys
have = tuple(int(x) for x in sys.argv[1].split("."))
need = (2, 33, 15)
if have < need:
    print(f"    WARNING: AWS CLI {sys.argv[1]} is older than 2.33.15 - 'aws ecs update-express-gateway-service' "
          f"may not be available yet. 'aws --version --upgrade' or see https://aws.amazon.com/cli/ to update.")
EOF
}

# --- repo location ----------------------------------------------------

REPO_URL="https://github.com/akashtalole/Agents-for-Humans-Hackathon.git"

# Finds (or clones) the repo and cd's into it. Sets REPO_DIR.
ensure_repo() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
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

# --- deployment manifest ---------------------------------------------------
#
# A small JSON file recording what setup.sh created, so teardown.sh (and a
# human re-running setup.sh to update the image) don't have to re-discover
# it. Independent of the AgentCore manifest deploy/cloudshell/ uses - this
# path is GlacierWatch-specific.

MANIFEST_PATH_DEFAULT="$HOME/.glacierwatch-ecs-express-deployment.json"
MANIFEST_PATH="${GLACIERWATCH_ECS_MANIFEST:-$MANIFEST_PATH_DEFAULT}"

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

# --- IAM roles (account-global, shared with BidWright/ClaimClarity's own
# ECS Express setup.sh, if that project also deploys this way) -------------

ensure_role_exists() {
    local role_name="$1" trust_policy="$2" policy_arn="$3"
    if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
        log_info "IAM role $role_name already exists - reusing it."
    else
        log_step "Creating IAM role $role_name"
        run aws iam create-role --role-name "$role_name" --assume-role-policy-document "$trust_policy" >/dev/null
        log_ok "Created $role_name"
    fi
    log_step "Attaching $policy_arn to $role_name (idempotent)"
    run aws iam attach-role-policy --role-name "$role_name" --policy-arn "$policy_arn"
}
