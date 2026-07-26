---
name: respect-dashboard
description: >
  Refresh the Torn faction respect dashboard — daily respect-gain bars
  (attacks and organized crimes above the axis, respect lost to incoming
  attacks below it, with both attacks and losses further split into
  ranked-war vs. other), plus a top-contributors table. Use this skill when
  the user wants to "refresh the respect dashboard", "rebuild
  respect_dashboard.html", "how much respect do we generate", or wants to see
  the faction's daily respect breakdown.
---

# Respect Dashboard

Regenerates `generated/respect_dashboard.html`: a self-contained D3 bar
chart. Daily bars above the axis show total respect gained per calendar day,
split into the attack contribution (itself split into ranked-war vs. other)
and the organized-crime contribution; daily bars below the axis show respect
lost to incoming attacks that landed on our members (also split into
ranked-war vs. other).

## How to refresh

```bash
.agents/skills/respect-dashboard/generate_respect_dashboard.sh
open generated/respect_dashboard.html
```

Default lookback is 90 days; pass `--days N` for a longer or shorter window:

```bash
.agents/skills/respect-dashboard/generate_respect_dashboard.sh --days 180
```

## How it works

Pulls from two endpoints for three respect series:
- `/faction/attacks?filters=attack` from `now - N days`, paginating via
  `_metadata.links.next`. This one call returns both incoming and outgoing
  records in a single pass, so both are used: hits landed by our own
  faction's members (`attacker.faction.id`) contribute `respect_gain`, and
  incoming hits landed on our members (`defender.faction.id`) contribute
  `respect_loss` — being attacked successfully costs the faction respect too,
  not just the attacker's gain (roughly a quarter of it, empirically). Both
  hits and losses are tagged `is_ranked_war` (a field the API provides
  directly), since spikes on either side usually line up with an active
  ranked war — one spike day checked was 98% ranked-war losses, and over the
  full 90-day window most attack and loss respect turned out to be war-driven.
- `/faction/crimes?cat=completed&filters=executed_at` from the same window,
  paginating separately (see gotcha below). Only `status == "Successful"`
  crimes pay out; each one's `rewards.respect` is bucketed into its
  `executed_at` UTC day.

Days with no activity are filled with zero rather than skipped, so quiet days
are visible rather than absent. The chart uses one axis (respect) with bars
above zero (attacks-war, attacks-other, organized crimes, stacked in that
order) and bars below zero (loss-war, loss-other, stacked). Colors: dark blue
(attack war) / light blue (attack other), orange (organized crimes), dark red
(loss war) / light red (loss other) — each war/other pair is a sequential
pair within one hue rather than a fully distinct categorical color, since
both halves are the same underlying measure split by cause. A hover
crosshair shows the exact day's full breakdown, and two toggle tables expose
the full daily series and a top-contributors leaderboard for the window
(attack respect only — OC rewards are shared across a crime's slot members
rather than attributed to one attacker, and incoming losses aren't
attributable to a specific defender in this view either).

Excludes territory, racket, and other passive respect sources: Torn's API
only exposes those (`FactionStatEnum` values like `territoryrespect` via
`/faction/contributors?stat=X`) as a current all-time cumulative total per
member, not a dated history, so they can't be charted retroactively. The only
way to track them going forward would be to poll and diff that total daily.

**Pagination gotcha this skill's fetch avoids:** the generic `torn <cmd> --all`
CLI flag and `report.go`'s `fetchAllPages` helper both fall back to the
`_metadata.links.prev` link whenever `next` is empty — which is unsafe for
long backfills, since `next` legitimately goes empty at the true end of a
`from`-bounded range, and Torn's generated `prev` links drop the original
`from`/`sort`/`limit` params, silently walking backward through unrelated
history. This script's own fetch functions only ever follow `next` and stop
when it's empty, so they don't hit that bug.

## Caching

Hits, incoming losses, and OC events are cached at
`~/.torn_cache/respect_dashboard_cache.json`, same pattern as the
`oc-spawning` skill's executed-crimes cache: historical records never
change once they've happened, so each run only fetches what's newer than
the cache's high-water mark instead of re-walking the whole `--days` window
(a 90-day attacks fetch alone is ~400 paginated requests, several minutes).
Records are deduped by their own id (`attack_id` for hits/losses, `crime_id`
for OCs) rather than by day, since a delta fetch's boundary can re-return a
record already cached.

The cache also tracks the earliest `since` timestamp it has ever fetched
from (`covered_since` / `oc_covered_since`). A run with a *shorter* `--days`
than before just serves from cache plus a small delta; a run with a
*longer* `--days` than any previous run detects the backward gap and
re-fetches the full window once to fill it, then goes back to fast deltas.

The cache file carries a `schema_version`. If a code change adds a field a
cached record didn't use to have (e.g. adding `war` tagging to hits after
losses already had it), bump `CACHE_SCHEMA_VERSION` in the script -- a
version mismatch on load discards the cache wholesale and does one full
re-fetch, rather than crashing on a missing key or silently treating old
records as belonging to the wrong bucket.
