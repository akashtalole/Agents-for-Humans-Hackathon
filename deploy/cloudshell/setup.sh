#!/usr/bin/env bash
# Spin up BidWright and ClaimClarity on Amazon Bedrock AgentCore Runtime,
# meant to run inside AWS CloudShell (or any shell with the AWS CLI
# configured and Bedrock access). Idempotent - safe to re-run.
#
# Usage:
#   ./setup.sh [--yes] [--region REGION] [--deployment-type container|direct_code_deploy] [--dry-run]
#
#   --yes               Skip the confirmation prompt (for unattended/CI use).
#   --region REGION     Override the detected AWS region.
#   --deployment-type   "container" (default; builds an ARM64 image via
#                        CodeBuild - well documented, works from CloudShell
#                        with no local Docker) or "direct_code_deploy" (a
#                        lighter path with less AWS documentation coverage -
#                        try it if you want fewer resources to manage, but
#                        verify it behaves as expected for your account).
#   --dry-run           Print what would run without touching AWS.
#
# What it does:
#   1. Locates (or clones) this repo, creates a venv, installs deps plus the
#      AgentCore starter toolkit (`bedrock-agentcore-starter-toolkit`).
#   2. Verifies AWS identity, resolves a region, and checks Bedrock is
#      reachable there.
#   3. Runs `agentcore configure` + `agentcore deploy` for BidWright and
#      ClaimClarity. IAM execution roles, an ECR repository, and (for the
#      default container deployment type) a CodeBuild project are
#      auto-created by the toolkit.
#   4. Writes a deployment manifest (default ~/.agentcore-deployment.json)
#      that invoke_samples.sh and teardown.sh read.
#
# COST WARNING: this creates billable AWS resources - Bedrock model
# invocations, AgentCore Runtime, CodeBuild build minutes, ECR image storage,
# an S3 bucket for build artifacts, and CloudWatch Logs. Run
# deploy/cloudshell/teardown.sh when you're done with the demo to avoid
# ongoing charges. Nothing here has been exercised against a live AWS account
# during development (this development environment had no working Bedrock
# access) - read through this script before running it, and watch the output
# of the first `agentcore deploy` closely.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

DEPLOYMENT_TYPE="container"
REGION_OVERRIDE=""
DRY_RUN=0
AUTO_YES=0

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=1; shift ;;
        --region) REGION_OVERRIDE="${2:?--region needs a value}"; shift 2 ;;
        --deployment-type) DEPLOYMENT_TYPE="${2:?--deployment-type needs a value}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done
export AUTO_YES

case "$DEPLOYMENT_TYPE" in
    container|direct_code_deploy) ;;
    *) die "--deployment-type must be 'container' or 'direct_code_deploy', got '$DEPLOYMENT_TYPE'" ;;
esac

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

log_step "BidWright + ClaimClarity -> Amazon Bedrock AgentCore Runtime setup"
log_warn "This creates BILLABLE AWS resources (Bedrock invocations, AgentCore Runtime,"
log_warn "CodeBuild, ECR, S3, CloudWatch Logs). Run teardown.sh when you're done."
if [[ "$DRY_RUN" != "1" ]]; then
    confirm "Continue?" || { log_info "Aborted."; exit 0; }
fi

require_python310
check_aws_identity
REGION="${REGION_OVERRIDE:-$(resolve_region)}"
log_ok "Using region: $REGION"

ensure_repo

log_step "Setting up Python environment in $REPO_DIR/.venv"
if [[ ! -d .venv ]]; then
    run python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
run pip install -q --upgrade pip
run pip install -q -e ".[agentcore]"
run pip install -q bedrock-agentcore-starter-toolkit
log_ok "Dependencies installed"

log_step "Checking Bedrock model access in $REGION"
if aws bedrock list-foundation-models --region "$REGION" --by-provider anthropic \
        >/tmp/agentcore_models.json 2>/tmp/agentcore_models.err; then
    log_ok "Bedrock is reachable in $REGION."
else
    log_warn "Could not list Bedrock foundation models (see /tmp/agentcore_models.err)."
    log_warn "If deployment fails with an access error, enable Anthropic model access in the"
    log_warn "Bedrock console -> Model access, for region $REGION, then re-run this script."
fi

deploy_agent() {
    local name="$1" entrypoint="$2"

    log_step "Configuring $name ($entrypoint, deployment-type=$DEPLOYMENT_TYPE)"
    run agentcore configure \
        --entrypoint "$entrypoint" \
        --name "$name" \
        --region "$REGION" \
        --runtime PYTHON_3_12 \
        --requirements-file deploy/cloudshell/requirements-agentcore.txt \
        --deployment-type "$DEPLOYMENT_TYPE" \
        --ecr auto \
        --disable-memory \
        --non-interactive

    log_step "Deploying $name (first deploy can take several minutes - container builds run on CodeBuild)"
    run agentcore deploy --agent "$name" --auto-update-on-conflict \
        --env "BIDWRIGHT_MODEL_PROVIDER=bedrock" --env "CLAIMCLARITY_MODEL_PROVIDER=bedrock"

    log_step "Status for $name"
    run agentcore status --agent "$name"

    if [[ "$DRY_RUN" != "1" ]]; then
        manifest_write \
            "${name}_agent=$name" \
            "${name}_region=$REGION" \
            "${name}_entrypoint=$entrypoint" \
            "${name}_deployment_type=$DEPLOYMENT_TYPE"
    fi
}

deploy_agent bidwright agentcore_app.py
deploy_agent claimclarity agentcore_app_claimclarity.py

if [[ "$DRY_RUN" != "1" ]]; then
    manifest_write "region=$REGION" "repo_dir=$REPO_DIR" "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log_ok "Both agents deployed. Manifest written to $MANIFEST_PATH"
else
    log_ok "Dry run complete - nothing was created."
fi

log_info ""
log_info "Next steps:"
log_info "  - Smoke-test both agents:  deploy/cloudshell/invoke_samples.sh"
log_info "  - Tear everything down:    deploy/cloudshell/teardown.sh"
