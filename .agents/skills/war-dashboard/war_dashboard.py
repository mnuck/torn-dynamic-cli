#!/usr/bin/env python3
"""Build a ranked-war net-trade dashboard straight from the Torn API v2.

Self-contained: Python 3.9+ and the standard library (certifi is used when
present, otherwise the system trust store). No Torn CLI, no scraped payout
newsletter, no money anywhere in the output.

    python3 war_dashboard.py <war_id> [--key KEY] [--out FILE] [--faction ID]

The key is read from --key, $TORN_API_KEY, or a .env file in the working
directory or alongside this script. It needs a *limited*-access key or better
(faction attack log + ranked war report).

------------------------------------------------------------------------------
WHAT THIS MEASURES

Net respect trade: respect dealt minus respect given up, per member.

In a ranked war the enemy scores respect for every hit they land on us, so
respect absorbed is a COST, not a contribution:

  * dealing damage AND taking it  -> holding ground; exposure is the price of
    attacking, and these members are usually net-positive.
  * exposed WITHOUT attacking     -> net-negative however many hits were soaked,
    because that absorbed respect is pure enemy score.

Deliberately absent: anything about pay. This dashboard is meant to inform how
payouts *should* work, so feeding existing payouts back in would be circular.

CHAIN-MILESTONE BONUSES are excluded from BOTH sides. They do count toward the
official war score, but they cluster wherever a chain happened to tick over and
say nothing about a trade. Excluding them symmetrically keeps the comparison
honest; the reconciliation panel shows the full walk back to Torn's number so
the gap is never mistaken for an error.

Do NOT use the API's `respect_loss` field. It tracks the faction's persistent
accumulated respect balance outside ranked war. RW score is purely a tug of war
over `respect_gain`.
------------------------------------------------------------------------------
"""
import argparse
import collections
import json
import os
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request

API = "https://api.torn.com/v2"
UA = "TornWarDashboard/1.0"
HERE = pathlib.Path(__file__).resolve().parent

# Chain-milestone bonus amounts. A milestone record carries the bonus in
# modifiers.chain AND an identical respect_gain -- an ordinary chained hit has a
# fractional multiplier there instead (1.37, 2.0, ...), which is what separates
# the two. Verified exact on all 76 members of war 45796.
MILESTONES = {10, 20, 40, 80, 160, 320, 640, 1280, 2560, 5120, 10240, 20480}


def ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_ctx()


def load_key(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("TORN_API_KEY"):
        return os.environ["TORN_API_KEY"]
    for env in (pathlib.Path.cwd() / ".env", HERE / ".env", HERE.parents[2] / ".env"):
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip().lstrip("export ").strip()
                if line.startswith("TORN_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("No API key. Pass --key, set TORN_API_KEY, or add it to a .env file.")


def api_get(path, key, retries=6):
    """GET with backoff. Torn rejects the default urllib User-Agent with a 403,
    and returns rate limiting as a 200 body with an `error` key."""
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"ApiKey {key}", "User-Agent": UA, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                data = json.loads(r.read().decode())
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                if err.get("code") == 5:          # rate limited
                    time.sleep(min(60, 2 ** attempt + 1))
                    continue
                sys.exit(f"Torn API error {err.get('code')}: {err.get('error')}")
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(min(60, 2 ** attempt + 1))
                continue
            if e.code == 403:
                sys.exit("HTTP 403 — key lacks faction access, or it was rejected.")
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    sys.exit(f"Gave up after {retries} attempts: {url}")


def fetch_attacks(key, start, end):
    """Page the faction attack log across the war window.

    Paging follows the last record's timestamp rather than _metadata.links.next:
    the next link stops early (it quit 12h before the war ended on 45796) and
    repeats records. Timestamps plus an id-keyed dict get complete coverage.
    """
    seen, cursor, page = {}, start, 0
    while cursor < end:
        page += 1
        batch = api_get(f"/faction/attacks?limit=100&sort=asc&from={cursor}&to={end}",
                        key).get("attacks", [])
        if not batch:
            break
        fresh = sum(1 for a in batch if a["id"] not in seen)
        for a in batch:
            seen[a["id"]] = a
        last = max(a.get("ended") or a.get("started") for a in batch)
        print(f"\r  attack log: page {page}, {len(seen)} unique records", end="", flush=True)
        if last <= cursor and not fresh:
            break
        cursor = last if last > cursor else cursor + 1
        time.sleep(0.5)
    print()
    return list(seen.values())


def is_bonus(a):
    chain = (a.get("modifiers") or {}).get("chain") or 1
    return chain in MILESTONES and abs((a.get("respect_gain") or 0) - chain) < 0.01


def build(war_id, key, faction_id=None, cache=None):
    # Direct-by-id endpoint: the war id is a path segment, not a query param.
    report = api_get(f"/faction/{war_id}/rankedwarreport", key)
    report = report.get("rankedwarreport", report)
    factions = report["factions"]

    if faction_id is None:
        faction_id = api_get("/faction/basic", key).get("basic", {}).get("id")
    us = next((f for f in factions if f["id"] == faction_id), None)
    if us is None:
        sys.exit(f"Faction {faction_id} did not fight in war {war_id} "
                 f"(combatants: {[f['id'] for f in factions]}).")
    them = next(f for f in factions if f["id"] != us["id"])

    start, end = report["start"], report["end"]
    print(f"War {war_id}: {us['name']} v {them['name']}  "
          f"({(end - start) / 3600:.1f}h, official {us['score']:,}–{them['score']:,})")

    roster = {m["id"]: m["name"] for m in us.get("members", [])}

    # A full window is ~9.5k records over ~100 requests; cache it so iterating on
    # the presentation doesn't re-pull the log every time. A finished war is
    # immutable, so the cache never needs invalidating.
    cache_path = pathlib.Path(cache) if cache else None
    if cache_path and cache_path.exists():
        attacks = json.loads(cache_path.read_text())
        print(f"  attack log: {len(attacks)} records from cache ({cache_path})")
    else:
        attacks = fetch_attacks(key, start, end)
        if cache_path:
            cache_path.write_text(json.dumps(attacks))
            print(f"  cached {len(attacks)} records to {cache_path}")

    Z = lambda: collections.defaultdict(float)
    dealt, absorbed, bon_d, bon_a = Z(), Z(), Z(), Z()
    outh, inh, hosp, stealth, assist, lost, defwin, nonwar = (
        collections.Counter() for _ in range(8))

    for a in attacks:
        gain = a.get("respect_gain") or 0
        at, df = a.get("attacker") or {}, a.get("defender") or {}
        aid, did = at.get("id"), df.get("id")
        res = a.get("result")
        if not a.get("is_ranked_war"):
            # Energy spent outside the war, by our own members.
            if aid in roster and res not in ("Assist", "Lost", "Escape", "Timeout"):
                nonwar[aid] += 1
            continue
        if aid in roster:                                    # we attacked
            if is_bonus(a):
                bon_d[aid] += gain
                continue
            dealt[aid] += gain
            if res == "Assist":
                assist[aid] += 1
            elif res in ("Lost", "Stalemate"):
                lost[aid] += 1
            else:
                outh[aid] += 1
        elif did in roster:                                  # we were hit
            if is_bonus(a):
                bon_a[did] += gain
                continue
            absorbed[did] += gain
            inh[did] += 1
            if res == "Hospitalized":
                hosp[did] += 1
            if res == "Lost":
                defwin[did] += 1
            if a.get("is_stealthed"):
                stealth[did] += 1

    members = []
    for mid, name in roster.items():
        d, ab = round(dealt[mid], 1), round(absorbed[mid], 1)
        war_atk = outh[mid]
        total_atk = war_atk + nonwar[mid]
        members.append({
            "name": name, "id": mid, "dealt": d, "absorbed": ab,
            "net": round(d - ab, 1),
            "ratio": round(d / ab, 2) if ab > 0 else None,
            "outhits": war_atk, "inhits": inh[mid], "hosp": hosp[mid],
            "stealth": stealth[mid], "defwin": defwin[mid],
            "war": war_atk, "assist": assist[mid], "lost": lost[mid],
            "nonwar": nonwar[mid],
            "focus": round(war_atk / total_atk * 100) if total_atk else None,
            "bonus": round(bon_a[mid], 1),
        })
    members.sort(key=lambda m: -m["net"])

    tot_d = sum(m["dealt"] for m in members)
    tot_a = sum(m["absorbed"] for m in members)
    margin = tot_d - tot_a
    gave_back = -sum(m["net"] for m in members if m["net"] < 0)
    quiet = [m for m in members if m["dealt"] < 50]
    leak = sum(m["absorbed"] for m in quiet)

    bd, ba = sum(bon_d.values()), sum(bon_a.values())
    official = {
        "us_name": us["name"], "us_score": us["score"],
        "them_name": them["name"], "them_score": them["score"],
        "margin": us["score"] - them["score"],
        "bonus_dealt": round(bd, 1), "bonus_absorbed": round(ba, 1),
        "residual": round((us["score"] - them["score"]) - margin - (bd - ba), 1),
    }
    walk = (official["margin"] - official["bonus_dealt"]
            + official["bonus_absorbed"] - official["residual"])
    assert abs(walk - margin) < 0.05, f"reconciliation open: {walk:.1f} vs {margin:.1f}"

    return {
        "war": str(war_id), "generated": time.strftime("%Y-%m-%d %H:%M"),
        "members": members, "official": official,
        "total_dealt": round(tot_d, 1), "total_absorbed": round(tot_a, 1),
        "margin": round(margin, 1), "gave_back": round(gave_back, 1),
        "peak": round(margin + gave_back, 1),
        "leak": round(leak, 1), "n_quiet": len(quiet), "threshold": 50,
        "total_bonus": round(ba, 1), "counterfactual": round(margin + leak, 1),
    }


def main():
    p = argparse.ArgumentParser(description="Ranked-war net-trade dashboard.")
    p.add_argument("war_id")
    p.add_argument("--key")
    p.add_argument("--faction", type=int, help="Your faction id (default: whoever the key belongs to)")
    p.add_argument("--out", help="Output HTML (default: war_nettrade_<id>.html)")
    p.add_argument("--template", default=str(HERE / "template.html"))
    p.add_argument("--json", help="Also write the computed data here")
    p.add_argument("--fragment", action="store_true",
                   help="Emit without the <html>/<head> wrapper, for embedding "
                        "in a host that supplies its own document shell")
    p.add_argument("--cache", help="Reuse/store the raw attack log here (a finished "
                                   "war is immutable, so this never goes stale)")
    a = p.parse_args()

    data = build(a.war_id, load_key(a.key), a.faction, a.cache)
    page = pathlib.Path(a.template).read_text() \
        .replace("__DATA__", json.dumps(data, separators=(",", ":"))) \
        .replace("__WAR__", str(a.war_id))
    if not a.fragment:
        page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                f'<title>War {a.war_id} — Net Respect Trade</title>\n</head>\n<body>\n'
                + page + '\n</body>\n</html>\n')
    out = pathlib.Path(a.out or f"war_nettrade_{a.war_id}.html")
    out.write_text(page)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(data, indent=1))

    o = data["official"]
    print(f"  dealt {data['total_dealt']:,.0f} | given up {data['total_absorbed']:,.0f} "
          f"| net trade {data['margin']:+,.0f}")
    print(f"  reconciles: official {o['margin']:+,.0f} − {o['bonus_dealt']:,.0f} bonus dealt "
          f"+ {o['bonus_absorbed']:,.0f} bonus absorbed − {o['residual']:,.0f} = {data['margin']:+,.0f}")
    print(f"  leak {data['leak']:,.0f} from {data['n_quiet']} members under 50 dealt")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
