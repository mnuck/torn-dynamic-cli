---
name: cpr-dashboard
description: >
  Refresh the OC Checkpoint Pass Rate (CPR) dashboard — the interactive
  cpr_dashboard.html visualization of every faction member's per-crime checkpoint
  pass rates over time. Use this skill when the user wants to "refresh the CPR
  dashboard", "rebuild the checkpoint pass rate chart", "update cpr_dashboard.html",
  "regenerate the OC pass rate visualization", or pull the latest faction OC history
  into that dashboard. Fetches current members + full OC history, accumulates new
  per-slot CPR data points, and injects them into a standalone D3 HTML file.
---

# CPR Dashboard

Regenerates `generated/cpr_dashboard.html`: a self-contained D3 visualization
plotting each faction member's checkpoint pass rate per organized crime over time,
filterable by member and crime type.

## How to refresh

```bash
.agents/skills/cpr-dashboard/generate_cpr_dashboard.sh
open generated/cpr_dashboard.html
```

Requires the built `./torn` binary (`go build -o torn ./cmd/torn/`) and a
`TORN_API_KEY` (env or `.env`). Takes a minute or two — it pages through the full
faction crime history with a deliberate sleep to stay under the Torn rate limit.

To open the dashboard on someone else's data by default:
`CPR_DEFAULT_MEMBER="SomeName" .agents/skills/cpr-dashboard/generate_cpr_dashboard.sh`

## Pipeline (what the script does)

1. `torn faction members` → `data/member_names.json` (current id→name map).
2. `torn faction crimes --cat all` paged → `data/oc_cache.json` (every crime, deduped).
3. Collect participant ids seen in crimes but no longer in the faction →
   `data/unknown_ids.json`, then resolve them via `torn user profile` →
   `data/resolved_names.json` (only fetches ids not already resolved).
4. Build `BY_MEMBER`: one record per filled slot in an **executed** crime
   `{name, difficulty, role, cpr, t, status, id}`, keyed by member name →
   `data/oc_by_member.json`.
5. Inject the blob into `cpr_dashboard_template.html` (replacing the `__BY_MEMBER__`
   token and setting `DEFAULT_MEMBER`) → `generated/cpr_dashboard.html`.

## What `status` is (important)

The record's `status` is the **crime-level** outcome — the crime's top-level
`status` field, one of `Successful` / `Failure` / `Expired`. The dashboard dims
points where `status === "Failure"`; `Expired` crimes never executed (no checkpoint
data) and are skipped. This is **not** the per-slot `slots[].user.outcome` field,
which is a richer per-participant result (`Successful` / `Failed` / `Jailed` /
`Hospitalized` / `Injured`, plus `outcome_duration` and `item_outcome`). If you ever
want to color points by a member's personal fate rather than the crime's result,
that per-slot field is where to get it. Because crime-level `status` is served
durably for every crime (old ones included), a fresh fetch is complete on its own —
no cross-run accumulation needed.

## Files

| File | Role |
|------|------|
| `generate_cpr_dashboard.sh` | Orchestrator — run from anywhere, writes `generated/cpr_dashboard.html` |
| `cpr_dashboard_template.html` | D3 dashboard with a `__BY_MEMBER__` data placeholder |
| `data/oc_by_member.json` | Derived `BY_MEMBER` blob (regenerated each run) |
| `data/oc_cache.json` | Raw crime history cache |

`data/` and `generated/` are both gitignored — regenerable cache/config data and
build output, not source.
