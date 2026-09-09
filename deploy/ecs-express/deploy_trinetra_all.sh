#!/usr/bin/env bash
# Deploy EVERY Trinetra service to Amazon ECS Express Mode in one go, with all
# image builds done by AWS CodeBuild - so this runs start to finish from AWS
# CloudShell with no local Docker daemon.
#
# What "everything" means here:
#
#   1. trinetra-webui  - the operator dashboard. This is a SINGLE container
#                        holding both halves: Dockerfile.trinetra.webapp is a
#                        multi-stage build that compiles the React frontend
#                        with Node, then copies the built bundle into the
#                        Python image where FastAPI serves it from the same
#                        process. There is no separate frontend deployment to
#                        do, and no CORS configuration, because the API and the
#                        static bundle are served from one origin.
#
#   2. trinetra-a2a    - the Agent2Agent surface other organisations' agents
#                        discover and call. Deployed separately from the
#                        dashboard on purpose: one is a human-facing UI that
#                        belongs behind whatever access control NTKMA puts in
#                        front of it, the other is machine-facing and reachable
#                        by peers. Separate services can be scaled, restricted
#                        and torn down independently.
#
# Each sub-deployment keeps its own ECR repo, CodeBuild project, ECS service
# and manifest file, so this wrapper adds no new state of its own - tearing
# down individually still works exactly as before.
#
# Usage:
#   ./deploy_trinetra_all.sh [--yes] [--region REGION] [--branch BRANCH]
#                            [--dry-run] [--only dashboard|a2a]
#
#   --yes            Skip confirmation prompts in both sub-deployments.
#   --region REGION  Passed through to both.
#   --branch BRANCH  Git branch CodeBuild builds from. Defaults to whatever
#                     this checkout is on - push your changes first.
#   --dry-run        Preview both, touching nothing.
#   --only NAME      Deploy just one of them (still uses this script's summary).
#
# COST WARNING: this creates real, billable AWS resources - TWO ECS Express
# services (each a Fargate task plus a share of a managed load balancer), two
# ECR repositories, two CodeBuild projects, and CloudWatch Logs. Run
# ./teardown_trinetra_all.sh when you are done.
#
# Nothing here has been exercised against a live AWS account - see
# ../CLOUDSHELL.md's standing caveat.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Reuses the dashboard deployment's helper library for logging only.
# shellcheck source=trinetra/common.sh
source "$SCRIPT_DIR/trinetra/common.sh"

PASS_THROUGH=()
ONLY=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only) ONLY="${2:?--only needs a value}"; shift 2 ;;
        --dry-run) DRY_RUN=1; PASS_THROUGH+=("$1"); shift ;;
        --yes) PASS_THROUGH+=("$1"); shift ;;
        --region|--branch) PASS_THROUGH+=("$1" "${2:?$1 needs a value}"); shift 2 ;;
        -h|--help) sed -n '2,46p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done

case "$ONLY" in
    ""|dashboard|a2a) ;;
    *) die "--only must be 'dashboard' or 'a2a', got '$ONLY'" ;;
esac

log_step "Trinetra -> Amazon ECS Express Mode (all services, built on CodeBuild)"
log_info "The dashboard image bundles the React frontend and the FastAPI backend"
log_info "in one container - there is no separate frontend deployment step."
log_info ""

FAILED=()
DEPLOYED=()

run_one() {
    local name="$1" dir="$2"
    if [[ -n "$ONLY" && "$ONLY" != "$name" ]]; then
        log_info "Skipping $name (--only $ONLY)"
        return 0
    fi

    log_step "=== $name ==="
    # Deliberately NOT aborting the whole run on failure: if the dashboard
    # deploys and the A2A agent does not, you want to know that, and you want
    # to keep the thing that worked rather than be left guessing.
    if "$SCRIPT_DIR/$dir/setup.sh" "${PASS_THROUGH[@]}"; then
        DEPLOYED+=("$name")
    else
        FAILED+=("$name")
        log_error "$name failed - continuing so any other service still gets a chance."
    fi
}

run_one dashboard trinetra
run_one a2a trinetra-a2a

log_info ""
log_step "Summary"

# Report outcomes BEFORE the dry-run early exit. A preview that says
# "complete" while both sub-scripts actually errored out is worse than no
# summary at all - it is the one line someone skims.
for name in "${DEPLOYED[@]}"; do
    if [[ "$DRY_RUN" == "1" ]]; then log_ok "$name preview OK"; else log_ok "$name deployed"; fi
done
for name in "${FAILED[@]}"; do
    log_error "$name FAILED"
done

if [[ "$DRY_RUN" == "1" ]]; then
    if [[ ${#FAILED[@]} -eq 0 ]]; then
        log_ok "Dry run complete - nothing was created, built, or pushed."
        exit 0
    fi
    log_error "Dry run finished, but ${#FAILED[@]} of them did not get far enough to preview."
    log_warn "Fix the errors above before deploying for real."
    exit 1
fi

# Read the real URLs back out of each manifest rather than guessing them.
DASH_MANIFEST="${TRINETRA_ECS_MANIFEST:-$HOME/.trinetra-ecs-express-deployment.json}"
A2A_MANIFEST="${TRINETRA_A2A_ECS_MANIFEST:-$HOME/.trinetra-a2a-ecs-express-deployment.json}"

read_url() {
    [[ -s "$1" ]] || return 0
    python3 -c "
import json, sys
try:
    print(json.load(open(sys.argv[1])).get('service_url', ''))
except Exception:
    pass
" "$1" 2>/dev/null
}

DASH_URL="$(read_url "$DASH_MANIFEST")"
A2A_URL="$(read_url "$A2A_MANIFEST")"

log_info ""
if [[ -n "$DASH_URL" ]]; then
    log_ok "Dashboard (frontend + API):  $DASH_URL"
else
    log_warn "Dashboard URL not recorded yet - the service may still be provisioning."
fi
if [[ -n "$A2A_URL" ]]; then
    log_ok "A2A agent card:              ${A2A_URL%/}/.well-known/agent-card.json"
else
    log_warn "A2A URL not recorded yet - the service may still be provisioning."
fi

log_info ""
log_info "Next steps:"
log_info "  - Open the dashboard URL in a browser (allow a few minutes for the"
log_info "    service to reach RUNNING and pass health checks on a first deploy)."
log_info "  - Check the provider:  curl <dashboard-url>/api/status"
log_info "  - Tear both down:      ./teardown_trinetra_all.sh"

[[ ${#FAILED[@]} -eq 0 ]] || exit 1
