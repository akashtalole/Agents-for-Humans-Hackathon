#!/usr/bin/env bash
# Tear down every Trinetra ECS Express deployment created by
# deploy_trinetra_all.sh.
#
# Each sub-teardown reads its OWN manifest, so this wrapper only sequences
# them. Run it when you are finished: an ECS Express service left running
# bills for a Fargate task and a share of a managed load balancer
# indefinitely, and the load balancer is the part people forget.
#
# Removing the A2A service makes Trinetra unreachable to every peer that has
# its URL registered - tell them before you run this, or their next
# consultation simply times out with no explanation.
#
# Usage:
#   ./teardown_trinetra_all.sh [--yes] [--region REGION] [--dry-run]
#                              [--only dashboard|a2a]

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=trinetra/common.sh
source "$SCRIPT_DIR/trinetra/common.sh"

PASS_THROUGH=()
ONLY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only) ONLY="${2:?--only needs a value}"; shift 2 ;;
        --yes|--dry-run) PASS_THROUGH+=("$1"); shift ;;
        --region) PASS_THROUGH+=("$1" "${2:?--region needs a value}"); shift 2 ;;
        -h|--help) sed -n '2,17p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done

case "$ONLY" in
    ""|dashboard|a2a) ;;
    *) die "--only must be 'dashboard' or 'a2a', got '$ONLY'" ;;
esac

log_step "Tearing down all Trinetra ECS Express deployments"

FAILED=()

run_one() {
    local name="$1" dir="$2"
    if [[ -n "$ONLY" && "$ONLY" != "$name" ]]; then
        log_info "Skipping $name (--only $ONLY)"
        return 0
    fi
    log_step "=== $name ==="
    # Keep going on failure: a half-finished teardown that stops at the first
    # error leaves the rest billing silently.
    "$SCRIPT_DIR/$dir/teardown.sh" "${PASS_THROUGH[@]}" || {
        FAILED+=("$name")
        log_error "$name teardown failed - check it by hand in the ECS console."
    }
}

run_one dashboard trinetra
run_one a2a trinetra-a2a

log_info ""
if [[ ${#FAILED[@]} -eq 0 ]]; then
    log_ok "All requested Trinetra ECS deployments torn down."
else
    log_error "Some teardowns failed: ${FAILED[*]}"
    log_warn "Verify in the ECS console that no Express service is still running -"
    log_warn "an orphaned one keeps billing for its Fargate task and load balancer."
fi

log_info ""
log_info "NOT removed (shared with any other Express service in this account):"
log_info "  ecsTaskExecutionRole, ecsInfrastructureRoleForExpressServices"

[[ ${#FAILED[@]} -eq 0 ]] || exit 1
