---
name: racing-dashboard
description: >
  Refresh the Torn racing dashboard — the interactive racing_dashboard.html
  visualization of race finishes, podiums, and per-track/per-car performance over
  time. Use this skill when the user wants to "refresh the racing dashboard",
  "rebuild the racing charts", "update racing_dashboard.html", "regenerate the race
  standings visualization", or pull the latest race results into that dashboard.
---

# Racing Dashboard

Regenerates `racing_dashboard.html` (written to repo root): a self-contained D3
visualization of official race finishes — podium rates, finishing positions, and
performance broken out by track and by car, over time.

## How to refresh

```bash
.agents/skills/racing-dashboard/generate_racing_dashboard.sh
open racing_dashboard.html
```

The wrapper `cd`s to the repo root before invoking `python3 racing_dashboard.py`,
so the script's default bare-filename paths (`racing_dashboard.html`,
`cache_races.json`, `Racing.json`) resolve there.

It fetches new races from the Torn API and merges them into `cache_races.json`
(also at repo root), which preserves history beyond Torn's ~6-month API retention
window. Keep that cache file around between runs.

### Forwarding flags

Anything you pass to the wrapper is forwarded to `racing_dashboard.py`:

```bash
.agents/skills/racing-dashboard/generate_racing_dashboard.sh --no-fetch
.agents/skills/racing-dashboard/generate_racing_dashboard.sh --output other.html
```

Useful flags:
- `--no-fetch` — rebuild the HTML from the existing cache only (no API calls).
- `--output FILE` / `--cache FILE` — override the default paths (relative to repo root).
- `--events FILE` — event-log path (defaults to `Racing.json`; see note below).
- `--key KEY` — override `TORN_API_KEY`.

## ⚠️ Note on Racing.json (manual refresh required)

`Racing.json` is an **optional event log** the script reads via `--events` (defaults
to `Racing.json` at repo root) to extend podium history further back than the API
cache reaches. It is **NOT** fetched automatically — you refresh it **manually** by
exporting from **https://torn.report**. The export's top-level key varies (e.g.
`cat116`, `log8731`); the loader just takes the first key, so the exact name doesn't
matter.

If `Racing.json` is missing or stale the dashboard still builds — it just won't
include the extra historical finishes from that export. So when you want the longest
possible history, re-export from torn.report first, drop it in at the repo root as
`Racing.json`, then run the generator.

## Files

| File | Location | Role |
|------|----------|------|
| `generate_racing_dashboard.sh` | this skill folder | Wrapper: `cd`s to repo root, forwards args to `python3 racing_dashboard.py` |
| `racing_dashboard.py` | this skill folder | Self-contained generator. Fetch → cache → build HTML |
| `cache_races.json` | repo root | Local race cache; preserves history past API retention — keep between runs |
| `cars.json` | repo root | Per-car display config (name/color/shape), keyed by car_id; edit names here to relabel cars (e.g. give each Edomondo NSX a distinct nickname) — keep between runs |
| `Racing.json` | repo root | Optional torn.report event-log export; **manually refreshed** (see note) |
| `racing_dashboard.html` | repo root | Generated output |

> Note: `*.py` is gitignored at the repo level, but `.gitignore` has a `!` exception
> for `.agents/skills/**/*.py` so `racing_dashboard.py` *is* tracked with the skill.
