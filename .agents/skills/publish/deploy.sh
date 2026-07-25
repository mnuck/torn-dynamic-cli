#!/bin/bash
#
# Deploy the faction dashboard hub to Cloudflare Pages (project jokerz-oc-stats,
# live at https://jokerz-oc-stats.pages.dev).
#
# The OC revenue dashboard (.agents/skills/oc-dashboard/dashboard.html) becomes
# the site's index.html; the rest of the hub is copied from generated/ by the
# MANIFEST below. Refresh each dashboard via its own skill BEFORE publishing —
# this script only ships whatever is currently on disk.
#
# Usage (from repo root, or via the publish skill):
#   .agents/skills/publish/deploy.sh
#   TORN_REPO_ROOT=/path/to/repo .agents/skills/publish/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${TORN_REPO_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
cd "$REPO_ROOT"

# Curated hub manifest: files copied verbatim from generated/ into the deploy.
# Edit this list to add/remove dashboards from the live site.
MANIFEST=(
    chain_dashboard.html
    cpr_dashboard.html
    racing_dashboard.html
    respect_dashboard.html
    track_odds.html
    track_odds_for_alias.html
    streakiness.html
    fastband_19934929.html
)

OC_DASHBOARD=".agents/skills/oc-dashboard/dashboard.html"

# nvm-managed node hosts the wrangler CLI.
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

# OC revenue dashboard is the hub home page.
if [ ! -f "$OC_DASHBOARD" ]; then
    echo "ERROR: OC dashboard not found at $OC_DASHBOARD" >&2
    exit 1
fi
cp "$OC_DASHBOARD" "$STAGING/index.html"
echo "  staged index.html  <- $OC_DASHBOARD"

# Curated dashboards from generated/. Missing files warn but don't abort.
for f in "${MANIFEST[@]}"; do
    if [ -f "generated/$f" ]; then
        cp "generated/$f" "$STAGING/$f"
        echo "  staged $f"
    else
        echo "  WARN: generated/$f missing — skipping (regenerate via its skill)" >&2
    fi
done

echo "Deploying $STAGING to Cloudflare Pages project jokerz-oc-stats..."
wrangler pages deploy "$STAGING" --project-name jokerz-oc-stats

echo "Done. Live at https://jokerz-oc-stats.pages.dev"
