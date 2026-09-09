#!/usr/bin/env bash
# Smoke-test the deployed Trinetra agent with a sample of each action shape
# (ask / sos / simulate / calibrate). Run deploy/trinetra/setup.sh first.
#
# Usage:
#   ./invoke_samples.sh [--action ask|sos|simulate|calibrate]   # default: all four

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ONLY_ACTION=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --action) ONLY_ACTION="${2:?--action needs a value}"; shift 2 ;;
        -h|--help) echo "Usage: $0 [--action ask|sos|simulate|calibrate]"; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

ensure_repo

if [[ ! -d .venv ]]; then
    die "No .venv found in $REPO_DIR - run deploy/trinetra/setup.sh first."
fi
# shellcheck disable=SC1091
source .venv/bin/activate
require_cmd agentcore

AGENT_NAME="$(manifest_read trinetra_agent || true)"
AGENT_NAME="${AGENT_NAME:-trinetra}"

invoke_action() {
    local action="$1" payload="$2"
    log_step "Invoking '$AGENT_NAME' (action=$action)"
    if ! agentcore invoke "$payload" --agent "$AGENT_NAME"; then
        log_error "Invocation of '$AGENT_NAME' (action=$action) failed. Check 'agentcore status --agent $AGENT_NAME' and CloudWatch Logs."
        return 1
    fi
}

status=0
if [[ -z "$ONLY_ACTION" || "$ONLY_ACTION" == "ask" ]]; then
    invoke_action ask '{"action": "ask", "text": "Ramkund kaise pahunche?", "language": "hindi"}' || status=1
fi
if [[ -z "$ONLY_ACTION" || "$ONLY_ACTION" == "sos" ]]; then
    invoke_action sos '{"action": "sos", "description": "lost my mother near Kushavarta", "location": "Kushavarta Ghat", "incident_type": "lost_person"}' || status=1
fi
if [[ -z "$ONLY_ACTION" || "$ONLY_ACTION" == "simulate" ]]; then
    invoke_action simulate '{"action": "simulate", "name": "smoke test", "total_pilgrims": 300000, "duration_minutes": 180, "peak_inflow_multiplier": 2.0, "active_ghat_ids": ["ramkund", "kushavarta"]}' || status=1
fi
if [[ -z "$ONLY_ACTION" || "$ONLY_ACTION" == "calibrate" ]]; then
    invoke_action calibrate '{"action": "calibrate"}' || status=1
fi

exit "$status"
