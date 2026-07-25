# data/

Working set for the analysis skills: fetched API dumps, telemetry pulls, and a
couple of manual exports. **The data itself is not tracked in git** — it is tens
of megabytes of other players' game records, and this repo is public. Only the
fetch scripts and this README are tracked.

`.gitignore` drops `data/**/*.{json,jsonl,csv,log}` at any depth, so a new dump
placed anywhere under `data/` stays local by default. If you ever need to track
something here, add an explicit `!` exception and say why.

A fresh clone therefore has an empty `data/`. Repopulate only what the skill you
are running actually needs — the table below says how.

## Layout

| Path | What it is | How to (re)create it |
|---|---|---|
| `oc_cache.json` | Every organized crime the faction has attempted, deduped by id, sorted by `created_at` | `./data/fetch_oc_cache.sh` (pages `/faction/crimes` with a 1.5 s sleep — deliberately not `--all`) |
| `oc_by_member.json`, `member_names.json`, `unknown_ids.json` | OC history pivoted per member, plus the name lookup and the ids that failed to resolve | Derived from `oc_cache.json` by the `oc-spawning` / `oc-member-progression` skills |
| `resolved_names.json` | Names for ex-faction OC participants no longer in `/faction/members` | `./data/resolve_names.sh` (reads `unknown_ids.json`, paced at 1.2 s/call) |
| `cars.json`, `track_paths.json` | Car stats and track geometry used by the racing skills | Hand-maintained reference data — **not refetchable**, back these up |
| `Racing.json` | Extended race history | Manual export from torn.report, **not** auto-fetched |
| `*_telemetry.json` | Per-track segment telemetry (16 tracks) used by `fast-band-delta` and the racing model | Fetched per track by the `fast-band-delta` skill; see its SKILL.md |
| `*_100lap_*.json` | Long-run single-race pulls kept for tail/record analysis | Refetch by raceID via the racing skills |
| `alias23_*.json` | An independent driver's race log, used to validate the two-coin race model without fitting to it | Fetched once for validation; regenerate only if the model changes |
| `cache_races.json` | Rolling cache of the user's own races | Written by the racing skills |
| `cache/war_attacks_<warid>.json` | Raw ranked-war attack log (~10 k records, ~6 MB) | `war_dashboard.py --cache data/cache/war_attacks_<id>.json`. A finished war is immutable, so this never needs invalidating |
| `war_report_<id>.json`, `war_incoming_<id>.json`, `war_payout_<id>.csv` | Per-war derived reports and the payout sheet | `war-dashboard` skill |
| `market-snapshots/prices.jsonl`, `capture.log` | Item-market price series, one JSON object per line | Appended every 30 min by the `deploy/` CronJob; pull down from the cluster PVC |

## Scripts

Both scripts `cd` to the repo root and expect the `torn` binary to be built
there (`go build -o torn ./cmd/torn/`).

- `fetch_oc_cache.sh` — full faction OC history into `oc_cache.json`.
- `resolve_names.sh` — resolve `unknown_ids.json` into `resolved_names.json`.
