#!/bin/bash
#
# Deploy the faction dashboard hub to Cloudflare Pages.
#
# The Pages project name is deliberately NOT hardcoded here — this repo is
# public, and the project name is also the public hostname. Set PAGES_PROJECT
# in the environment or in the repo-root .env (which is gitignored); the hub
# URL is derived from it as https://$PAGES_PROJECT.pages.dev.
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

# Pages project name lives in the environment or .env, never in the repo.
if [[ -z "${PAGES_PROJECT:-}" && -f .env ]]; then
    PAGES_PROJECT="$(grep -m1 '^PAGES_PROJECT=' .env | cut -d= -f2- | tr -d '"'"'"' ')"
fi
if [[ -z "${PAGES_PROJECT:-}" ]]; then
    echo "ERROR: PAGES_PROJECT is not set." >&2
    echo "       Add 'PAGES_PROJECT=<your-pages-project>' to .env, or export it." >&2
    exit 1
fi
HUB_URL="https://${PAGES_PROJECT}.pages.dev"

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
    war_incoming_45796.html
    war_nettrade_45796.html
    koa_incoming_45796.html
    kassie_war_report.html
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

# Pages treats only its production branch as production; wrangler otherwise infers
# the branch from git, so deploying from a feature branch silently publishes to a
# preview URL instead of the live hub. Pin it.
PAGES_BRANCH="${PAGES_BRANCH:-main}"

echo "Deploying $STAGING to Cloudflare Pages project $PAGES_PROJECT (branch: $PAGES_BRANCH)..."
wrangler pages deploy "$STAGING" \
    --project-name "$PAGES_PROJECT" \
    --branch "$PAGES_BRANCH" \
    --commit-dirty=true

# Verify every staged file is served byte-for-byte from the live hub. A
# preview-only deploy returns 200 for everything (falling back to index.html),
# and an unchanged file matches the *previous* build just as well, so only a
# full-content comparison of the files that changed catches it — index.html
# (the OC dashboard) changes on every refresh, and it is checked too. Retry a
# few times for the edge cache to catch up.
verify_live() {
    local f mismatched=()
    for f in "$STAGING"/*; do
        f="$(basename "$f")"
        curl -sfL "$HUB_URL/$f" | cmp -s - "$STAGING/$f" || mismatched+=("$f")
    done
    if [ "${#mismatched[@]}" -eq 0 ]; then
        return 0
    fi
    echo "  not yet live: ${mismatched[*]}" >&2
    return 1
}

echo "Verifying staged files against $HUB_URL ..."
for attempt in 1 2 3 4 5; do
    sleep 5
    if verify_live; then
        echo "Done. Live at $HUB_URL"
        exit 0
    fi
done
echo "WARN: the live hub is not serving this build — it may have deployed to a" >&2
echo "      preview URL, or the edge cache has not caught up. Re-check before" >&2
echo "      telling anyone it is live." >&2
exit 1
