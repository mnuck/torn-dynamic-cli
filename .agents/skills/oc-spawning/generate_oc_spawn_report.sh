#!/bin/bash
#
# Wrapper that runs oc_spawn_report.py from the repo root so ./torn resolves.
#
# Usage: pass any oc_spawn_report.py flags through; they're forwarded as-is.
#   .agents/skills/oc-spawning/generate_oc_spawn_report.sh
#   .agents/skills/oc-spawning/generate_oc_spawn_report.sh --recruit-positions "Recruit,Trainee"
#   TORN_REPO_ROOT=/path/to/repo .agents/skills/oc-spawning/generate_oc_spawn_report.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${TORN_REPO_ROOT:-}" ]; then
    cd "$TORN_REPO_ROOT"
else
    cd "$SCRIPT_DIR/../../.."
fi

exec python3 "$SCRIPT_DIR/oc_spawn_report.py" "$@"
