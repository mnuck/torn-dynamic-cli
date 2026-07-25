#!/usr/bin/env python3
"""
Fetch faction OC data from Torn API and embed it into dashboard.html.

Incremental update: on first run (or schema migration), does a full rebuild.
On subsequent runs, fetches only the current week's crimes at current item
prices and merges them into the frozen historical data already in the dashboard.
This prevents past weeks from being silently repriced as market values shift.

Usage:
    python3 update_data.py

Requires:
    - TORN_API_KEY env var or a .env file in this directory
    - dashboard.html in the same directory as this script
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:
    certifi = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_HTML = os.path.join(SCRIPT_DIR, "dashboard.html")
API_BASE = "https://api.torn.com/v2"
USER_AGENT = "torn-oc-dashboard/1.0"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where()) if certifi else None


def load_env_file(path):
    """Load KEY=value lines from a .env file, including named pipes."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


# Prefer the TORN_API_KEY env var; otherwise read the torn-dynamic-cli repo
# root .env. This script lives at .agents/skills/oc-dashboard/ within that repo,
# so the root is three levels up.
if not os.environ.get("TORN_API_KEY"):
    load_env_file(os.path.join(SCRIPT_DIR, "../../../.env"))

def api_key():
    key = os.environ.get("TORN_API_KEY")
    if not key:
        print("ERROR: TORN_API_KEY is required via env var or .env", file=sys.stderr)
        sys.exit(1)
    return key


def torn_get(path_or_url, params=None, retries=3):
    """Call Torn API v2 and return parsed JSON."""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        url = path_or_url
    else:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{API_BASE}{path_or_url}"
        if query:
            url = f"{url}?{query}"

    headers = {
        "Authorization": f"ApiKey {api_key()}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    request = Request(url, headers=headers)

    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(attempt * 5)
                continue
            print(f"HTTP error from Torn API: {e.code} {e.reason}", file=sys.stderr)
            print(body, file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            if attempt < retries:
                time.sleep(attempt * 5)
                continue
            print(f"Network error calling Torn API: {e.reason}", file=sys.stderr)
            sys.exit(1)

    if "error" in data:
        print(f"Torn API error: {data['error']}", file=sys.stderr)
        sys.exit(1)
    return data


def paged_torn_get(path, params):
    """Fetch all pages by following _metadata.links.next."""
    rows = []
    url = None
    while True:
        data = torn_get(url or path, params if url is None else None)
        rows.extend(data.get("crimes", []))
        next_url = (((data.get("_metadata") or {}).get("links") or {}).get("next"))
        if not next_url:
            break
        url = urljoin(API_BASE, next_url)
    return rows


def dedup_crimes(crimes):
    seen = set()
    unique = []
    for crime in crimes:
        if crime["id"] not in seen:
            seen.add(crime["id"])
            unique.append(crime)
    return unique


def fetch_all_crimes():
    """Fetch all completed crimes from the Torn API."""
    print("Fetching all completed crimes...")
    crimes = dedup_crimes(paged_torn_get("/faction/crimes", {
        "cat": "completed",
        "limit": 100,
        "sort": "DESC",
    }))
    print(f"  {len(crimes)} unique crimes")
    return crimes


def fetch_crimes_since(ts):
    """Fetch completed crimes since a Unix timestamp."""
    dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    print(f"Fetching crimes since {dt_str}...")

    # Torn's _metadata.links.next is not currently populated for from-filtered
    # faction/crimes responses, so page manually by advancing the timestamp.
    rows = []
    seen = set()
    cursor = ts
    while True:
        page = torn_get("/faction/crimes", {
            "cat": "completed",
            "filters": "executed_at",
            "from": cursor,
            "limit": 100,
            "sort": "ASC",
        }).get("crimes", [])
        new_rows = [c for c in page if c.get("id") not in seen]
        for crime in new_rows:
            seen.add(crime.get("id"))
        rows.extend(new_rows)

        max_ts = max((c.get("executed_at") or c.get("planning_at") or 0) for c in page) if page else cursor
        if len(page) < 100 or max_ts <= cursor:
            break
        cursor = max_ts

    # Filter in Python too — keeps boundary behavior explicit.
    crimes = [c for c in rows if (c.get("executed_at") or c.get("planning_at") or 0) >= ts]
    crimes = dedup_crimes(crimes)
    print(f"  {len(crimes)} unique crimes")
    return crimes


def fetch_item_prices(crimes):
    """Fetch market prices for all unique item IDs found in rewards and consumed items."""
    item_ids = set()
    for crime in crimes:
        # Reward items
        rewards = crime.get("rewards") or {}
        for item in rewards.get("items") or []:
            if item.get("id"):
                item_ids.add(item["id"])
        # Consumed items: non-reusable requirements in filled slots
        for slot in crime.get("slots", []):
            req  = slot.get("item_requirement") or {}
            user = slot.get("user") or {}
            if req and not req.get("is_reusable", True) and user.get("id"):
                if req.get("id"):
                    item_ids.add(req["id"])

    if not item_ids:
        return {}

    ids_str = ",".join(str(i) for i in sorted(item_ids))
    print(f"  Fetching market prices for {len(item_ids)} unique item IDs...")
    data = torn_get(f"/torn/{ids_str}/items")
    prices = {}
    for item in data.get("items", []):
        mp = (item.get("value") or {}).get("market_price") or 0
        prices[item["id"]] = mp
    return prices


def week_start(ts):
    """Return the Monday of the week containing the given Unix timestamp (YYYY-MM-DD)."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def current_week_start():
    """Return a datetime for the start of the current week (Monday 00:00 UTC)."""
    now = datetime.now(tz=timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def day_str(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def crime_revenue(crime, prices):
    """Cash + market value of reward items."""
    rewards = crime.get("rewards") or {}
    money = rewards.get("money", 0) or 0
    item_value = sum(
        (prices.get(i["id"], 0) or 0) * (i.get("quantity", 1) or 1)
        for i in (rewards.get("items") or [])
        if i.get("id")
    )
    return money + item_value


def crime_person_days(crime):
    """Person-days of member commitment: filled slots × duration in days."""
    planning = crime.get("planning_at") or 0
    executed = crime.get("executed_at") or 0
    if not planning or not executed or executed <= planning:
        return 0.0
    duration_days = (executed - planning) / 86400
    filled_slots = sum(
        1 for slot in crime.get("slots", [])
        if (slot.get("user") or {}).get("id")
    )
    return filled_slots * duration_days


def crime_cost(crime, prices):
    """Market value of items consumed: non-reusable requirements in filled slots.

    item_outcome.outcome is unreliable (null for ~87% of consumed items in the
    Torn API). Instead we use item_requirement.is_reusable == False as the
    signal — if a slot is filled and its required item is non-reusable, it was
    consumed regardless of whether the crime succeeded or failed.
    """
    cost = 0
    for slot in crime.get("slots", []):
        req  = slot.get("item_requirement") or {}
        user = slot.get("user") or {}
        if req and not req.get("is_reusable", True) and user.get("id"):
            item_id = req.get("id")
            if item_id:
                cost += prices.get(item_id, 0)
    return cost


def build_weekly(crimes, prices):
    """Aggregate crimes into weekly buckets with per-difficulty breakdown.

    participantsByDiff counts each participant once per week at their highest
    difficulty level that week.
    """
    weeks = defaultdict(lambda: {
        "money": 0, "cost": 0, "crimes": 0, "wins": 0, "fails": 0,
        "byDiff":          {str(d): 0 for d in range(1, 9)},
        "costByDiff":      {str(d): 0 for d in range(1, 9)},
        "countByDiff":     {str(d): 0 for d in range(1, 9)},
        "winsByDiff":      {str(d): 0 for d in range(1, 9)},
        "personDaysByDiff":{str(d): 0.0 for d in range(1, 9)},
    })

    # week -> {user_id: max_difficulty} — used to build participantsByDiff
    week_participants = defaultdict(dict)

    for crime in crimes:
        ts = crime.get("executed_at") or crime.get("planning_at") or 0
        if not ts:
            continue
        w = week_start(ts)
        d = str(crime["difficulty"])
        diff_int = crime["difficulty"]
        revenue = crime_revenue(crime, prices)
        cost = crime_cost(crime, prices)
        status = crime.get("status", "")

        pd = crime_person_days(crime)
        weeks[w]["crimes"] += 1
        weeks[w]["money"] += revenue
        weeks[w]["cost"] += cost
        weeks[w]["byDiff"][d] = weeks[w]["byDiff"].get(d, 0) + revenue
        weeks[w]["costByDiff"][d] = weeks[w]["costByDiff"].get(d, 0) + cost
        weeks[w]["countByDiff"][d] = weeks[w]["countByDiff"].get(d, 0) + 1
        weeks[w]["personDaysByDiff"][d] = weeks[w]["personDaysByDiff"].get(d, 0.0) + pd
        if status == "Successful":
            weeks[w]["wins"] += 1
            weeks[w]["winsByDiff"][d] = weeks[w]["winsByDiff"].get(d, 0) + 1
        else:
            weeks[w]["fails"] += 1

        for slot in crime.get("slots", []):
            user_id = (slot.get("user") or {}).get("id")
            if user_id:
                prev = week_participants[w].get(user_id, 0)
                week_participants[w][user_id] = max(prev, diff_int)

    result = []
    for w, entry in sorted(weeks.items()):
        counts = {str(d): 0 for d in range(1, 9)}
        for uid, max_diff in week_participants.get(w, {}).items():
            counts[str(max_diff)] += 1
        entry["participantsByDiff"] = counts
        result.append({"week": w, **entry})
    return result


def build_daily(crimes):
    """Aggregate crimes into daily buckets for rolling win rate."""
    days = defaultdict(lambda: {"wins": 0, "crimes": 0})

    for crime in crimes:
        ts = crime.get("executed_at") or crime.get("planning_at") or 0
        if not ts:
            continue
        d = day_str(ts)
        days[d]["crimes"] += 1
        if crime.get("status") == "Successful":
            days[d]["wins"] += 1

    return [{"date": d, **v} for d, v in sorted(days.items())]


def apply_week_limit(weekly, daily, limit):
    """Keep only the most recent N weekly buckets and matching daily rows."""
    if not limit:
        return weekly, daily
    weekly = weekly[-limit:]
    if not weekly:
        return weekly, []
    start_week = weekly[0]["week"]
    daily = [d for d in daily if d["date"] >= start_week]
    return weekly, daily


def read_existing_data():
    """Parse the embedded const data = {...}; from dashboard.html. Returns dict or None."""
    with open(DASHBOARD_HTML, "r") as f:
        html = f.read()
    pattern = re.compile(r"^const data = (\{.*\});$", re.MULTILINE)
    match = pattern.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, Exception):
        return None


def inject_into_dashboard(data):
    """Replace the const data = {...} line in dashboard.html."""
    with open(DASHBOARD_HTML, "r") as f:
        html = f.read()

    json_str = json.dumps(data, separators=(",", ":"))
    new_line = f"const data = {json_str};"

    pattern = re.compile(r"^const data = \{.*\};$", re.MULTILINE)
    match = pattern.search(html)
    if not match:
        print("ERROR: Could not find 'const data = {...};' in dashboard.html", file=sys.stderr)
        sys.exit(1)
    new_html = html[:match.start()] + new_line + html[match.end():]

    with open(DASHBOARD_HTML, "w") as f:
        f.write(new_html)
    print("  Injected data into dashboard.html")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", help="Override the current week start (YYYY-MM-DD), e.g. to backfill a missed week")
    parser.add_argument("--weeks", type=int, help="Keep only the most recent N weeks in the generated dashboard")
    args = parser.parse_args()

    existing = read_existing_data()
    if args.week:
        cur_week = datetime.strptime(args.week, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        print(f"Week override: treating {args.week} as current week start")
    else:
        cur_week = current_week_start()
    cur_week_str = cur_week.strftime("%Y-%m-%d")

    # Full rebuild when: no existing data, or weekly entries lack costByDiff
    # (costByDiff was added to support profit tracking — missing means old schema)
    needs_full_rebuild = (
        existing is None
        or not existing.get("weekly")
        or "costByDiff" not in existing["weekly"][0]
        or "participantsByDiff" not in existing["weekly"][0]
        or "personDaysByDiff" not in existing["weekly"][0]
    )

    if needs_full_rebuild:
        print("Full rebuild (first run or schema migration)...")
        crimes = fetch_all_crimes()
        print("Fetching item prices...")
        time.sleep(60)  # avoid rate limiting after the paginated crimes fetch
        prices = fetch_item_prices(crimes)
        print(f"  Got prices for {len(prices)} items")
        print("Building aggregates...")
        weekly = build_weekly(crimes, prices)
        daily = build_daily(crimes)
        total_crimes = len(crimes)
    else:
        print(f"Incremental update — current week: {cur_week_str}")
        crimes = fetch_crimes_since(int(cur_week.timestamp()))
        print("Fetching item prices...")
        time.sleep(10)
        prices = fetch_item_prices(crimes)
        print(f"  Got prices for {len(prices)} items")
        print("Building aggregates...")

        # Build fresh entries for the current week only
        cur_weekly = build_weekly(crimes, prices)
        cur_daily = build_daily(crimes)

        # Merge: drop old entries for any week the fresh build covers (the
        # fetch has no upper bound, so cur_weekly can span multiple weeks
        # when --week backfills a past week), splice in the fresh ones
        cur_weeks = {w["week"] for w in cur_weekly}
        weekly = [w for w in existing["weekly"] if w["week"] not in cur_weeks]
        weekly += cur_weekly
        weekly.sort(key=lambda w: w["week"])

        cur_dates = {d["date"] for d in cur_daily}
        daily = [d for d in existing["daily"] if d["date"] not in cur_dates]
        daily += cur_daily
        daily.sort(key=lambda d: d["date"])

        total_crimes = sum(w["crimes"] for w in weekly)

    if args.weeks:
        print(f"Applying {args.weeks}-week dashboard window...")
        weekly, daily = apply_week_limit(weekly, daily, args.weeks)
        total_crimes = sum(w["crimes"] for w in weekly)

    date_range = f"{weekly[0]['week']} – {weekly[-1]['week']}" if weekly else "n/a"
    print(f"  {len(weekly)} weeks, {len(daily)} days, date range: {date_range}")

    data = {
        "weekly": weekly,
        "daily": daily,
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_crimes": total_crimes,
            "date_range": date_range,
        }
    }

    print("Injecting into dashboard.html...")
    inject_into_dashboard(data)
    print(f"\nDone. {total_crimes} crimes, {len(weekly)} weeks.")


if __name__ == "__main__":
    main()
