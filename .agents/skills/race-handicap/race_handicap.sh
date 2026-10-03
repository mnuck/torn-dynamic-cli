#!/bin/bash
#
# Wrapper that runs race_handicap.py from the repo root, so .env (TORN_API_KEY) is found.
#
# Usage: pass race_handicap.py arguments through as-is.
#   .agents/skills/race-handicap/race_handicap.sh ladyME DarkEdge 2937866 "Guest=12"
#   .agents/skills/race-handicap/race_handicap.sh --track "stone park" --laps 10,25 ladyME@Trident DarkEdge
#   TORN_REPO_ROOT=/path/to/repo .agents/skills/race-handicap/race_handicap.sh ...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "${TORN_REPO_ROOT:-}" ]; then
    cd "$TORN_REPO_ROOT"
else
    cd "$SCRIPT_DIR/../../.."
fi

exec python3 "$SCRIPT_DIR/race_handicap.py" "$@"
