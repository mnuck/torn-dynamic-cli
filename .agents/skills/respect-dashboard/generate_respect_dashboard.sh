#!/bin/bash
#
# Wrapper that runs respect_dashboard.py from the repo root so its default
# output path (generated/respect_dashboard.html) resolves where you expect it.
#
# Usage: pass any respect_dashboard.py flags through; they're forwarded as-is.
#   .agents/skills/respect-dashboard/generate_respect_dashboard.sh
#   .agents/skills/respect-dashboard/generate_respect_dashboard.sh --days 180
#   TORN_REPO_ROOT=/path/to/repo .agents/skills/respect-dashboard/generate_respect_dashboard.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${TORN_REPO_ROOT:-}" ]; then
    cd "$TORN_REPO_ROOT"
else
    cd "$SCRIPT_DIR/../../.."
fi

exec python3 "$SCRIPT_DIR/respect_dashboard.py" "$@"
