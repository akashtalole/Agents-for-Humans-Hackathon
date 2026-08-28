#!/usr/bin/env bash
# Smoke-test both deployed agents with the repo's bundled example data, sent
# as inline text (document_texts / rfp_text+profile_text) rather than file
# paths - the shape a real caller has to use, since they have no filesystem
# access to the deployed container. Run deploy/cloudshell/setup.sh first.
#
# Usage:
#   ./invoke_samples.sh [--agent bidwright|claimclarity]   # default: both

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ONLY_AGENT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent) ONLY_AGENT="${2:?--agent needs a value}"; shift 2 ;;
        -h|--help) echo "Usage: $0 [--agent bidwright|claimclarity]"; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

ensure_repo

if [[ ! -d .venv ]]; then
    die "No .venv found in $REPO_DIR - run deploy/cloudshell/setup.sh first."
fi
# shellcheck disable=SC1091
source .venv/bin/activate
require_cmd agentcore

build_bidwright_payload() {
    python3 -c "
import json
with open('examples/sample_rfp.md') as f:
    rfp_text = f.read()
with open('examples/company_profile.json') as f:
    profile_text = f.read()
print(json.dumps({'rfp_text': rfp_text, 'profile_text': profile_text}))
"
}

build_claimclarity_payload() {
    python3 -c "
import json
paths = [
    'examples/claimclarity/denial_notice.md',
    'examples/claimclarity/plan_summary_of_benefits.md',
    'examples/claimclarity/medical_record_excerpt.md',
]
texts = [open(p).read() for p in paths]
print(json.dumps({'document_texts': texts}))
"
}

invoke_one() {
    local agent_key="$1" build_payload_fn="$2"
    local agent_name
    agent_name="$(manifest_read "${agent_key}_agent" || true)"
    agent_name="${agent_name:-$agent_key}"

    log_step "Invoking '$agent_name'"
    local payload
    payload="$("$build_payload_fn")"
    if ! agentcore invoke "$payload" --agent "$agent_name"; then
        log_error "Invocation of '$agent_name' failed. Check 'agentcore status --agent $agent_name' and CloudWatch Logs."
        return 1
    fi
}

status=0
if [[ -z "$ONLY_AGENT" || "$ONLY_AGENT" == "bidwright" ]]; then
    invoke_one bidwright build_bidwright_payload || status=1
fi
if [[ -z "$ONLY_AGENT" || "$ONLY_AGENT" == "claimclarity" ]]; then
    invoke_one claimclarity build_claimclarity_payload || status=1
fi

exit "$status"
