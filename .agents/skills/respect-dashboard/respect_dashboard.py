#!/usr/bin/env python3
"""Respect Dashboard generator.

Fetches the faction's outgoing attack history and executed OCs from the Torn
API v2 and renders daily respect-gain bars (attacks + organized crimes,
stacked), plus a top-contributors table. Fetched records are cached at
~/.torn_cache/respect_dashboard_cache.json (same pattern as the oc-spawning
skill's executed-crimes cache) so repeat runs only fetch what's new.

Usage:
    python3 respect_dashboard.py --key YOUR_API_KEY
    python3 respect_dashboard.py                # uses TORN_API_KEY from .env or env var
    python3 respect_dashboard.py --days 180     # look back further than the 90-day default

Options:
    --key KEY        Torn API key (or set TORN_API_KEY in .env or env var)
    --output FILE    Output HTML path (default: generated/respect_dashboard.html)
    --days N         How many days of history to pull (default: 90)
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict

API_BASE = "https://api.torn.com/v2"
DAY = 86400
CACHE_FILE = os.path.expanduser("~/.torn_cache/respect_dashboard_cache.json")


def _ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def load_dotenv():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
    for base in (os.getcwd(), repo_root):
        for name in (".env", ".env.local"):
            path = os.path.join(base, name)
            if not os.path.exists(path):
                continue
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                            value = value[1:-1]
                        os.environ.setdefault(key, value)
            except Exception:
                pass


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    ctx = ssl.create_default_context()
    try:
        import socket
        with socket.create_connection(("api.torn.com", 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname="api.torn.com"):
                pass
        return ctx
    except Exception:
        pass
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


_SSL_CTX = _ssl_context()


def api_get(url, api_key, retries=8):
    headers = {
        "Authorization": f"ApiKey {api_key}",
        "User-Agent": "TornRespectDashboard/1.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                data = json.loads(resp.read().decode())
            if "error" in data:
                code = data["error"].get("code", 0)
                msg = data["error"].get("error", "Unknown")
                if code == 5:
                    wait = min(60, 2 ** attempt + 1)
                    print(f"  Rate limited, waiting {wait}s ...", flush=True)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"API error {code}: {msg}")
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = min(60, 2 ** attempt + 1)
                print(f"  HTTP 429, waiting {wait}s ...", flush=True)
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise
    raise RuntimeError(f"Failed after {retries} retries: {url}")


def fetch_faction_basic(api_key):
    data = api_get(f"{API_BASE}/faction/basic", api_key)
    basic = data.get("basic", data)
    return basic["id"], basic.get("name", "Faction")


def fetch_respect_attacks(api_key, faction_id, since_ts):
    """Fetch every attack from since_ts onward, following pagination.
    `filters=attack` returns both incoming and outgoing records in one pass,
    so both are pulled from it: hits landed by our own members (keyed by
    `attacker.faction.id`) and incoming losses landed on our members (keyed
    by `defender.faction.id`) that carry a `respect_loss`. A hit where an
    outsider attacks our member isn't free -- it costs the faction a slice
    of respect too, roughly a quarter of what the attacker gains. Both hits
    and losses are tagged with `is_ranked_war`, since spikes on either side
    usually line up with an active ranked war rather than regular hunting or
    opportunistic mugging."""
    url = f"{API_BASE}/faction/attacks?limit=1000&filters=attack&sort=asc&from={since_ts}"

    hits = []
    losses = []
    page = 0
    while url:
        page += 1
        print(f"  Fetching attacks page {page} ...", end=" ", flush=True)
        data = api_get(url, api_key)
        attacks = data.get("attacks", [])
        print(f"{len(attacks)} records")
        # Torn's per-key rate limit gets tripped by long backfills (each page
        # is capped at 100 records regardless of the requested limit, so a
        # 90-day pull can be 150+ requests) -- a small pause between requests
        # keeps us under the limit instead of just reacting to 429s after the fact.
        time.sleep(0.7)
        for a in attacks:
            ts = a.get("ended") or a.get("started")
            attack_id = a.get("id")
            attacker = a.get("attacker")
            if attacker:
                fac = attacker.get("faction")
                if fac and fac.get("id") == faction_id:
                    respect = a.get("respect_gain") or 0
                    hits.append({
                        "attack_id": attack_id,
                        "ts": ts,
                        "id": attacker["id"],
                        "name": attacker.get("name", f"#{attacker['id']}"),
                        "respect": respect,
                        "war": bool(a.get("is_ranked_war")),
                    })
            defender = a.get("defender")
            if defender:
                fac = defender.get("faction")
                if fac and fac.get("id") == faction_id:
                    loss = a.get("respect_loss") or 0
                    if loss:
                        losses.append({
                            "attack_id": attack_id,
                            "ts": ts,
                            "respect": loss,
                            "war": bool(a.get("is_ranked_war")),
                        })
        url = (data.get("_metadata", {}) or {}).get("links", {}).get("next")

    return hits, losses


def fetch_oc_respect(api_key, since_ts):
    """Fetch every executed OC from since_ts onward. `rewards.respect` is the
    respect the faction gained from that crime; only 'Successful' crimes pay
    out (failures carry no reward). This is a second real, timestamped
    respect source the attacks endpoint doesn't cover -- and typically the
    larger one.

    This endpoint's `_metadata.links.next` is unreliable: it comes back null
    on a full page of 100 even when strictly more data exists past it, and
    `offset` is silently ignored once `from` is also set (confirmed directly
    against the API, not just this CLI). The only combination that actually
    advances is re-issuing `from` set to just past the last record's
    `executed_at` once a page comes back full."""
    seen_ids = set()
    events = []
    cursor = since_ts
    page = 0
    while True:
        page += 1
        url = f"{API_BASE}/faction/crimes?limit=100&cat=completed&filters=executed_at&sort=ASC&from={cursor}"
        print(f"  Fetching OC page {page} ...", end=" ", flush=True)
        data = api_get(url, api_key)
        crimes = data.get("crimes", [])
        print(f"{len(crimes)} records")
        time.sleep(0.7)

        max_ts = cursor
        new_count = 0
        for c in crimes:
            ts = c.get("executed_at")
            if ts is not None and ts > max_ts:
                max_ts = ts
            cid = c.get("id")
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            new_count += 1
            if c.get("status") != "Successful":
                continue
            rewards = c.get("rewards") or {}
            respect = rewards.get("respect") or 0
            if not respect:
                continue
            events.append({"crime_id": cid, "ts": ts, "respect": respect})

        if len(crimes) < 100 or new_count == 0:
            break
        cursor = max_ts + 1

    return events


# ------------------------------------------------------------------ caching

# Bump whenever a cached record's shape changes (e.g. a new field a day-
# bucketing function now assumes is always present) -- a stale cache is
# discarded wholesale rather than crashing on a missing key or silently
# misclassifying old records that predate the field.
CACHE_SCHEMA_VERSION = 2

EMPTY_CACHE = {"hits": [], "losses": [], "oc_events": [], "covered_since": None, "oc_covered_since": None}


def load_cache():
    """Historical hits/losses/OCs never change once they've happened, so
    they're cached like `oc-spawning`'s executed-crimes cache: keep
    everything ever fetched, and each run only asks the API for records
    newer than the cache's high-water mark rather than re-walking the whole
    window from scratch. `covered_since`/`oc_covered_since` track the
    earliest `since` timestamp each series has ever been fetched from, so a
    later run asking for a *longer* lookback than any previous run can tell
    it has a backward gap to fill, rather than silently under-reporting."""
    if not os.path.exists(CACHE_FILE):
        return dict(EMPTY_CACHE)
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(EMPTY_CACHE)
    if cache.get("schema_version") != CACHE_SCHEMA_VERSION:
        print(f"  Cache schema changed ({cache.get('schema_version')!r} -> {CACHE_SCHEMA_VERSION}), rebuilding ...",
              file=sys.stderr)
        return dict(EMPTY_CACHE)
    return {
        "hits": cache.get("hits", []),
        "losses": cache.get("losses", []),
        "oc_events": cache.get("oc_events", []),
        "covered_since": cache.get("covered_since"),
        "oc_covered_since": cache.get("oc_covered_since"),
    }


def save_cache(hits, losses, oc_events, covered_since, oc_covered_since):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({
            "schema_version": CACHE_SCHEMA_VERSION,
            "fetched_at": int(time.time()),
            "hits": hits,
            "losses": losses,
            "oc_events": oc_events,
            "covered_since": covered_since,
            "oc_covered_since": oc_covered_since,
        }, f)


def merge_by_key(cached, fresh, key):
    """Dedup cached + freshly-fetched records by their unique id, preferring
    the fresh copy (matters mainly at the delta fetch's boundary record)."""
    by_key = {r[key]: r for r in cached}
    for r in fresh:
        by_key[r[key]] = r
    return list(by_key.values())


def max_ts(records, default=0):
    return max((r["ts"] for r in records), default=default)


def day_key(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def build_daily_series(attack_hits, oc_events, losses, since_ts, until_ts):
    """Bucket all respect sources into UTC day totals, filling gaps with
    zero so quiet days show up rather than being skipped."""
    blank = lambda: {
        "attacks_war": 0.0, "attacks_other": 0.0, "oc": 0.0, "hits": 0, "ocs": 0,
        "loss_war": 0.0, "loss_other": 0.0, "losses": 0,
    }
    by_day = defaultdict(blank)
    for h in attack_hits:
        k = day_key(h["ts"])
        by_day[k]["attacks_war" if h["war"] else "attacks_other"] += h["respect"]
        by_day[k]["hits"] += 1
    for e in oc_events:
        k = day_key(e["ts"])
        by_day[k]["oc"] += e["respect"]
        by_day[k]["ocs"] += 1
    for l in losses:
        k = day_key(l["ts"])
        by_day[k]["loss_war" if l["war"] else "loss_other"] += l["respect"]
        by_day[k]["losses"] += 1

    start_day = since_ts - (since_ts % DAY)
    end_day = until_ts - (until_ts % DAY)
    days = []
    t = start_day
    while t <= end_day:
        k = day_key(t)
        entry = by_day.get(k) or blank()
        attacks_war = round(entry["attacks_war"], 2)
        attacks_other = round(entry["attacks_other"], 2)
        respect_attacks = round(attacks_war + attacks_other, 2)
        respect_oc = round(entry["oc"], 2)
        loss_war = round(entry["loss_war"], 2)
        loss_other = round(entry["loss_other"], 2)
        days.append({
            "date": k,
            "attacks_war": attacks_war,
            "attacks_other": attacks_other,
            "respect_attacks": respect_attacks,
            "respect_oc": respect_oc,
            "respect": round(respect_attacks + respect_oc, 2),
            "hits": entry["hits"],
            "ocs": entry["ocs"],
            "loss_war": loss_war,
            "loss_other": loss_other,
            "respect_loss": round(loss_war + loss_other, 2),
            "losses": entry["losses"],
        })
        t += DAY

    return days


def top_contributors(hits, limit=15):
    totals = defaultdict(lambda: {"name": "", "respect": 0.0, "hits": 0})
    for h in hits:
        t = totals[h["id"]]
        t["name"] = h["name"]
        t["respect"] += h["respect"]
        t["hits"] += 1
    ranked = sorted(totals.values(), key=lambda x: -x["respect"])
    return ranked[:limit]


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Respect Dashboard</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  :root {{ --bg:#1a1a2e; --panel:#16213e; --ink:#e0e0e0; --muted:#888; --border:#0f3460; --accent:#48dbfb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif; }}
  header {{ padding:24px 28px 8px; text-align:center; }}
  h1 {{ margin:0; font-size:28px; font-weight:bold; }}
  .sub {{ color:var(--muted); font-size:14px; margin-top:8px; }}
  .stats {{ display:flex; justify-content:center; gap:36px; flex-wrap:wrap; margin:18px 0 0; }}
  .stat {{ text-align:center; }}
  .stat .value {{ font-size:22px; font-weight:bold; font-variant-numeric:tabular-nums; }}
  .stat .label {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .panel {{ background:var(--panel); border:1px solid var(--border); border-radius:10px;
            max-width:960px; margin:22px auto; padding:20px 24px 16px; }}
  .legend {{ display:flex; justify-content:center; gap:22px; margin-bottom:10px; font-size:12px; color:var(--muted); }}
  .legend .item {{ display:flex; align-items:center; gap:6px; cursor:pointer; user-select:none; }}
  .legend .item.hidden {{ opacity:0.35; text-decoration:line-through; }}
  .legend .swatch {{ width:12px; height:12px; border-radius:2px; display:inline-block; }}
  .axis-lock {{ text-align:center; font-size:12px; color:var(--muted); margin-bottom:10px; }}
  .axis-lock label {{ cursor:pointer; user-select:none; }}
  .axis-lock input {{ accent-color:var(--accent); vertical-align:middle; margin-right:4px; }}
  #chart {{ display:block; margin:0 auto; }}
  .bar-attacks-war {{ fill:#3068b0; }}
  .bar-attacks-other {{ fill:#3987e5; }}
  .bar-oc {{ fill:#c98500; }}
  .bar-loss-war {{ fill:#b33939; }}
  .bar-loss-other {{ fill:#e66767; }}
  .axis text {{ fill:var(--muted); font-size:11px; }}
  .axis path, .axis line {{ stroke:#333; }}
  .grid line {{ stroke:#26264a; }}
  .grid path {{ display:none; }}
  #tooltip {{ position:absolute; pointer-events:none; background:var(--panel); border:1px solid var(--border);
              border-radius:6px; padding:8px 12px; font-size:12px; color:var(--ink); display:none;
              box-shadow:0 4px 12px rgba(0,0,0,0.4); }}
  #tooltip b {{ color:#fff; }}
  .crosshair {{ stroke:var(--muted); stroke-dasharray:3,3; }}
  .toggle-row {{ text-align:center; margin:6px 0 16px; }}
  .toggle-row button {{ background:none; border:none; color:var(--accent); cursor:pointer;
                         font-size:13px; text-decoration:underline; font-family:inherit; margin:0 10px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; display:none; }}
  table.shown {{ display:table; }}
  th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:normal; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .stat.loss .value {{ color:#e66767; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; padding:10px 0 30px; }}
</style>
</head>
<body>
<header>
  <h1>Respect Dashboard</h1>
  <div class="sub">{faction_name} &middot; {start_str} &ndash; {end_str}</div>
  <div class="stats">
    <div class="stat"><div class="value">{total_respect}</div><div class="label">Total respect</div></div>
    <div class="stat"><div class="value">{total_attacks_respect}</div><div class="label">From attacks ({total_hits} hits, {attacks_war_share}% ranked war)</div></div>
    <div class="stat"><div class="value">{total_oc_respect}</div><div class="label">From OCs ({total_ocs} crimes)</div></div>
    <div class="stat loss"><div class="value">&minus;{total_loss}</div><div class="label">Lost to incoming ({total_losses} hits, {war_share}% ranked war)</div></div>
    <div class="stat"><div class="value">{avg_per_day}</div><div class="label">Avg respect / day</div></div>
    <div class="stat"><div class="value">{best_day_value}</div><div class="label">Best day ({best_day_date})</div></div>
  </div>
</header>

<div class="panel">
  <div class="legend">
    <span class="item" data-series="attacks_war"><span class="swatch" style="background:#3068b0"></span>Attacks (ranked war)</span>
    <span class="item" data-series="attacks_other"><span class="swatch" style="background:#3987e5"></span>Attacks (other)</span>
    <span class="item" data-series="oc"><span class="swatch" style="background:#c98500"></span>Organized crimes</span>
    <span class="item" data-series="loss_war"><span class="swatch" style="background:#b33939"></span>Lost (ranked war)</span>
    <span class="item" data-series="loss_other"><span class="swatch" style="background:#e66767"></span>Lost (other)</span>
  </div>
  <div class="axis-lock">
    <label><input type="checkbox" id="lockAxis"> Lock y-axis range</label>
  </div>
  <div style="position:relative;">
    <svg id="chart"></svg>
    <div id="tooltip"></div>
  </div>
  <div class="toggle-row">
    <button id="dailyToggle">Show daily data table</button>
    <button id="topToggle">Show top contributors</button>
  </div>
  <table id="dailyTable">
    <thead><tr><th>Date</th><th class="num">Attacks (war)</th><th class="num">Attacks (other)</th><th class="num">OCs</th><th class="num">Total</th><th class="num">Hits</th><th class="num">Lost (war)</th><th class="num">Lost (other)</th></tr></thead>
    <tbody></tbody>
  </table>
  <table id="topTable">
    <thead><tr><th>#</th><th>Member</th><th class="num">Respect</th><th class="num">Hits</th><th class="num">Share of attacks</th></tr></thead>
    <tbody></tbody>
  </table>
</div>

<footer>Bars above zero are daily totals (attacks split into ranked-war/other, plus organized crimes, all stacked); bars below
  zero are respect lost to incoming attacks that landed on our members (also split into ranked-war/other). Top contributors
  covers attack respect only, since OC rewards are shared across a crime's slot members rather than attributed to one attacker.
  Excludes territory, racket, and other passive respect &mdash; Torn's API only exposes those as current all-time totals, not a
  dated history, so they can't be charted retroactively.</footer>

<script>
const DAYS = {days_json};
const TOP = {top_json};
const TOTAL_ATTACK_RESPECT = {total_attacks_respect_raw};

const margin = {{top: 20, right: 30, bottom: 30, left: 60}};
const width = 900, height = 340;
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select('#chart').attr('width', width).attr('height', height);
const plot = svg.append('g').attr('transform', `translate(${{margin.left}},${{margin.top}})`);

const x = d3.scaleBand().domain(d3.range(DAYS.length)).range([0, innerW]).padding(0.2);

// Each series stacks in this order within its group (positive = above zero,
// negative = below zero). Toggling a series off via the legend excludes it
// from the stack entirely -- the series above/beyond it collapse to fill the
// gap, rather than leaving a floating disconnected segment.
const SERIES = [
  {{ key: 'attacks_war', field: 'attacks_war', cls: 'bar-attacks-war', sign: 1 }},
  {{ key: 'attacks_other', field: 'attacks_other', cls: 'bar-attacks-other', sign: 1 }},
  {{ key: 'oc', field: 'respect_oc', cls: 'bar-oc', sign: 1 }},
  {{ key: 'loss_war', field: 'loss_war', cls: 'bar-loss-war', sign: -1 }},
  {{ key: 'loss_other', field: 'loss_other', cls: 'bar-loss-other', sign: -1 }},
];
const visible = Object.fromEntries(SERIES.map(s => [s.key, true]));

// Domain reflects only the currently-visible series, so hiding e.g. the big
// ranked-war spikes rescales the axis to the (much smaller) remaining data
// instead of leaving most of the chart empty.
function computeDomain() {{
  const posMax = d3.max(DAYS, d => SERIES
    .filter(s => s.sign > 0 && visible[s.key])
    .reduce((sum, s) => sum + d[s.field], 0)) || 0;
  const negMax = d3.max(DAYS, d => SERIES
    .filter(s => s.sign < 0 && visible[s.key])
    .reduce((sum, s) => sum + d[s.field], 0)) || 0;
  return [(-negMax * 1.08) || -1, (posMax * 1.08) || 1];
}}

const y = d3.scaleLinear().domain(computeDomain()).range([innerH, 0]);

const gGrid = plot.append('g').attr('class', 'grid')
  .call(d3.axisLeft(y).tickSize(-innerW).tickFormat(''));

const tickEvery = Math.max(1, Math.ceil(DAYS.length / 10));
plot.append('g').attr('class', 'axis').attr('transform', `translate(0,${{innerH}})`)
  .call(d3.axisBottom(x)
    .tickValues(d3.range(DAYS.length).filter(i => i % tickEvery === 0))
    .tickFormat(i => DAYS[i].date.slice(5)));

const gYAxis = plot.append('g').attr('class', 'axis')
  .call(d3.axisLeft(y).ticks(6).tickFormat(d3.format('~s')));

// A separate zero-baseline: the x-axis (date labels) stays pinned to the
// bottom edge above, since the loss bars below it would otherwise collide
// with the tick labels.
const zeroLine = plot.append('line').attr('x1', 0).attr('x2', innerW).attr('y1', y(0)).attr('y2', y(0))
  .attr('stroke', '#555');

for (const s of SERIES) {{
  plot.selectAll('rect.' + s.cls).data(DAYS).enter().append('rect')
    .attr('class', s.cls)
    .attr('x', (d, i) => x(i))
    .attr('width', x.bandwidth())
    .attr('rx', 2);
}}

const RESCALE_MS = 500;
let axisLocked = false;

function renderBars() {{
  if (!axisLocked) y.domain(computeDomain());
  const t = d3.transition().duration(RESCALE_MS).ease(d3.easeCubicOut);

  gGrid.transition(t).call(d3.axisLeft(y).tickSize(-innerW).tickFormat(''));
  gYAxis.transition(t).call(d3.axisLeft(y).ticks(6).tickFormat(d3.format('~s')));
  zeroLine.transition(t).attr('y1', y(0)).attr('y2', y(0));

  const posCum = DAYS.map(() => 0);
  const negCum = DAYS.map(() => 0);
  for (const s of SERIES) {{
    const sel = plot.selectAll('rect.' + s.cls);
    const active = visible[s.key];
    sel.transition(t)
       .attr('y', (d, i) => s.sign > 0
        ? y(posCum[i] + (active ? d[s.field] : 0))
        : y(-negCum[i]))
       .attr('height', (d, i) => {{
         if (!active) return 0;
         return s.sign > 0
           ? y(posCum[i]) - y(posCum[i] + d[s.field])
           : y(-(negCum[i] + d[s.field])) - y(-negCum[i]);
       }});
    if (active) {{
      DAYS.forEach((d, i) => {{
        if (s.sign > 0) posCum[i] += d[s.field]; else negCum[i] += d[s.field];
      }});
    }}
  }}
}}
renderBars();

const tooltip = document.getElementById('tooltip');
const overlay = plot.append('rect').attr('width', innerW).attr('height', innerH)
  .attr('fill', 'none').attr('pointer-events', 'all');
const crosshair = plot.append('line').attr('class', 'crosshair')
  .attr('y1', 0).attr('y2', innerH).style('display', 'none');

overlay.on('mousemove', function(event) {{
  const [mx] = d3.pointer(event);
  let i = Math.floor(mx / (innerW / DAYS.length));
  i = Math.max(0, Math.min(DAYS.length - 1, i));
  const d = DAYS[i];
  const cx = x(i) + x.bandwidth() / 2;
  crosshair.attr('x1', cx).attr('x2', cx).style('display', null);
  tooltip.style.display = 'block';
  tooltip.style.left = (cx + margin.left + 16) + 'px';
  tooltip.style.top = '10px';
  tooltip.innerHTML = `<b>${{d.date}}</b><br>Total: <b>${{d.respect.toLocaleString()}}</b><br>` +
    `Attacks: ${{d.respect_attacks.toLocaleString()}} (${{d.hits}} hits) &mdash; war ${{d.attacks_war.toLocaleString()}}, other ${{d.attacks_other.toLocaleString()}}<br>` +
    `OCs: ${{d.respect_oc.toLocaleString()}} (${{d.ocs}} crimes)<br>` +
    `Lost: -${{d.respect_loss.toLocaleString()}} (${{d.losses}} hits) &mdash; war -${{d.loss_war.toLocaleString()}}, other -${{d.loss_other.toLocaleString()}}`;
}}).on('mouseleave', function() {{
  crosshair.style('display', 'none');
  tooltip.style.display = 'none';
}});

document.getElementById('dailyToggle').addEventListener('click', () => {{
  document.getElementById('dailyTable').classList.toggle('shown');
}});
document.getElementById('topToggle').addEventListener('click', () => {{
  document.getElementById('topTable').classList.toggle('shown');
}});

document.querySelectorAll('.legend .item').forEach(el => {{
  el.addEventListener('click', () => {{
    const key = el.dataset.series;
    visible[key] = !visible[key];
    el.classList.toggle('hidden', !visible[key]);
    renderBars();
  }});
}});

document.getElementById('lockAxis').addEventListener('change', (event) => {{
  axisLocked = event.target.checked;
  if (!axisLocked) renderBars();
}});

document.querySelector('#dailyTable tbody').innerHTML = DAYS.slice().reverse().map(d => `
  <tr><td>${{d.date}}</td><td class="num">${{d.attacks_war.toLocaleString()}}</td>
  <td class="num">${{d.attacks_other.toLocaleString()}}</td>
  <td class="num">${{d.respect_oc.toLocaleString()}}</td><td class="num">${{d.respect.toLocaleString()}}</td>
  <td class="num">${{d.hits}}</td><td class="num">-${{d.loss_war.toLocaleString()}}</td>
  <td class="num">-${{d.loss_other.toLocaleString()}}</td></tr>
`).join('');

document.querySelector('#topTable tbody').innerHTML = TOP.map((t, i) => `
  <tr><td>${{i + 1}}</td><td>${{t.name}}</td><td class="num">${{t.respect.toLocaleString()}}</td>
  <td class="num">${{t.hits}}</td><td class="num">${{(100 * t.respect / TOTAL_ATTACK_RESPECT).toFixed(1)}}%</td></tr>
`).join('');
</script>
</body>
</html>
"""


def build_html(faction_name, days, attack_hits, output_path):
    total_attacks_respect = round(sum(d["respect_attacks"] for d in days), 2)
    total_attacks_war = round(sum(d["attacks_war"] for d in days), 2)
    total_oc_respect = round(sum(d["respect_oc"] for d in days), 2)
    total_respect = round(total_attacks_respect + total_oc_respect, 2)
    total_hits = sum(d["hits"] for d in days)
    total_ocs = sum(d["ocs"] for d in days)
    total_loss = round(sum(d["respect_loss"] for d in days), 2)
    total_loss_war = round(sum(d["loss_war"] for d in days), 2)
    total_losses = sum(d["losses"] for d in days)
    war_share = round(100 * total_loss_war / total_loss, 1) if total_loss else 0
    attacks_war_share = round(100 * total_attacks_war / total_attacks_respect, 1) if total_attacks_respect else 0
    avg_per_day = round(total_respect / len(days), 1) if days else 0
    best = max(days, key=lambda d: d["respect"]) if days else {"respect": 0, "date": "-"}

    top = top_contributors(attack_hits)

    html = HTML_TEMPLATE.format(
        faction_name=faction_name,
        start_str=days[0]["date"] if days else "-",
        end_str=days[-1]["date"] if days else "-",
        total_respect=f"{total_respect:,.0f}",
        total_attacks_respect=f"{total_attacks_respect:,.0f}",
        total_oc_respect=f"{total_oc_respect:,.0f}",
        total_hits=f"{total_hits:,}",
        total_ocs=f"{total_ocs:,}",
        total_loss=f"{total_loss:,.0f}",
        total_losses=f"{total_losses:,}",
        war_share=f"{war_share:.0f}",
        attacks_war_share=f"{attacks_war_share:.0f}",
        avg_per_day=f"{avg_per_day:,.0f}",
        best_day_value=f"{best['respect']:,.0f}",
        best_day_date=best["date"],
        days_json=json.dumps(days),
        top_json=json.dumps(top),
        total_attacks_respect_raw=json.dumps(total_attacks_respect),
    )

    _ensure_parent_dir(output_path)
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Wrote {output_path} ({len(days)} days, {total_hits} hits, {total_ocs} OCs, {total_respect:,.0f} respect)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", default=os.environ.get("TORN_API_KEY", ""),
                         help="Torn API key (or set TORN_API_KEY env var)")
    parser.add_argument("--output", default="generated/respect_dashboard.html", help="Output HTML path")
    parser.add_argument("--days", type=int, default=90, help="Days of history to pull (default: 90)")
    args = parser.parse_args()

    load_dotenv()
    api_key = args.key or os.environ.get("TORN_API_KEY", "")
    if not api_key:
        print("Error: API key required. Use --key, set TORN_API_KEY env var, or add it to .env", file=sys.stderr)
        sys.exit(1)

    print("Fetching faction info ...")
    faction_id, faction_name = fetch_faction_basic(api_key)

    now = int(time.time())
    since = now - args.days * DAY

    cache = load_cache()

    if cache["covered_since"] is not None and cache["covered_since"] <= since:
        # Cache already reaches back far enough; only need what's newer.
        attacks_fetch_from = max(since, max_ts(cache["hits"] + cache["losses"]) + 1)
        new_covered_since = cache["covered_since"]
    else:
        # No cache yet, or this run wants a longer lookback than any run
        # before it -- (re)fetch the whole window so the older gap gets filled.
        attacks_fetch_from = since
        new_covered_since = since
    print(f"Fetching attacks for {faction_name} (#{faction_id}) from "
          f"{time.strftime('%Y-%m-%d', time.gmtime(attacks_fetch_from))} ...")
    fresh_hits, fresh_losses = fetch_respect_attacks(api_key, faction_id, attacks_fetch_from)
    hits = merge_by_key(cache["hits"], fresh_hits, "attack_id")
    losses = merge_by_key(cache["losses"], fresh_losses, "attack_id")
    print(f"{len(fresh_hits)} new hits, {len(fresh_losses)} new incoming losses "
          f"({len(hits)}/{len(losses)} cached total)")

    if cache["oc_covered_since"] is not None and cache["oc_covered_since"] <= since:
        oc_fetch_from = max(since, max_ts(cache["oc_events"]) + 1)
        new_oc_covered_since = cache["oc_covered_since"]
    else:
        oc_fetch_from = since
        new_oc_covered_since = since
    print(f"Fetching executed OCs from {time.strftime('%Y-%m-%d', time.gmtime(oc_fetch_from))} ...")
    fresh_oc_events = fetch_oc_respect(api_key, oc_fetch_from)
    oc_events = merge_by_key(cache["oc_events"], fresh_oc_events, "crime_id")
    print(f"{len(fresh_oc_events)} new successful OCs ({len(oc_events)} cached total)")

    save_cache(hits, losses, oc_events, new_covered_since, new_oc_covered_since)

    # The cache can hold more history than this run asked for; trim to the
    # requested window before building the dashboard and its leaderboards.
    hits_in_window = [h for h in hits if h["ts"] >= since]
    losses_in_window = [l for l in losses if l["ts"] >= since]
    oc_events_in_window = [e for e in oc_events if e["ts"] >= since]

    days = build_daily_series(hits_in_window, oc_events_in_window, losses_in_window, since, now)
    build_html(faction_name, days, hits_in_window, args.output)


if __name__ == "__main__":
    main()
