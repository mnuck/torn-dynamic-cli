---
name: oc-dashboard
description: >
  Refresh the faction Organized Crime revenue dashboard — the single-file D3
  visualization (generated/oc_dashboard.html) tracking OC revenue, profit, win rate,
  participation, and person-day efficiency over the most recent 52 weeks. Use
  this skill when the user wants to "refresh the OC dashboard", "update the OC
  revenue dashboard", "rebuild the organized crime dashboard", "run the OC data
  update", or pull the latest completed-crime data into that dashboard before
  publishing.
---

# OC Revenue Dashboard

Renders `generated/oc_dashboard.html`: a self-contained D3 dashboard tracking
faction Organized Crime performance (revenue, profit, win rate, participation,
person-day efficiency) over the most recent 52 weeks. The page does not call
Torn at runtime — all data is embedded as a `const data = {...};` line near the
top of the `<script>` block, filled in by `update_data.py`.

## Where the data lives

The history is stored in **BigQuery**, dataset `oc_dashboard` in `BQ_PROJECT`:

| Table | One row per | Holds |
|---|---|---|
| `weekly` | week (Monday, UTC) | revenue, cost, crime/win/fail counts, and the per-difficulty maps (`by_diff`, `cost_by_diff`, `count_by_diff`, `wins_by_diff`, `person_days_by_diff`, `participants_by_diff`) as JSON |
| `daily` | day | wins and crimes, for the rolling win rate |

Each week's item rewards and consumed-item costs are priced when the week is
processed and then **frozen** in BigQuery. Torn has no price-history API, so a
past week can never be recomputed at the prices it had: BigQuery is the only
copy of that history. It keeps every week; the 52-week window is only what the
page shows.

The tracked `dashboard.html` here is just the page template, with an empty
`const data` line. Don't commit dashboard data to git: the repo is public, and
the rendered page goes to the gitignored `generated/`.

## How to refresh

```bash
.agents/skills/oc-dashboard/generate_oc_dashboard.sh --weeks 52
open generated/oc_dashboard.html
```

The `--weeks N` flag shows only the most recent N weeks (52 is the standard
window). BigQuery keeps all of them either way.

Requires:

- `TORN_API_KEY` and `BQ_PROJECT`, as env vars or in the repo-root `.env`. The
  script reads `.env` itself; it's a FIFO, see AGENTS.md.
- The `bq` CLI (Google Cloud SDK), authenticated with access to `BQ_PROJECT`.
- Network access to `https://api.torn.com/v2`. It calls `GET /faction/crimes`
  for completed organized crimes and `GET /torn/{ids}/items` for market prices.

## Incremental vs full rebuild

- **Incremental (default):** reads the stored history from BigQuery, refetches
  and reprices only the current week, and upserts that week and its days back.
  ~10 seconds.
- **Full rebuild:** runs only when the `weekly` table is empty. Refetches all
  history and **prices every past week at today's market**, so the result is
  not the history it replaces. ~60 seconds (rate-limit sleep). Never empty the
  table to force one.

## Backfilling a missed week

```bash
.agents/skills/oc-dashboard/generate_oc_dashboard.sh --week 2026-06-08
```

`--week YYYY-MM-DD` treats the given date as the current week start so a skipped
week gets fetched and stored without a full rebuild. Only the named week (and
its days) is written to BigQuery; later weeks are fetched too, because the
fetch has no upper bound, but their stored values are left alone. The named
week is priced at today's market.

To find weeks that need a backfill, compare each week's `crimes` count with the
executed crimes (`Successful`/`Failure`, bucketed by UTC Monday of `executed_at`)
in `data/oc_cache.json`. The CPR refresh brings that cache up to date. A week
that shows fewer crimes than the cache was frozen before all of its crimes were
recorded.

## Charts

Each chart is scoped in its own IIFE inside the `dashboard.html` template:

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

`generated/oc_dashboard.html` is the home page (`index.html`) of the live
faction dashboard hub. After refreshing, use the `publish` skill to deploy the hub.
