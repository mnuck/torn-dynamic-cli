#!/bin/bash
#
# Wrapper that runs chain_dashboard.py from the repo root so its default
# output path (generated/chain_dashboard.html) resolves where you expect it.
#
# Usage: pass any chain_dashboard.py flags through; they're forwarded as-is.
#   .agents/skills/chain-dashboard/generate_chain_dashboard.sh
#   .agents/skills/chain-dashboard/generate_chain_dashboard.sh --chain-id 61682092
#   TORN_REPO_ROOT=/path/to/repo .agents/skills/chain-dashboard/generate_chain_dashboard.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${TORN_REPO_ROOT:-}" ]; then
    cd "$TORN_REPO_ROOT"
else
    cd "$SCRIPT_DIR/../../.."
fi

exec python3 "$SCRIPT_DIR/chain_dashboard.py" "$@"
