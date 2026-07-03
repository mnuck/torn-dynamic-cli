---
name: oc-spawning
description: >
  Daily OC spawn planning for a Torn faction leader. Use this skill when the user
  wants to know which OC difficulty slots need to be spawned, which members need
  a next OC, or whether newly spawned OCs cover everyone. Triggers on phrases like
  "what OCs do I need to spawn", "do I need to spawn any OCs", "does that cover it",
  "what difficulty for the people finishing soon", "plan OCs for the next 24 hours",
  or any request to figure out what organized crimes to create for faction members
  who are free or about to finish their current OC.
---

# OC Spawn Planning

You're helping a Torn faction leader figure out which OC difficulty slots to spawn so that every member who needs one has a next OC ready. Run this once or twice a day.

All `./torn` commands run from `/Users/mnuck/torn-dynamic-cli`.

---

## Phase 1: Gather data

Fetch live data (run these in parallel — they change frequently):
```bash
./torn faction crimes --cat planning > /tmp/planning_crimes.json
./torn faction crimes --cat recruiting > /tmp/recruiting_crimes.json
./torn faction members > /tmp/faction_members.json
```

**Executed crimes — use the cache with incremental fetches.** Historical OC data never changes once an OC fires. Use `--from <max_executed_at> --filters executed_at` for efficient delta fetches — this returns only crimes that fired since the last cache entry, not the full dataset.

**Important:** `--from` only works correctly when paired with `--filters executed_at`. Without `--filters`, it uses a different default sort field and returns near the full dataset. Always use both together.

```python
import json, os, time, subprocess

CACHE = os.path.expanduser('~/.torn_cache/executed_crimes_cache.json')
os.makedirs(os.path.dirname(CACHE), exist_ok=True)

if os.path.exists(CACHE):
    cache = json.load(open(CACHE))
    existing = cache['crimes']
    # Use the latest executed_at in cache as the delta boundary
    exec_times = [c.get('executed_at') for c in existing if c.get('executed_at')]
    last_executed = max(exec_times) if exec_times else 0
else:
    existing = []
    last_executed = 0

def run_torn(args, cwd='/Users/mnuck/torn-dynamic-cli', retries=5, delay=10):
    """Run a torn command with retry on rate-limit (code 5)."""
    import time
    for attempt in range(retries):
        r = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Bad JSON: {r.stdout[:200]}")
        if data.get('code') == 5:
            print(f"Rate limited, retrying in {delay}s... (attempt {attempt+1}/{retries})")
            time.sleep(delay)
            continue
        return data
    raise RuntimeError("Rate limit retries exhausted")

if last_executed == 0:
    # First run — full paginated fetch with rate-limit handling
    print("No cache found — doing full fetch (this may take a minute)...")
    all_raw = []
    page = 1
    while True:
        data = run_torn(['./torn', 'faction', 'crimes', '--cat', 'executed',
                         '--filters', 'executed_at', '--page', str(page)])
        crimes_page = data.get('crimes', [])
        if isinstance(crimes_page, dict):
            crimes_page = list(crimes_page.values())
        if not crimes_page:
            break
        all_raw.extend(crimes_page)
        meta = data.get('_metadata', {})
        if not meta.get('links', {}).get('next'):
            break
        page += 1
        print(f"  Fetched page {page-1} ({len(all_raw)} crimes so far)...")
    new_crimes = [c for c in all_raw if c.get('status') in ('Successful', 'Failure')]
    print(f"Full fetch: {len(new_crimes)} completed crimes")
else:
    # Delta fetch — only crimes that fired since last cache entry
    data = run_torn(['./torn', 'faction', 'crimes', '--cat', 'executed',
                     '--from', str(last_executed), '--filters', 'executed_at'])
    raw = data.get('crimes', [])
    if isinstance(raw, dict): raw = list(raw.values())
    new_crimes = [c for c in raw if c.get('executed_at', 0) > last_executed]
    print(f"Delta fetch: {len(new_crimes)} new crimes since last run")

all_crimes = existing + new_crimes

# DEDUP GUARD: collapse to one record per crime id. Delta fetches can overlap
# (the boundary crime reappears, and occasional re-fetches double up), which
# silently inflated the cache to ~73% duplicates once. Keep the record that has
# executed_at when there's a conflict. Always dedup before writing.
by_id = {}
for c in all_crimes:
    cid = c.get('id')
    if cid is None:
        continue
    if cid not in by_id or (c.get('executed_at') and not by_id[cid].get('executed_at')):
        by_id[cid] = c
all_crimes = list(by_id.values())

cache = {'fetched_at': int(time.time()), 'crimes': all_crimes}
json.dump(cache, open(CACHE, 'w'))
print(f"Cache: {len(all_crimes)} unique crimes")
```

Then work from `cache['crimes']` for CPR analysis. First run does a full fetch (can take a minute); subsequent runs only pull the tiny delta. The dedup guard keeps the cache clean even if a fetch overlaps — counts won't balloon again.

**Who needs a slot?** There are two groups:

1. **Free members** — faction members not currently in any planning or recruiting OC slot, excluding anyone in recruit rank (recruits can't join OCs). Ask the leader if you're unsure who is recruit status.

2. **Completing members** — members in planning OCs whose `ready_at` is within the next 24 hours. These people will be free soon and need their next OC ready.

**Target members** = free + completing (deduplicated). Planning and recruiting crime slots only contain user IDs, not names — cross-reference with faction members to get names.

---

## Phase 2: Determine recommended difficulty for each member

**CPR is deterministic, not noisy — but it's keyed on (position, crime name), not just position.** The same position label (e.g. "Engineer") appears across different OC crime types, and each crime type exercises different hidden variables — a member's CPR trajectory in "Engineer @ No Reserve" is independent of their trajectory in "Engineer @ Guardian Ángels." Collapsing multiple crime types into one position-level series manufactures the *appearance* of noise (a flat/bouncing read) when each individual (position, crime name) series is actually cleanly monotonically increasing. **Always split by (position, crime name) before judging a trend — never aggregate across crime types.**

For each target member, scan the executed crimes history, strip position suffixes (e.g. "Muscle #1" → "Muscle"), and group by `(difficulty, position, crime name)`. Within each group, sort chronologically and look at the trend, not just a flattened max:

- **Recent runs plateaued at/above 82** (e.g. last 3+ runs holding steady high) → strong bump case, this is a skill ceiling reached.
- **Monotonically climbing but hasn't cleared 82 yet** → not yet a bump case on that series alone, but note the trajectory — a member can be climbing on multiple series simultaneously and some series may already be over threshold while others aren't. Read the member's *best* series, not the average across series.
- **A single high value with no trend support (small sample, no climb)** → weak evidence, don't bump on this alone.

**The rubric** (apply per member, using their strongest position+crime series at their highest attempted difficulty):

| Situation | Recommendation |
|-----------|---------------|
| Best series is plateaued or trending ≥ 82 | Bump up one level |
| Best series sits ≥ 70 but < 82, or is still climbing toward 82 without having reached it | Stay at that level |
| Best series < 70 | Drop to the highest level where a series shows ≥ 70 |
| No history at all | Default to difficulty 1 |

Don't average CPR across different crime types at a difficulty — that's the mistake that flattens real, independent growth curves into false noise.

---

## Phase 3: Compare demand vs available slots

Count how many people need each difficulty level. Check recruiting crimes for open slots (slots with no user) by difficulty. The leader spawns OCs in bands — **report slot shortfalls, not OC counts**, since the leader doesn't control exact OC types within a band.

**Report format:**

```
Slots needed (N members: X completing + Y free):
  2 slots @ diff 8  → DarkEdge, Orochi              [0 available — SHORT]
  4 slots @ diff 7  → CaptainChris, Cbatt, ...       [1 available — 3 SHORT]
  5 slots @ diff 6  → ...                            [39 available — covered]
  ...
```

Only list difficulties where at least one member needs a slot.

---

## Phase 4: Position-fit verification

When the leader says they've spawned new OCs and asks if they're covered, **don't just recount slots** — verify that specific positions in the new OCs actually match member strengths.

For each newly available OC:
1. Get its position list from the recruiting crimes
2. For each member assigned to that difficulty, look up their best CPR per position at that difficulty from executed crimes
3. Flag positions where best CPR < 70 with ⚠
4. Explicitly state whether each member has at least one qualifying position (≥ 70) in that OC

A member may be right for a difficulty band overall but have sub-70 CPR in every specific position that a particular OC offers — that OC type is wrong for them regardless of slot count.

**Report format per OC:**

```
Clinical Precision d8 (id=1659310) — Imitator, Cat Burglar, Assassin, Cleaner
  DarkEdge:  ✓ Assassin (74), ✓ Imitator (73), ⚠ Robber (66), ⚠ Muscle (66)
  Orochi:    ✓ Assassin (72), ✓ Imitator (71), ⚠ Muscle (63)
  → Both can be placed ✓

Break the Bank d8 (id=1659293) — Robber, Muscle, Thief
  DarkEdge:  ⚠ Robber (66), ⚠ Muscle (66), ⚠ Thief (67)
  Orochi:    ⚠ Robber (64), ⚠ Muscle (63), ⚠ Thief (66)
  → Neither can be placed — wrong OC type, needs Assassin or Imitator slots
```

---

## Key gotchas from real usage

- **Planning/recruiting API responses don't include member names** — only IDs. Always cross-reference with the faction members endpoint.
- **Slot user IDs are nested**: `slot['user']['id']`, NOT `slot['user_id']`. Always extract with a helper: `uid = slot.get('user_id') or (slot.get('user') or {}).get('id')`
- **`checkpoint_pass_rate` is a plain integer**, not a dict with passed/total fields.
- **Recruit-rank members cannot join OCs** — exclude them from the target list. The leader will confirm who these are.
- **Don't use the "executing" crimes category** for current slots — it returns historical completed OCs, same as "executed".
- **`--cat executed` does NOT filter by status** — it returns crimes of ALL statuses (Recruiting, Planning, Successful, Failure, Expired). Always filter in Python: `[c for c in crimes if c.get('status') in ('Successful', 'Failure')]`
- **`--from` requires `--filters executed_at`** — without `--filters`, `--from` uses a default sort field and returns near the full dataset. Always pair them: `--from <max_executed_at> --filters executed_at`. Delta fetches using `max(executed_at)` from the cache as the boundary work correctly.
- **Avoid `--all`** — it can trigger rate limits during long paginated fetches. For the initial full fetch, paginate manually using `--page` in a loop with rate-limit retry logic. Delta fetches never need `--all` since they return a single small page.
- **Slot count ≠ fit** — always run Phase 4 after spawns to catch position mismatches.
- **Always dedup the cache by crime `id` before writing** (the Phase 1 snippet does this). Overlapping delta fetches re-add the boundary crime, and once inflated the cache to ~73% duplicates — which silently skewed any count-based stat (late rates, blocker tallies). If a count ever looks 2–4× too big, dedup by `id` first.
