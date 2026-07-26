#!/usr/bin/env python3
"""OC spawn planning report for a Torn faction leader.

Deterministically answers: which OC difficulty slots need to be spawned so
that every member who is free (or finishing an OC in the next 24h) has a
next OC ready?

Pipeline (do NOT reimplement this in ad-hoc scripts — run this file):
  1. Fetch planning crimes, recruiting crimes, and faction members (live).
  2. Load/refresh the executed-crimes cache (~/.torn_cache/) with a delta
     fetch (--from <max_executed_at> --filters executed_at), dedup by id,
     and keep only Successful/Failure crimes.
  3. Target members = free members (not in any planning/recruiting slot,
     excluding recruit-rank) + members whose planning OC is ready within 24h.
  4. Per-member CPR rubric on (difficulty, position, crime name) series.
  5. Demand vs open recruiting slots, with per-difficulty shortfalls.
  6. Position-fit check of open OCs at difficulties where demand exists.

Run from the repo root (needs ./torn):
  python3 .agents/skills/oc-spawning/oc_spawn_report.py
  python3 .agents/skills/oc-spawning/oc_spawn_report.py --recruit-positions "Recruit,Trainee"
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc_probability as ocp

CACHE = os.path.expanduser("~/.torn_cache/executed_crimes_cache.json")
BUMP_THRESHOLD = 82     # plateau/trend at or above this -> bump up a level
QUALIFY_THRESHOLD = 70  # below this the member doesn't qualify at that level
COMPLETING_WINDOW = 24 * 3600
MAX_DIFFICULTY = 10


# ---------------------------------------------------------------- fetching

def run_torn(args, retries=5, delay=10):
    """Run ./torn with retry on Torn rate-limit (error code 5)."""
    for attempt in range(retries):
        r = subprocess.run(["./torn"] + args, capture_output=True, text=True)
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            sys.exit(f"ERROR: torn {' '.join(args)} returned bad JSON: "
                     f"{r.stdout[:200]!r} stderr={r.stderr[:200]!r}")
        if isinstance(data, dict) and data.get("code") == 5:
            print(f"  rate limited, retry {attempt + 1}/{retries} in {delay}s...",
                  file=sys.stderr)
            time.sleep(delay)
            continue
        if isinstance(data, dict) and "error" in data:
            sys.exit(f"ERROR: torn {' '.join(args)}: {data['error']}")
        return data
    sys.exit("ERROR: rate limit retries exhausted")


def crimes_of(data):
    c = data.get("crimes", [])
    return list(c.values()) if isinstance(c, dict) else c


def load_executed_crimes():
    """Cache + delta fetch + dedup. Historical OCs never change once fired."""
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    existing = []
    last_executed = 0
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE))
        existing = cache.get("crimes", [])
        times = [c.get("executed_at") for c in existing if c.get("executed_at")]
        last_executed = max(times) if times else 0

    if last_executed == 0:
        print("No executed-crimes cache — full paginated fetch (may take a minute)...",
              file=sys.stderr)
        raw, page = [], 1
        while True:
            data = run_torn(["faction", "crimes", "--cat", "executed",
                             "--filters", "executed_at", "--page", str(page)])
            batch = crimes_of(data)
            if not batch:
                break
            raw.extend(batch)
            if not data.get("_metadata", {}).get("links", {}).get("next"):
                break
            page += 1
            print(f"  page {page - 1} done ({len(raw)} crimes)...", file=sys.stderr)
        new = raw
    else:
        # --from only works when paired with --filters executed_at.
        data = run_torn(["faction", "crimes", "--cat", "executed",
                         "--from", str(last_executed), "--filters", "executed_at"])
        new = [c for c in crimes_of(data)
               if (c.get("executed_at") or 0) > last_executed]
        print(f"Delta fetch: {len(new)} new executed crimes", file=sys.stderr)

    # Opportunistic enrichment via the third-party tornprobability.com API
    # (expected win probability from per-slot CPR). Best-effort only: any
    # failure (network, unexpected API shape) must never block the report.
    try:
        counts = ocp.enrich_crimes(new, limiter=ocp.RateLimiter(2.0))
        if counts:
            print(f"Win-probability enrichment: {counts}", file=sys.stderr)
    except Exception as e:
        print(f"NOTE: win-probability enrichment skipped ({e})", file=sys.stderr)

    # Dedup by id (delta boundaries overlap); prefer records with executed_at.
    by_id = {}
    for c in existing + new:
        cid = c.get("id")
        if cid is None:
            continue
        if cid not in by_id or (c.get("executed_at") and not by_id[cid].get("executed_at")):
            by_id[cid] = c
    all_crimes = list(by_id.values())
    json.dump({"fetched_at": int(time.time()), "crimes": all_crimes}, open(CACHE, "w"))

    # --cat executed does NOT filter by status; do it here.
    completed = [c for c in all_crimes if c.get("status") in ("Successful", "Failure")]
    print(f"Cache: {len(all_crimes)} crimes, {len(completed)} completed "
          f"(Successful/Failure)", file=sys.stderr)
    return completed


# ---------------------------------------------------------------- analysis

def slot_uid(slot):
    return slot.get("user_id") or (slot.get("user") or {}).get("id")


def strip_pos(p):
    return p.split(" #")[0] if p else p


def build_history(completed_crimes):
    """member_id -> {(difficulty, position, crime_name): [cpr, ...] chrono}."""
    hist = defaultdict(lambda: defaultdict(list))
    for c in sorted(completed_crimes, key=lambda c: c.get("executed_at") or 0):
        for s in c.get("slots", []):
            uid = slot_uid(s)
            if uid:
                key = (c.get("difficulty"), strip_pos(s.get("position", "")), c.get("name"))
                hist[uid][key].append(s.get("checkpoint_pass_rate", 0))
    return hist


def recommend(groups):
    """Apply the rubric to one member's series. Returns (difficulty, reason).

    Rubric (on the strongest series at the highest attempted difficulty):
      - plateaued/trending >= 82        -> bump up one level
      - >= 70, or climbing toward 82    -> stay at that level
      - < 70                            -> drop to highest level with a series >= 70
      - no history                      -> difficulty 1
    Never average CPR across crime types — each (position, crime name) series
    is independent.
    """
    if not groups:
        return 1, "no OC history — start at difficulty 1"
    top_diff = max(k[0] for k in groups)
    key, vals = max(((k, v) for k, v in groups.items() if k[0] == top_diff),
                    key=lambda kv: kv[1][-1])
    last = vals[-1]
    recent = vals[-3:]
    label = f"{key[1]} @ {key[2]} d{top_diff}, recent CPR {recent}"

    plateaued = len(vals) >= 3 and all(v >= BUMP_THRESHOLD for v in recent)
    trending_up = (len(vals) >= 3 and last >= BUMP_THRESHOLD
                   and recent[0] <= recent[1] <= recent[2])
    if plateaued or trending_up:
        return min(top_diff + 1, MAX_DIFFICULTY), f"bump up — {label}"
    if last >= BUMP_THRESHOLD:
        # single high value, no trend support -> weak evidence, don't bump
        return top_diff, f"stay — {label} (high but no trend support yet)"
    if last >= QUALIFY_THRESHOLD:
        return top_diff, f"stay — {label}"
    qualified = [k[0] for k, v in groups.items() if v[-1] >= QUALIFY_THRESHOLD]
    if qualified:
        d = max(qualified)
        return d, f"drop to d{d} — best at d{top_diff} is {last} (<{QUALIFY_THRESHOLD})"
    return 1, f"drop to d1 — no series >= {QUALIFY_THRESHOLD} (best {last} at d{top_diff})"


def best_cpr_for_position(groups, difficulty, position, crime_name):
    """Best last-CPR for a (difficulty, position), preferring exact crime match."""
    exact = groups.get((difficulty, position, crime_name))
    if exact:
        return exact[-1], True
    candidates = [v[-1] for (d, p, _), v in groups.items()
                  if d == difficulty and p == position]
    if candidates:
        return max(candidates), False
    return None, False


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recruit-positions", default="Recruit",
                    help="comma-separated faction position names that cannot "
                         "join OCs (case-insensitive, default: Recruit)")
    args = ap.parse_args()
    recruit_positions = {p.strip().lower() for p in args.recruit_positions.split(",") if p.strip()}

    if not os.path.exists("./torn"):
        sys.exit("ERROR: ./torn not found — run from the repo root "
                 "(or via generate_oc_spawn_report.sh)")

    now = int(time.time())
    print(f"Reference time (wall clock): "
          f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}\n")

    planning = crimes_of(run_torn(["faction", "crimes", "--cat", "planning"]))
    recruiting = crimes_of(run_torn(["faction", "crimes", "--cat", "recruiting"]))
    members = run_torn(["faction", "members"]).get("members", [])
    completed = load_executed_crimes()
    history = build_history(completed)
    name_of = {m["id"]: m["name"] for m in members}

    # --- who is already in a slot, and which planning OCs finish within 24h
    in_slot = set()
    for c in planning + recruiting:
        for s in c.get("slots", []):
            uid = slot_uid(s)
            if uid:
                in_slot.add(uid)

    completing = {}  # member_id -> (crime name, ready_at)
    for c in planning:
        ra = c.get("ready_at")
        if ra and ra <= now + COMPLETING_WINDOW:
            for s in c.get("slots", []):
                uid = slot_uid(s)
                if uid:
                    completing[uid] = (c.get("name"), ra)

    recruits = [m for m in members if m.get("position", "").lower() in recruit_positions]
    recruit_ids = {m["id"] for m in recruits}

    targets = []  # (member dict, reason)
    for m in members:
        if m["id"] in recruit_ids:
            continue
        if m["id"] not in in_slot:
            targets.append((m, "free"))
        elif m["id"] in completing:
            cname, ra = completing[m["id"]]
            hrs = max(0, ra - now) // 3600
            targets.append((m, f"completing '{cname}' in ~{hrs}h"))

    print("=" * 78)
    print(f"TARGET MEMBERS ({len(targets)}: "
          f"{sum(1 for _, r in targets if r == 'free')} free, "
          f"{sum(1 for _, r in targets if r != 'free')} completing within 24h)")
    if recruits:
        print(f"Excluded recruit-rank members: "
              f"{', '.join(m['name'] for m in recruits)}")
    else:
        print(f"NOTE: no members matched recruit positions "
              f"({args.recruit_positions!r}). If the faction has recruit-rank "
              f"members under a different position name, re-run with "
              f"--recruit-positions.")
    print("=" * 78)

    demand = defaultdict(list)  # difficulty -> [names]
    for m, reason in targets:
        diff, why = recommend(history.get(m["id"], {}))
        demand[diff].append(m["name"])
        print(f"  {m['name']:<20} d{diff}  [{reason}]")
        print(f"      {why}")

    # --- demand vs open recruiting slots
    open_slots = defaultdict(int)      # difficulty -> count of empty slots
    open_ocs = defaultdict(list)       # difficulty -> [(crime, [open positions])]
    for c in recruiting:
        empty = [strip_pos(s.get("position", "")) for s in c.get("slots", [])
                 if s.get("user") is None]
        if empty:
            open_slots[c.get("difficulty")] += len(empty)
            open_ocs[c.get("difficulty")].append((c, empty))

    print()
    print("=" * 78)
    print("SLOTS NEEDED vs AVAILABLE")
    print("=" * 78)
    shortfalls = []
    for d in sorted(demand, reverse=True):
        names = demand[d]
        avail = open_slots.get(d, 0)
        if avail >= len(names):
            status = f"[{avail} available — covered]"
        else:
            status = f"[{avail} available — {len(names) - avail} SHORT]"
            shortfalls.append((d, len(names) - avail))
        print(f"  {len(names)} slot(s) @ diff {d} -> {', '.join(names)}  {status}")

    # --- position-fit check for open OCs at demanded difficulties
    print()
    print("=" * 78)
    print("POSITION FIT (open OCs at demanded difficulties)")
    print("  ✓ = CPR >= 70 in that position; ~ = CPR from a different crime")
    print("  type at that difficulty (approximate); ? = no history")
    print("=" * 78)
    for d in sorted(demand, reverse=True):
        if not open_ocs.get(d):
            continue
        for c, positions in open_ocs[d]:
            print(f"\n  {c.get('name')} d{d} (id={c.get('id')}) — open: "
                  f"{', '.join(positions)}")
            for name in demand[d]:
                uid = next((i for i, n in name_of.items() if n == name), None)
                groups = history.get(uid, {})
                parts, qualifies = [], False
                for pos in positions:
                    cpr, exact = best_cpr_for_position(groups, d, pos, c.get("name"))
                    if cpr is None:
                        parts.append(f"? {pos}")
                    else:
                        mark = "✓" if cpr >= QUALIFY_THRESHOLD else "⚠"
                        approx = "" if exact else "~"
                        parts.append(f"{mark} {pos} ({approx}{cpr})")
                        if cpr >= QUALIFY_THRESHOLD:
                            qualifies = True
                verdict = "can be placed" if qualifies else \
                    "NO qualifying position (or no history) in this OC"
                print(f"    {name:<20} {', '.join(parts)}  -> {verdict}")

    # --- final answer
    print()
    print("=" * 78)
    print("SPAWN RECOMMENDATION")
    print("=" * 78)
    if shortfalls:
        for d, n in sorted(shortfalls, reverse=True):
            print(f"  Spawn OC(s) providing at least {n} slot(s) at difficulty {d}")
    else:
        print("  No spawns strictly required by slot count — but check the")
        print("  position-fit section above: a member with no qualifying")
        print("  position in the open OCs still needs a different OC type.")


if __name__ == "__main__":
    main()
