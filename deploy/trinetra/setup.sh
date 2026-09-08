#!/usr/bin/env bash
# Deploy Trinetra to Amazon Bedrock AgentCore Runtime, meant to run inside
# AWS CloudShell (or any shell with the AWS CLI configured). Idempotent -
# safe to re-run.
#
# Usage:
#   ./setup.sh [--yes] [--region REGION] [--deployment-type container|direct_code_deploy]
#              [--model-provider bedrock|anthropic] [--dry-run]
#
#   --yes               Skip the confirmation prompt (for unattended/CI use).
#   --region REGION     Override the detected AWS region.
#   --deployment-type   "container" (default; builds an ARM64 image via
#                        CodeBuild - well documented, works from CloudShell
#                        with no local Docker) or "direct_code_deploy" (a
#                        lighter path with less AWS documentation coverage).
#   --model-provider    "bedrock" (default - no API key needed, model calls
#                        are authorized by the agent's IAM execution role) or
#                        "anthropic" (calls the Anthropic API directly; requires
#                        ANTHROPIC_API_KEY to already be set in your shell
#                        environment, and passes it to `agentcore deploy --env`
#                        as its ONLY supported mechanism - the AgentCore CLI
#                        has no native Secrets Manager/SSM Parameter Store
#                        integration for this, so the raw key value goes on
#                        the command line for that one command).
#   --dry-run           Print what would run without touching AWS.
#
# What it does:
#   1. Locates (or clones) this repo, creates a venv, installs deps plus the
#      AgentCore starter toolkit (`bedrock-agentcore-starter-toolkit`).
#   2. Verifies AWS identity, resolves a region, and (for --model-provider
#      bedrock, the default) checks Bedrock is reachable there.
#   3. Runs `agentcore configure` + `agentcore deploy` for Trinetra. IAM
#      execution roles, an ECR repository, and (for the default container
#      deployment type) a CodeBuild project are auto-created by the toolkit.
#      CodeBuild only builds the container IMAGE here - it never calls a
#      model and never sees any API key; model credentials are injected as
#      a runtime environment variable via `agentcore deploy --env`, a
#      separate step from the image build.
#   4. Writes a deployment manifest (default ~/.agentcore-deployment.json)
#      that invoke_samples.sh and teardown.sh read.
#
# COST WARNING: this creates billable AWS resources - Bedrock model
# invocations (or, with --model-provider anthropic, billable Anthropic API
# usage instead), AgentCore Runtime, CodeBuild build minutes, ECR image
# storage, an S3 bucket for build artifacts, and CloudWatch Logs. Run
# deploy/trinetra/teardown.sh when you're done with the demo to avoid
# ongoing charges. Nothing here has been exercised against a live AWS account
# during development - read through this script before running it, and
# watch the output of the first `agentcore deploy` closely.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

DEPLOYMENT_TYPE="container"
MODEL_PROVIDER="bedrock"
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
        --model-provider) MODEL_PROVIDER="${2:?--model-provider needs a value}"; shift 2 ;;
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

case "$MODEL_PROVIDER" in
    bedrock) ;;
    anthropic)
        if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
            die "--model-provider anthropic requires ANTHROPIC_API_KEY to be set in your shell. Run: export ANTHROPIC_API_KEY=sk-ant-... then re-run this script."
        fi
        ;;
    *) die "--model-provider must be 'bedrock' or 'anthropic', got '$MODEL_PROVIDER'" ;;
esac

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        local shown=()
        local arg
        for arg in "$@"; do
            if [[ "$arg" == ANTHROPIC_API_KEY=* ]]; then
                shown+=("ANTHROPIC_API_KEY=***redacted***")
            else
                shown+=("$arg")
            fi
        done
        printf '[dry-run] %s\n' "${shown[*]}"
    else
        "$@"
    fi
}

log_step "Trinetra -> Amazon Bedrock AgentCore Runtime setup"
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
run pip install -q -e "."
run pip install -q bedrock-agentcore-starter-toolkit
log_ok "Dependencies installed"

if [[ "$MODEL_PROVIDER" == "bedrock" ]]; then
    log_step "Checking Bedrock model access in $REGION"
    if aws bedrock list-foundation-models --region "$REGION" --by-provider anthropic \
            >/tmp/agentcore_models.json 2>/tmp/agentcore_models.err; then
        log_ok "Bedrock is reachable in $REGION."
    else
        log_warn "Could not list Bedrock foundation models (see /tmp/agentcore_models.err)."
        log_warn "If deployment fails with an access error, enable Anthropic model access in the"
        log_warn "Bedrock console -> Model access, for region $REGION, then re-run this script."
    fi
else
    log_step "Model provider: anthropic (skipping Bedrock reachability check)"
    log_warn "ANTHROPIC_API_KEY will be passed to 'agentcore deploy --env' and injected into the"
    log_warn "deployed container as a runtime environment variable. It is not written to any file"
    log_warn "in this repo and CodeBuild never sees it (CodeBuild only builds the container image)."
fi

log_step "Configuring trinetra (agentcore_app_trinetra.py, deployment-type=$DEPLOYMENT_TYPE)"
run agentcore configure \
    --entrypoint agentcore_app_trinetra.py \
    --name trinetra \
    --region "$REGION" \
    --runtime PYTHON_3_12 \
    --requirements-file deploy/trinetra/requirements-agentcore.txt \
    --deployment-type "$DEPLOYMENT_TYPE" \
    --ecr auto \
    --disable-memory \
    --non-interactive

if [[ "$MODEL_PROVIDER" == "anthropic" ]]; then
    deploy_env_args=(--env "TRINETRA_MODEL_PROVIDER=anthropic" --env "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY")
else
    deploy_env_args=(--env "TRINETRA_MODEL_PROVIDER=bedrock")
fi

log_step "Deploying trinetra (first deploy can take several minutes - container builds run on CodeBuild)"
run agentcore deploy --agent trinetra --auto-update-on-conflict "${deploy_env_args[@]}"

log_step "Status for trinetra"
run agentcore status --agent trinetra

if [[ "$DRY_RUN" != "1" ]]; then
    manifest_write \
        "trinetra_agent=trinetra" \
        "trinetra_region=$REGION" \
        "trinetra_entrypoint=agentcore_app_trinetra.py" \
        "trinetra_deployment_type=$DEPLOYMENT_TYPE" \
        "region=$REGION" "repo_dir=$REPO_DIR" "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log_ok "Trinetra deployed. Manifest written to $MANIFEST_PATH"
else
    log_ok "Dry run complete - nothing was created."
fi

log_info ""
log_info "Next steps:"
log_info "  - Smoke-test the agent:   deploy/trinetra/invoke_samples.sh"
log_info "  - Tear everything down:   deploy/trinetra/teardown.sh"
