#!/bin/bash
#
# Wrapper that runs racing_dashboard.py from the repo root so its default
# bare-filename paths (racing_dashboard.html, cache_races.json, Racing.json)
# resolve where you expect them.
#
# Usage: pass any racing_dashboard.py flags through; they're forwarded as-is.
#   .agents/skills/racing-dashboard/generate_racing_dashboard.sh
#   .agents/skills/racing-dashboard/generate_racing_dashboard.sh --no-fetch
#   TORN_REPO_ROOT=/path/to/repo .agents/skills/racing-dashboard/generate_racing_dashboard.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${TORN_REPO_ROOT:-}" ]; then
    cd "$TORN_REPO_ROOT"
else
    cd "$SCRIPT_DIR/../../.."
fi

exec python3 "$SCRIPT_DIR/racing_dashboard.py" "$@"
