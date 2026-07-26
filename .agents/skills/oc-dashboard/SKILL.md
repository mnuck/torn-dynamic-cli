---
name: oc-dashboard
description: >
  Refresh the faction Organized Crime revenue dashboard — the single-file D3
  visualization (dashboard.html) tracking OC revenue, profit, win rate,
  participation, and person-day efficiency over the most recent 52 weeks. Use
  this skill when the user wants to "refresh the OC dashboard", "update the OC
  revenue dashboard", "rebuild the organized crime dashboard", "run the OC data
  update", or pull the latest completed-crime data into that dashboard before
  publishing.
---

# OC Revenue Dashboard

Refreshes `.agents/skills/oc-dashboard/dashboard.html`: a self-contained D3
dashboard tracking faction Organized Crime performance (revenue, profit, win
rate, participation, person-day efficiency) over the most recent 52 weeks. The
page does not call Torn at runtime — all data is embedded as a
`const data = {...};` line near the top of the `<script>` block, injected by
`update_data.py`.

Unlike the other dashboards in this repo, `dashboard.html` is **both source and
datastore**: `update_data.py` freezes each historical week's item rewards and
consumed-item costs into the file in place, so old weeks are never silently
repriced as market values shift. That is why `dashboard.html` is a tracked file
(not regenerable output in `generated/`), and each refresh is committed with a
`Data refresh: N crimes...` message.

## How to refresh

```bash
.agents/skills/oc-dashboard/generate_oc_dashboard.sh --weeks 52
open .agents/skills/oc-dashboard/dashboard.html
```

The `--weeks N` flag keeps only the most recent N weeks in the generated
dashboard (52 is the standard window).

Requires `TORN_API_KEY` (env var, or the repo-root `.env` — the script reads it
automatically) and direct network access to `https://api.torn.com/v2`. It calls
`GET /faction/crimes` for completed organized crimes and `GET /torn/{ids}/items`
for market prices.

## Incremental vs full rebuild

- **Incremental (default):** historical weeks stay frozen; only the current week
  is refetched and repriced. ~10 seconds.
- **Full rebuild:** triggered automatically when the embedded schema is missing
  fields (e.g. `costByDiff`, `participantsByDiff`, `personDaysByDiff`). Refetches
  all history and **reprices every historical week at current market prices**.
  ~60 seconds (rate-limit sleep). Avoid unless a schema migration is intentional.

## Backfilling a missed week

```bash
.agents/skills/oc-dashboard/generate_oc_dashboard.sh --week 2026-06-08
```

`--week YYYY-MM-DD` treats the given date as the current week start so a skipped
week gets fetched and merged without a full rebuild.

## Charts

Each chart is scoped in its own IIFE inside `dashboard.html`:

1. Weekly OC Revenue — stacked bars by low/high difficulty split, red cost caps
2. Weekly OC Attempts — stacked bars by low/high difficulty split
3. Weekly Participants by Highest OC Level — each member counted once/week at
   their highest OC difficulty
4. Rolling Win Rate — 28-day and 7-day rolling averages with hover window bands
5. Avg Revenue/Profit by Difficulty — grouped Last 52 / Last 4 weeks bars;
   defaults to Profit per Person-Day
6. Total Revenue by Difficulty — stacked profit plus cost bars
7. Win Rate by Difficulty — grouped Last 52 / Last 4 weeks bars, 85% target line

Theme: dark navy (`#1a1a2e`) with gold accents (`#c9a227`).

## Publishing

`dashboard.html` is the home page (`index.html`) of the live faction dashboard
hub. After refreshing, use the `publish` skill to deploy the hub.
