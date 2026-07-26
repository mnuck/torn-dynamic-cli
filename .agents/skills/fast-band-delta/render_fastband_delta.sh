#!/usr/bin/env bash
# Render a fast-band delta trace from a fetched race field-telemetry JSON.
# cd's to repo root so the default generated/ output path resolves there.
set -euo pipefail
cd "$(dirname "$0")/../../.."
exec python3 .agents/skills/fast-band-delta/fastband_delta.py "$@"
