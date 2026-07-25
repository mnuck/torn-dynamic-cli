#!/bin/bash
#
# Wrapper that runs update_data.py from the repo root. update_data.py locates
# dashboard.html and the repo-root .env relative to its own directory, so cwd
# does not actually matter — but we cd to the repo root anyway to match the
# other dashboard generators' conventions.
#
# Usage: pass any update_data.py flags through; they're forwarded as-is.
#   .agents/skills/oc-dashboard/generate_oc_dashboard.sh
#   .agents/skills/oc-dashboard/generate_oc_dashboard.sh --weeks 52
#   .agents/skills/oc-dashboard/generate_oc_dashboard.sh --week 2026-06-08
#   TORN_REPO_ROOT=/path/to/repo .agents/skills/oc-dashboard/generate_oc_dashboard.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${TORN_REPO_ROOT:-}" ]; then
    cd "$TORN_REPO_ROOT"
else
    cd "$SCRIPT_DIR/../../.."
fi

exec python3 "$SCRIPT_DIR/update_data.py" "$@"
