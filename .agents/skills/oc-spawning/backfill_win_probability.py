#!/usr/bin/env python3
"""One-time(-ish) backfill: enrich cached executed OCs with an expected
success probability from the unofficial tornprobability.com API.

Idempotent — crimes that already carry "oc_success_probability" are
skipped, so re-running only fills in what's new (recently executed crimes,
or crimes that were previously unsupported/incomplete and might now
qualify). Rate-limited to 2 requests/sec against the third-party API and
saves progress periodically so an interrupted run doesn't lose work.

Run from anywhere:
  python3 .agents/skills/oc-spawning/backfill_win_probability.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc_probability as ocp

CACHE = os.path.expanduser("~/.torn_cache/executed_crimes_cache.json")
SAVE_EVERY = 25


def main():
    if not os.path.exists(CACHE):
        sys.exit(f"ERROR: no cache at {CACHE} — run the oc-spawning report "
                  f"at least once first to build it")

    cache = json.load(open(CACHE))
    crimes = cache.get("crimes", [])
    eligible = [c for c in crimes
                if c.get("status") in ("Successful", "Failure")
                and "oc_success_probability" not in c]
    print(f"{len(crimes)} crimes cached, {len(eligible)} eligible for enrichment",
          file=sys.stderr)
    if not eligible:
        print("Nothing to do.", file=sys.stderr)
        return

    limiter = ocp.RateLimiter(2.0)
    state = {"since_save": 0, "done": 0, "start": time.time(), "counts": {}}

    def on_each(_crime, status):
        state["done"] += 1
        state["counts"][status] = state["counts"].get(status, 0) + 1
        state["since_save"] += 1
        if state["since_save"] >= SAVE_EVERY:
            json.dump(cache, open(CACHE, "w"))
            state["since_save"] = 0
        if state["done"] % 50 == 0 or state["done"] == len(eligible):
            print(f"  [{state['done']}/{len(eligible)}] {state['counts']}",
                  file=sys.stderr)

    counts = ocp.enrich_crimes(eligible, limiter=limiter, on_each=on_each)

    json.dump(cache, open(CACHE, "w"))
    elapsed = time.time() - state["start"]
    print(f"\nDone in {elapsed:.0f}s: {counts}", file=sys.stderr)


if __name__ == "__main__":
    main()
