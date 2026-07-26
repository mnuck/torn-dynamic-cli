---
name: oc-member-progression
description: >
  Analyze our Torn faction's organized-crime member movement over time. Use when the
  user asks who is moving up, whether people are progressing into higher OC
  difficulties, whether cohorts are the same people over time, asks for an
  individual member's OC journey/timeline graph, or asks who "leveled up" /
  hit a new personal-best difficulty recently (e.g. "did anyone level up this
  week", "who succeeded at a higher OC than they ever have before").
---

# OC Member Progression Skill

Working directory: the `torn-dynamic-cli` repo root. This skill reuses the OC
dashboard's updater, which lives alongside the dashboard file at
`.agents/skills/oc-dashboard/`. Run the Python snippets below from the repo root,
and note the two path constants they set up:

```python
import sys
OC_DIR = ".agents/skills/oc-dashboard"
sys.path.insert(0, OC_DIR)          # so `import update_data` resolves
DASHBOARD = f"{OC_DIR}/dashboard.html"
```

Use the **full 52-week dashboard window by default**. Read `dashboard.html`,
parse the embedded `const data = {...};`, and use `data.weekly[0].week` through
`data.weekly[-1].week` as the analysis window unless the user explicitly asks
for another date range.

## Core Definition

For each member, compute their **highest OC difficulty per active week** from
Torn crime slot data.

- Active week: a week where the member appears in at least one completed OC slot.
- Weekly level: max `crime.difficulty` across that member's filled slots that week.
- Cohort counts must count each member once per week at that highest weekly level.
- This matches the dashboard's "Weekly Participants by Highest OC Level" logic.

Do not infer member movement from the embedded dashboard counts alone; the
dashboard does not store member IDs. Fetch completed crime slots from Torn.

## Fetch Pattern

Use the existing `update_data.py` helpers. No item-price calls are needed.

```python
import json, re, sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, Counter
sys.path.insert(0, ".agents/skills/oc-dashboard")
import update_data

html = Path(".agents/skills/oc-dashboard/dashboard.html").read_text()
data = json.loads(re.search(r"^const data = (\{.*\});$", html, re.M).group(1))
weeks = [w["week"] for w in data["weekly"]]
start = datetime.fromisoformat(weeks[0]).replace(tzinfo=timezone.utc)
crimes = update_data.fetch_crimes_since(int(start.timestamp()))
```

Then build:

```python
user_weeks = defaultdict(dict)  # user_id -> week -> highest difficulty
for crime in crimes:
    ts = crime.get("executed_at") or crime.get("planning_at") or 0
    week = update_data.week_start(ts)
    if week not in weeks:
        continue
    diff = crime.get("difficulty") or 0
    for slot in crime.get("slots") or []:
        user_id = (slot.get("user") or {}).get("id")
        if user_id:
            user_weeks[user_id][week] = max(user_weeks[user_id].get(week, 0), diff)
```

## Movement Metrics

Report movement using several lenses, because one-week assignment variance can
look like promotion.

- `any upward step`: any active-week transition where current level > previous level.
- `ever above first`: max level observed > first observed level.
- `sustained above first`: highest level L above first with at least 3 active weeks
  at level L or higher.
- `net up`: last observed level > first observed level.
- `low-to-high special case`: first observed level d1-d5 and later d6+; report both
  peak d6+ and sustained d6+.

Also report transition counts: same/up/down between consecutive active weeks.

## Cohort Stability

When comparing groups such as `d6+` or `d1-d5`, use weekly sets based on highest
weekly level:

- d6+: `level >= 6`
- d1-d5: `1 <= level <= 5`

Useful outputs:

- weekly count min/max/mean/median
- unique people in window
- present in all weeks / 90% / 75% / half
- average prior-week retention
- average Jaccard overlap
- average joiners and leavers per week
- last 4 or last 8 week stability when relevant

## Names

Crime slot data has user IDs, not names. Resolve names only for IDs you present:

```python
profile = update_data.torn_get(f"/user/{uid}/profile").get("profile", {})
name = profile.get("name") or str(uid)
faction_id = profile.get("faction_id")
```

Our faction id is in `.env` as `TORN_FACTION_ID`. Use it when the user asks who
is still in the faction.

## Individual Journey Graphs

For "show me X's journey", resolve the user ID if needed, then render a small
SVG to `generated/<name>_journey.svg` and include it in the reply with Markdown
image syntax.

Graph conventions:

- X axis: dashboard weeks.
- Y axis: difficulty levels.
- Dot: highest OC level for that member that week.
- Connect active weeks with a line.
- Highlight d6+ zone for high-level members, or call out repeated high-level
  appearances for lower-level progression.
- State clearly whether the path is monotonic or wobbly.

Preferred summary fields:

- active weeks / total weeks
- first active level
- last active level
- peak level and first peak week
- weeks at d6+, d7+, d8 for high-level members
- weeks at d4/d5 or d5 for low-to-mid movers

## Weekly Level-Up Check

A specific, recurring query: "did anyone level up [in the last N days]?" —
meaning did any member *succeed* at a higher OC difficulty than the highest
difficulty they have ever *succeeded* at before, with the new success
falling inside the lookback window (default: last 7 days).

This is a personal-best-ever check, not a per-week-bucket check like the
movement metrics above — it needs full crime history per user, not just the
dashboard window, since someone's all-time best may have been set over a
year ago.

### Method

1. Fetch **all** completed crimes (not windowed) — full history is required
   to establish each member's true prior best:
   ```python
   import sys
   sys.path.insert(0, ".agents/skills/oc-dashboard")
   import update_data
   crimes = update_data.fetch_all_crimes()
   ```
2. Resolve names in one call via the faction members endpoint (cheaper than
   per-user `/user/{id}/profile` calls):
   ```python
   members = update_data.torn_get("/faction/members")
   names = {m["id"]: m["name"] for m in members["members"]}
   ```
3. For each user, collect `(executed_at_or_planning_at, difficulty, crime_id)`
   for crimes with `status == "Successful"`, sorted ascending by timestamp.
4. Walk the sorted list maintaining a running `prior_max` (starts at 0).
   **Update `prior_max` every time `diff > prior_max`, regardless of whether
   the entry falls inside or outside the lookback window.** This avoids
   double-flagging the same difficulty if a member hits it twice within the
   window — only the first occurrence of a new max counts as leveling up.
   ```python
   from collections import defaultdict
   from datetime import datetime, timedelta, timezone

   cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
   user_crimes = defaultdict(list)
   for crime in crimes:
       if crime.get("status") != "Successful":
           continue
       ts = crime.get("executed_at") or crime.get("planning_at") or 0
       if not ts:
           continue
       diff = crime["difficulty"]
       for slot in crime.get("slots", []):
           uid = (slot.get("user") or {}).get("id")
           if uid:
               user_crimes[uid].append((ts, diff, crime["id"]))

   leveled_up = []
   for uid, entries in user_crimes.items():
       entries.sort(key=lambda e: e[0])
       prior_max = 0
       for ts, diff, cid in entries:
           if diff > prior_max:
               if ts >= cutoff_ts:
                   leveled_up.append((uid, diff, prior_max, ts, cid))
               prior_max = diff
   ```
5. Report each leveled-up member once: name, new best difficulty, previous
   best (or "none (first OC)" if `prior_max == 0`), and the date.

### Gotchas

- Don't use the dashboard's embedded `weekly`/`byDifficulty` data for this —
  it's pre-aggregated and has no per-user identity.
- Don't limit the initial fetch to the lookback window — that would make
  every difficulty look like a "new best" since there'd be no prior history
  to compare against.
- Report the result inline as a markdown table (name / new best / previous
  best / date); no need to render a graph unless asked.

## Interpretation

Be careful with language:

- "sustained d5" means at least 3 active weeks at d5 or higher, not continuous d5.
- "moving up" can be broad movement, sustained movement, or net movement; label
  which one is being used.
- Prefer "progression with assignment wobble" when the timeline rises but has dips.
