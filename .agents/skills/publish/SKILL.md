---
name: publish
description: >
  Deploy the faction dashboard hub to Cloudflare Pages. Use this skill
  whenever the user says "publish",
  "deploy", "ship it", "push to prod", "update the live dashboards", or anything
  that implies refreshing the live faction dashboard site. The hub's home page is
  the OC revenue dashboard; the rest (cpr, racing, chain, respect, track_odds,
  fastband, streakiness) is pulled from generated/.
---

# Publish Skill

Ships the faction dashboard hub to Cloudflare Pages. Run all commands from the
repo root.

The Pages project name is **not** in the repo — it is also the public hostname,
and this repo is public. `deploy.sh` reads `PAGES_PROJECT` from the environment
or `.env` and derives the hub URL as `https://$PAGES_PROJECT.pages.dev`. If it
is unset the script exits with instructions; do not hardcode a value to get
past that.

The deploy is a plain aggregation of files already on disk — it does **not**
regenerate anything. Refresh whatever the user cares about first (see Step 1),
then deploy.

## Step 1 — Refresh the dashboards (as needed)

Each dashboard has its own skill/generator; run the ones that are stale:

- OC revenue dashboard (the hub home page) — `oc-dashboard` skill:
  `.agents/skills/oc-dashboard/generate_oc_dashboard.sh --weeks 52`
- CPR — `cpr-dashboard` skill
- Racing — `racing-dashboard` skill
- Chain — `chain-dashboard` skill
- Respect — `respect-dashboard` skill
- Track odds / fastband — their respective skills

The hub manifest (which files ship) is the `MANIFEST` array at the top of
`.agents/skills/publish/deploy.sh` plus the OC dashboard as `index.html`. Edit
that array to add or drop a dashboard from the live site.

## Step 2 — Preview locally

Open the OC dashboard (and any other refreshed page) and confirm it looks right:

```bash
open .agents/skills/oc-dashboard/dashboard.html
```

Or load it in the in-app Browser. Ask the user to eyeball it and wait for an
explicit "looks good" / "ship it" before deploying.

## Step 3 — Deploy

Once the user confirms:

```bash
.agents/skills/publish/deploy.sh
```

This assembles a temp staging dir (OC dashboard → `index.html`, plus the
manifest files from `generated/`), runs `wrangler pages deploy` against the
configured project, and cleans up. Show the wrangler output.

Requires `wrangler` on `PATH` — the script sources nvm to find it. When
complete, relay the live URL the script prints in its final line.

## Notes

- Missing manifest files warn but don't abort the deploy — the site keeps the
  previously deployed copy of anything not staged this run.
- Pushing to git is separate from deploying. `dashboard.html` refreshes should be
  committed (`Data refresh: N crimes...`); the other dashboards under `generated/`
  are gitignored regenerable output.
