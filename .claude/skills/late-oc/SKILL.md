---
name: late-oc
description: Use this skill when the user asks about late, delayed, or stuck organized crimes (OCs) in the Torn game — e.g. "which OC is late?", "why hasn't the OC started?", "who is blocking the OC?", "find the late OC", "investigate the OC delay", "who delayed the OC?". Also use when the user wants to look back at OCs that were late in the past. Guides a two-phase investigation to identify who was absent from Torn when an OC became ready, using live API data and BigQuery (or user-provided CSV) of historical member status tracking.
---

# Late OC Investigation

All `./torn` commands must be run from `/Users/mnuck/torn-dynamic-cli`.

You're helping a Torn faction leader build a case for who delayed an organized crime. Being outside of Torn when an OC is ready to fire is against faction rules. There are two questions to answer:
1. **Right now**: which OC is late, and who is currently blocking it?
2. **At the moment it went live**: who was absent from Torn when the OC first became ready?

**How OCs fire:** OCs trigger **automatically** the moment `ready_at` arrives — there is no manual execute step and no button to push. The only requirement is that every member is in Torn (status "Okay") at that moment. If anyone is Abroad, Traveling, in Hospital, or in Jail when `ready_at` hits, the OC is delayed until they return.

---

## Phase 1: Find late OCs

Use the built-in CLI report command:

```bash
# Currently late OCs (with member status and blocker identification)
./torn report late-ocs

# Historical lookback (includes completed OCs that were late, with 5min+ delay)
./torn report late-ocs --hours 24
./torn report late-ocs --hours 48
```

The command handles everything: fetching crimes, filtering out Recruiting, identifying blockers, looking up member names and current status in parallel, and formatting a summary table.

For currently-late OCs it shows a full table with position, item availability, current status, and last active time — with blockers (Abroad, Hospital, Jail, Traveling) marked with ▶.

**Note on progress:** The "progress" percentage on OC slots is just a countdown timer — it ticks to 100% on its own regardless of what the member does. It is NOT meaningful for determining who is blocking an OC. The only thing that matters is whether the member is **in Torn** (status "Okay") when ready_at hits.

For historical OCs it shows the delay duration and member list.

From here, pick the OC(s) to investigate and proceed to Phase 2.

---

## Phase 2: Who was absent at ready time

The user has automation that polls faction member statuses every ~5 minutes and logs **status changes** to a tracking system. Important: the tracker logs *changes*, not periodic snapshots — a member who stays "Okay" for hours won't generate any rows during that time.

### Data source: BigQuery (preferred)

Try BigQuery first. The data lives in `torn-willie.torn_rw_stats.state_changes` with this schema:

| Column | Type |
|--------|------|
| `timestamp` | TIMESTAMP |
| `member_id` | STRING |
| `member_name` | STRING |
| `faction_id` | STRING |
| `faction_name` | STRING |
| `last_action_status` | STRING |
| `status_description` | STRING |
| `status_state` | STRING |
| `status_until` | TIMESTAMP |
| `status_travel_type` | STRING |

The table is partitioned by `timestamp` and clustered by `faction_id, member_id`.

Use the BigQuery MCP tools (`mcp__4f9cd1a3-be42-4e88-888a-bc64c2bdee09__execute_sql`) with `projectId: "torn-willie"`.

#### Query: find each member's status at ready time

For each OC member, find the **last status change before `ready_at`** — this tells you their state when the OC went live:

```sql
SELECT member_name, status_state, status_description, status_travel_type, timestamp
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY member_name ORDER BY timestamp DESC) AS rn
  FROM `torn-willie.torn_rw_stats.state_changes`
  WHERE member_name IN ('Name1', 'Name2', 'Name3')
    AND timestamp <= TIMESTAMP_SECONDS(<ready_at_unix>)
    AND timestamp >= TIMESTAMP_SECONDS(<ready_at_unix> - 86400)
)
WHERE rn = 1
ORDER BY member_name
```

If a member has **no rows** returned, BigQuery doesn't have enough history — their last status change happened before data collection started. Fall back to CSV.

### Fallback: user-provided CSV

If BigQuery has insufficient data (no rows for some members, or the OC predates data collection), ask the user for a CSV export.

Give the user what they need to filter their export:
1. **Member names** (not IDs — look these up via `./torn user profile --id` first)
2. **UTC time range** — suggest starting ~24 hours before `ready_at` through execution time (or current time if still late). A wide window ensures you capture the last status change for members who were stable for a long time.

Example prompt:
> "Could you export a CSV from your tracking data for **ladyME, EMI97, perkyguy** covering **2026-03-16 12:00 UTC → 2026-03-17 18:00 UTC**?"

### Parsing the CSV

The CSV may or may not have headers. The columns match the BigQuery schema above (same names, same order). Timestamps are **UTC**. Handle both cases:

```python
import csv
from datetime import datetime, timezone

ready_at = <unix_timestamp>
ready_dt = datetime.fromtimestamp(ready_at, tz=timezone.utc).replace(tzinfo=None)

cols = ["Timestamp","Member ID","Member Name","Faction ID","Faction Name",
        "Last Action Status","Status Description","Status State","Status Until",
        "Status Travel Type"]

with open("path/to/file.csv") as f:
    reader = csv.reader(f)
    first_row = next(reader)
    # Check if first row is a header
    if first_row[0] == "Timestamp":
        rows = [dict(zip(cols, row)) for row in reader]
    else:
        rows = [dict(zip(cols, first_row))] + [dict(zip(cols, row)) for row in reader]

for member_id, name, position in members:
    member_rows = [r for r in rows if r["Member ID"] == member_id]
    before = [r for r in member_rows
              if datetime.strptime(r["Timestamp"], "%Y-%m-%d %H:%M:%S") <= ready_dt]
    after  = [r for r in member_rows
              if datetime.strptime(r["Timestamp"], "%Y-%m-%d %H:%M:%S") >  ready_dt]
    last_before = before[-1] if before else None
    first_after = after[0] if after else None
```

### Handling gaps (either data source)

If a member has **no rows before ready_at**, the data doesn't go back far enough — their last status change happened before tracking started or before the export window. Ask the user for a wider CSV export. Don't assume absence.

### Final report

For each member, state clearly:
- **In Torn** (Status State = "Okay") or **Absent** (Traveling, Abroad, Hospital, Jail) at the moment the OC became ready
- If absent: what exactly they were doing and where

The goal: "At the moment this OC went live, X, Y, Z were in Torn and ready, but **coolcookie123 was abroad in the United Kingdom**."

---

## Phase 3: Predictive — OCs that will be late

When the user asks "are there any OCs in danger of being late?" or any similar open-ended question about upcoming OCs, **always run Phase 3** — don't stop at Phase 1. Phase 1 only finds already-late OCs; Phase 3 catches ones about to become late.

When checking planning OCs:
- Run `./torn faction crimes --cat planning` and parse the **full** response — never truncate the output. There can be many OCs.
- Sort by `ready_at` ascending to find the soonest ones first.
- Check member statuses for any OC whose `ready_at` is within the next ~6 hours.

Save the output to a file and parse it with Python:

```bash
./torn faction crimes --cat planning > /tmp/planning_crimes.json
```

```python
import json, datetime

with open('/tmp/planning_crimes.json') as f:
    data = json.load(f)

# IMPORTANT: use datetime.now(timezone.utc).timestamp() — NOT utcnow().timestamp()
# utcnow() returns a naive datetime; .timestamp() interprets it as local time, giving
# a wrong Unix timestamp if the machine is not UTC. This bug makes OCs appear late
# or early by the local timezone offset.
now = datetime.datetime.now(datetime.timezone.utc).timestamp()
cutoff = now + 6 * 3600  # 6 hours from now

soon = []
for crime in data['crimes']:
    ready_at = crime.get('ready_at')
    if ready_at and ready_at <= cutoff:
        dt = datetime.datetime.fromtimestamp(ready_at, tz=datetime.timezone.utc)
        mins_away = (ready_at - now) / 60
        member_ids = [s['user']['id'] for s in crime.get('slots', []) if s.get('user')]
        soon.append((mins_away, crime['id'], crime['name'], dt.strftime('%H:%M UTC'), member_ids))

soon.sort()
for mins, cid, name, dt, mids in soon:
    h, m = divmod(int(abs(mins)), 60)
    sign = 'in' if mins >= 0 else 'PAST'
    print(f'{name} (id={cid}) — {sign} {h}h{m:02d}m at {dt} — members: {mids}')
```

**Note on expired OCs:** OCs with `expired_at` < `ready_at` represent crimes where a member joined during planning and then left before the crime became viable. These appear in API results but are **not real late OCs** — ignore them in penalty investigations.

**Note on server lag:** Torn sometimes takes up to ~30 seconds to execute a crime after `ready_at`. A delay that small is server processing, not a member violation. Don't penalize for it.

1. Fetch the OC details (from `./torn faction crimes --cat planning`) to get `ready_at` and member list
2. Look up each member's current status via `./torn user profile --id <id>`
3. For any member who is **Abroad** or **Traveling**, estimate whether they can make it back in time

### Travel time reference (from wiki, memorized in project memory)

Use the **business class** time as the absolute minimum (fastest possible return). If a member is abroad and cannot physically return even at business class speed before `ready_at`, the OC **will** be late.

Key business class return times (fastest possible):
- Mexico: 8min
- Cayman Islands: 11min
- Canada: 12min
- Hawaii: 40min
- United Kingdom: 48min
- Argentina: 50min
- Switzerland: 53min
- Japan: 1h 8min
- China: 1h 12min
- UAE: 1h 21min
- South Africa: 1h 29min

Standard (slowest) return times:
- Mexico: 26min
- Cayman Islands: 35min
- Canada: 41min
- Hawaii: 2h 14min
- United Kingdom: 2h 39min
- Argentina: 2h 47min
- Switzerland: 2h 55min
- Japan: 3h 45min
- China: 4h 02min
- UAE: 4h 31min
- South Africa: 4h 57min

These are one-way times. A member who is Abroad must also *start* the return trip — they aren't traveling yet. A member whose status is "Traveling" and description says "Returning to Torn from X" is already en route.

### Determining flight class from data

**Key rule:** In Torn, flights can only go to and from Torn (no city-to-city). The flight class used outbound is always the same class used inbound. So if BigQuery has data on a member's outbound flight to a destination, you can measure the travel duration and compare it to the known standard/business/airstrip times to determine their flight class. Then use that same class to estimate the return time.

Example: if a member's status changed from "Okay" → "Traveling to South Africa" at 01:00, and then "Abroad — In South Africa" at 05:57, that's ~4h 57m, which matches the standard time (4h 57m). So their return will also be standard (4h 57m).

Query to find outbound flight duration:
```sql
SELECT timestamp, status_state, status_description
FROM `torn-willie.torn_rw_stats.state_changes`
WHERE member_name = 'MemberName'
ORDER BY timestamp DESC
LIMIT 20
```
Look for the transition from "Traveling" → "Abroad" (arrival) and work backwards to find when they departed ("Okay" → "Traveling").

### Prediction logic

- **Abroad + not yet traveling back**: Earliest return = now + business class time for that country. If that's after `ready_at`, the OC **will** be late. Report the range: "will be late by between X (business class) and Y (standard) unless they leave now." If BigQuery has their outbound flight data, determine the actual flight class and give a precise estimate instead of a range.
- **Traveling + returning**: They're already en route. Check BigQuery for when they started the return trip, determine their flight class (from outbound data if available), and calculate estimated arrival = departure time + flight duration for their class.
- **Traveling + outbound** ("Traveling to X"): They haven't even arrived yet. Return is impossible before they arrive, spend time abroad, and fly back. The OC will almost certainly be late.
- **Hospital/Jail abroad**: Even worse — they need to wait out hospital/jail time, THEN fly back (unless they work at 5* Logistics Management, which allows traveling home while hospitalized).

### Report format for predictions

> **First Aid and Abet** (id=1411404) — ready in 4h at 05:57 UTC
> - Firethem (Picklock): ⚠ **Abroad in South Africa** — even at business class speed (1h 29m), they need to leave within the next 2h 31m. Currently inactive for 6h. **High risk of delay.**
> - Deador (Decoy): ✓ Okay
> - Cathsuuup (Pickpocket): ✓ Okay
