#!/usr/bin/env python3
"""Self-contained Torn racing dashboard generator.

Fetches race data from the Torn API v2, maintains a local cache to preserve
history beyond the API's ~6 month retention window, and generates an HTML
dashboard with D3 charts.

Usage:
    python3 racing_dashboard.py --key YOUR_API_KEY
    python3 racing_dashboard.py                     # uses TORN_API_KEY from .env or env var

Options:
    --key KEY        Torn API key (or set TORN_API_KEY in .env or env var)
    --output FILE    Output HTML path (default: racing_dashboard.html)
    --cache FILE     Cache file path (default: cache_races.json)
    --events FILE    Optional Racing.json event log for extended podium history
    --no-fetch       Skip API fetch, just rebuild from cache
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://api.torn.com/v2"

TRACK_NAMES = {
    6: "Uptown", 7: "Withdrawal", 8: "Underdog", 9: "Parkland",
    10: "Docks", 11: "Commerce", 12: "Two Islands", 15: "Industrial",
    16: "Vector", 17: "Mudpit", 18: "Hammerhead", 19: "Sewage",
    20: "Meltdown", 21: "Speedway", 23: "Stone Park", 24: "Convict",
}

CAR_ITEM_NAMES = {
    78: "Edomondo NSX",
    82: "Chevalier CZ06",
    93: "Volt MNG",
    498: "Cagoutte 10-6",
    511: "Colina Tanprice",
    520: "Lolo 458",
    522: "Veloria LFA",
}

# Color/shape palette for auto-assigning cars in order of first appearance
_PALETTE = [
    ("#4a90d9", "circle"),
    ("#e85d4a", "diamond"),
    ("#50c878", "triangle"),
    ("#daa520", "square"),
    ("#bb77dd", "cross"),
    ("#ff6b9d", "star"),
    ("#ff9f43", "circle"),
    ("#48dbfb", "diamond"),
    ("#ff6b6b", "triangle"),
    ("#1dd1a1", "square"),
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CARS_CONFIG_FILE = os.path.join(SCRIPT_DIR, "cars.json")

CUTOFF = datetime(2025, 12, 12).timestamp()


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def load_dotenv():
    """Load key=value pairs from a .env file into os.environ.
    Tries .env then .env.local in the script's directory.
    Handles named pipes (e.g. 1Password), comments, blank lines,
    and optional quoting."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for name in (".env", ".env.local"):
        path = os.path.join(script_dir, name)
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
                    # Strip surrounding quotes
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    os.environ.setdefault(key, value)
        except Exception:
            pass  # silently skip if unreadable

# ---------------------------------------------------------------------------
# API helpers (stdlib only)
# ---------------------------------------------------------------------------

def _ssl_context():
    """Create an SSL context. Tries certifi first, then system defaults,
    then unverified as last resort for macOS Python.org builds."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    # Quick smoke test: try to actually connect
    ctx = ssl.create_default_context()
    try:
        import socket
        with socket.create_connection(("api.torn.com", 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname="api.torn.com"):
                pass
        return ctx
    except Exception:
        pass
    # macOS Python.org builds often lack certs — fall back to unverified
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

_SSL_CTX = _ssl_context()


def api_get(url, api_key, retries=3):
    """GET a Torn API URL with retries and rate-limit handling."""
    headers = {
        "Authorization": f"ApiKey {api_key}",
        "User-Agent": "TornRacingDashboard/1.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                data = json.loads(resp.read().decode())

            # Torn sometimes returns 200 with an error body
            if "error" in data:
                code = data["error"].get("code", 0)
                msg = data["error"].get("error", "Unknown")
                if code == 5:  # rate limited
                    wait = 2 ** attempt + 1
                    print(f"  Rate limited, waiting {wait}s ...", flush=True)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"API error {code}: {msg}")

            return data

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt + 1
                print(f"  HTTP 429, waiting {wait}s ...", flush=True)
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise

    raise RuntimeError(f"Failed after {retries} retries: {url}")


def fetch_user_id(api_key):
    """Get the authenticated user's player ID."""
    data = api_get(f"{API_BASE}/user/profile", api_key)
    # Response may be {"profile": {"id": ...}} or {"id": ...}
    if "profile" in data and isinstance(data["profile"], dict):
        uid = data["profile"].get("id")
    else:
        uid = data.get("id") or data.get("player_id")
    if not uid:
        # Try any nested dict with "id"
        for v in data.values():
            if isinstance(v, dict) and "id" in v:
                uid = v["id"]
                break
    if not uid:
        raise RuntimeError("Could not determine user ID from API")
    return uid


def fetch_enlisted_cars(api_key):
    """Fetch the user's enlisted cars, returning a dict of car_id -> car info."""
    data = api_get(f"{API_BASE}/user/enlistedcars", api_key)
    cars = data.get("enlistedcars", [])
    return {c["id"]: c for c in cars if not c.get("is_removed")}


def load_cars_config():
    """Load cars.json config, returning dict of car_id (int) -> style dict."""
    if not os.path.exists(CARS_CONFIG_FILE):
        return {}
    with open(CARS_CONFIG_FILE) as f:
        raw = json.load(f)
    # Keys are stored as strings in JSON
    return {int(k): v for k, v in raw.items()}


def save_cars_config(config):
    """Save cars config to cars.json."""
    with open(CARS_CONFIG_FILE, "w") as f:
        json.dump({str(k): v for k, v in sorted(config.items())}, f, indent=2)


def build_car_styles(api_key, races, user_id):
    """Load or generate car styles config.

    On first run (no cars.json): fetches enlisted cars from API to get
    car_name, assigns colors/shapes from palette, saves cars.json.
    On subsequent runs: loads cars.json, adds any new cars found in race data.
    Returns dict of car_id (int) -> {name, color, shape}.
    """
    config = load_cars_config()

    # Find car_ids the user personally drove
    seen_car_ids = set()
    for race in races:
        for r in race.get("results", []):
            if r.get("driver_id") == user_id and r.get("car_id"):
                seen_car_ids.add(r["car_id"])

    new_ids = seen_car_ids - set(config.keys())

    if new_ids:
        # Fetch car names from API if we have a key, else use item name fallback
        enlisted = {}
        if api_key:
            try:
                enlisted = fetch_enlisted_cars(api_key)
            except Exception as e:
                print(f"  Warning: could not fetch enlisted cars: {e}")

        # Also build a car_id -> car_item_name map from race data as fallback
        item_names = {}
        for race in races:
            for r in race.get("results", []):
                cid = r.get("car_id")
                if cid and r.get("car_item_name"):
                    item_names[cid] = r["car_item_name"]

        # Assign palette slots — stable by sorting new IDs
        used_slots = {(v["color"], v["shape"]) for v in config.values()}
        available = [p for p in _PALETTE if p not in used_slots]
        # Cycle if we've exhausted the palette
        if not available:
            available = _PALETTE[:]

        for car_id in sorted(new_ids):
            car_info = enlisted.get(car_id, {})
            name = car_info.get("car_name") or item_names.get(car_id) or f"Car #{car_id}"
            color, shape = available.pop(0) if available else ("#aaaaaa", "circle")
            config[car_id] = {"name": name, "color": color, "shape": shape}
            print(f"  New car: {name} (id={car_id}, {color}, {shape})")

        save_cars_config(config)
        print(f"  Saved {CARS_CONFIG_FILE}")

    return config


def fetch_races(api_key, since=None):
    """Fetch races via auto-pagination, optionally starting from a timestamp."""
    url = f"{API_BASE}/user/races?limit=100&sort=desc"
    if since:
        url += f"&from={since}"
    all_races = []
    page = 0

    while url:
        page += 1
        print(f"  Fetching page {page} ...", end=" ", flush=True)
        data = api_get(url, api_key)

        races = data.get("races", [])
        print(f"{len(races)} races", flush=True)
        all_races.extend(races)

        if not races:
            break

        # Follow pagination
        links = data.get("_metadata", {}).get("links", {})
        url = links.get("prev")  # desc order → prev = older pages

    print(f"  Total fetched: {len(all_races)} races")
    return all_races


def latest_cache_timestamp(races):
    """Find the most recent schedule.end timestamp in cached races."""
    latest = 0
    for race in races:
        end_ts = race.get("schedule", {}).get("end", 0)
        if end_ts > latest:
            latest = end_ts
    return latest


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def load_cache(cache_file):
    """Load existing cache, return list of races."""
    if not os.path.exists(cache_file):
        return []
    with open(cache_file) as f:
        data = json.load(f)
    races = data.get("races", [])
    return races


def merge_and_save(existing, fresh, cache_file):
    """Merge race lists by ID (fresh wins), deduplicate, save."""
    by_id = {}
    for r in existing:
        by_id[r["id"]] = r
    for r in fresh:
        by_id[r["id"]] = r

    merged = sorted(by_id.values(), key=lambda r: r["id"])

    with open(cache_file, "w") as f:
        json.dump({"races": merged}, f, indent=2)

    return merged


# ---------------------------------------------------------------------------
# Data extraction (same logic as generate_race_dashboard.py)
# ---------------------------------------------------------------------------

def load_event_log(event_file):
    """Load Racing.json event log if it exists."""
    if not event_file or not os.path.exists(event_file):
        return []

    with open(event_file) as f:
        data = json.load(f)

    # Key varies by export (e.g. "cat116", "log8731") — always the first/only key
    events = next(iter(data.values()), {})
    finishes = []
    pos_map = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6}

    for e in events.values():
        if e["title"] != "Racing finish official race":
            continue
        d = e["data"]
        pos_str = d.get("position", "")
        position = pos_map.get(pos_str, 0)
        if position == 0:
            continue

        car_item_id = d.get("car", 0)
        car_item_name = CAR_ITEM_NAMES.get(car_item_id, f"Car #{car_item_id}")

        finishes.append({
            "date": e["timestamp"] * 1000,
            "track_id": d.get("track", 0),
            "position": position,
            "podium": 1 if position <= 3 else 0,
            "race_id": d.get("race_id", 0),
            "car_item_name": car_item_name,
        })

    finishes.sort(key=lambda x: x["date"])
    return finishes


def extract_track_data(races, user_id, car_styles):
    """Filter and group race results by track for the user."""
    track_data = {}

    for race in races:
        track_id = race.get("track_id")
        if track_id not in TRACK_NAMES:
            continue
        if not race.get("is_official", False):
            continue

        end_ts = race.get("schedule", {}).get("end", 0)
        if end_ts < CUTOFF:
            continue

        race_id = race.get("id")

        for r in race.get("results", []):
            if r.get("driver_id") != user_id:
                continue
            if r.get("has_crashed", False):
                continue

            race_time = r.get("race_time", 0)
            if race_time < 100:
                continue

            car_id = r.get("car_id")
            car_item_name = r.get("car_item_name", "Unknown")

            if car_id in car_styles:
                style = car_styles[car_id]
                car_name = style["name"]
                color = style["color"]
                shape = style["shape"]
            else:
                car_name = car_item_name
                color = "#999999"
                shape = "circle"

            track_data.setdefault(track_id, []).append({
                "date": end_ts * 1000,
                "race_time": race_time,
                "car_name": car_name,
                "car_item_name": car_item_name,
                "color": color,
                "shape": shape,
                "position": r.get("position", 0),
                "race_id": race_id,
                "car_id": car_id,
            })

    return track_data


def extract_meta_data(races, user_id):
    """Compute monthly opponent car composition per track."""
    track_months = defaultdict(lambda: defaultdict(Counter))

    for race in races:
        track_id = race.get("track_id")
        if track_id not in TRACK_NAMES:
            continue
        if not race.get("is_official", False):
            continue

        end_ts = race.get("schedule", {}).get("end", 0)
        month = datetime.fromtimestamp(end_ts).strftime("%Y-%m")

        for r in race.get("results", []):
            if r.get("driver_id") == user_id:
                continue
            car = r.get("car_item_name", "Unknown")
            track_months[track_id][month][car] += 1

    result = {}
    for track_id in sorted(track_months.keys()):
        months_data = track_months[track_id]
        total = Counter()
        for month_cars in months_data.values():
            total += month_cars
        top_cars = [car for car, _ in total.most_common(5)]

        months_sorted = sorted(months_data.keys())
        series = []
        for month in months_sorted:
            cars = months_data[month]
            entry = {"month": month, "total": sum(cars.values())}
            for car in top_cars:
                entry[car] = cars.get(car, 0)
            entry["Other"] = sum(c for car, c in cars.items() if car not in top_cars)
            series.append(entry)

        result[track_id] = {
            "cars": top_cars + ["Other"],
            "series": series,
        }

    return result


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_html(track_data, event_log, meta_data, car_styles):
    sorted_track_ids = sorted(track_data.keys())

    embedded_json = json.dumps(
        {str(k): v for k, v in track_data.items()}, separators=(",", ":")
    )
    track_names_json = json.dumps(
        {str(k): v for k, v in TRACK_NAMES.items()}, separators=(",", ":")
    )

    # Build legend from cars that actually appear in the data
    used_car_ids = {p["car_id"] for pts in track_data.values() for p in pts}
    car_legend = [
        {"name": car_styles[cid]["name"], "color": car_styles[cid]["color"], "shape": car_styles[cid]["shape"]}
        for cid in sorted(used_car_ids)
        if cid in car_styles
    ]
    car_legend_json = json.dumps(car_legend, separators=(",", ":"))

    meta_json = json.dumps(
        {str(k): v for k, v in meta_data.items()}, separators=(",", ":")
    )
    sorted_ids_json = json.dumps(sorted_track_ids)

    event_by_track = defaultdict(list)
    for e in event_log:
        if e["track_id"] in TRACK_NAMES:
            event_by_track[e["track_id"]].append(e)

    event_log_json = json.dumps(
        {str(k): v for k, v in event_by_track.items()}, separators=(",", ":")
    )
    all_events_json = json.dumps(event_log, separators=(",", ":"))

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Race Times - All Tracks</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  body {{
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0;
    padding: 20px;
  }}
  h1 {{
    text-align: center;
    color: #e0e0e0;
    margin-bottom: 10px;
    font-size: 28px;
  }}
  .subtitle {{
    text-align: center;
    color: #888;
    margin-bottom: 20px;
    font-size: 14px;
  }}
  .legend {{
    display: flex;
    justify-content: center;
    gap: 24px;
    margin-bottom: 30px;
    flex-wrap: wrap;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
  }}
  .chart-container {{
    display: grid;
    /* 2-up on desktop; collapses to a single column as the window narrows */
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 540px), 1fr));
    gap: 30px;
    max-width: 1600px;
    margin: 0 auto;
  }}
  .chart-box {{
    background: #16213e;
    border-radius: 10px;
    padding: 20px;
    border: 1px solid #0f3460;
    overflow: visible;
  }}
  /* Main chart SVGs scale to fill their grid cell (legend swatch SVGs are
     nested deeper, so this direct-child rule leaves them untouched). */
  .chart-box > svg {{
    width: 100%;
    height: auto;
  }}
  .chart-title {{
    text-align: center;
    font-size: 18px;
    font-weight: bold;
    margin-bottom: 10px;
    color: #e0e0e0;
  }}
  .chart-subtitle {{
    text-align: center;
    font-size: 12px;
    color: #888;
    margin-bottom: 5px;
  }}
  .chart-legend {{
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 10px;
  }}
  .chart-legend .legend-item {{
    font-size: 12px;
    color: #ccc;
  }}
  .controls {{
    text-align: center;
    margin: 0 auto 20px auto;
    font-size: 14px;
    color: #ccc;
  }}
  .controls label {{
    cursor: pointer;
    user-select: none;
  }}
  .controls input {{
    vertical-align: middle;
    margin-right: 6px;
  }}
  .tooltip {{
    position: absolute;
    background: rgba(22, 33, 62, 0.95);
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 10px;
    font-size: 12px;
    pointer-events: auto;
    color: #e0e0e0;
    z-index: 1000;
    line-height: 1.6;
    min-width: 200px;
    max-width: 350px;
    white-space: nowrap;
  }}
  .axis text {{
    fill: #888;
    font-size: 11px;
  }}
  .axis line, .axis path {{
    stroke: #333;
  }}
  .grid line {{
    stroke: #222;
    stroke-opacity: 0.7;
  }}
  .grid path {{
    stroke-width: 0;
  }}
  svg {{
    overflow: visible;
  }}
  .section-header {{
    text-align: center;
    color: #e0e0e0;
    margin: 40px 0 10px 0;
    font-size: 24px;
    border-top: 1px solid #0f3460;
    padding-top: 30px;
  }}
  .section-header:first-of-type {{
    border-top: none;
    margin-top: 10px;
    padding-top: 0;
  }}
</style>
</head>
<body>

<h1>Racing Dashboard</h1>
<div class="subtitle">Race times (left axis) and rolling 20-race podium rate (right axis) | Dec 12 2025 onwards</div>

<div class="legend" id="legend"></div>

<div class="chart-box" style="max-width:1600px; margin:0 auto 30px auto;">
  <div class="chart-title">All Tracks Combined - Podium Rate</div>
  <div class="chart-subtitle">Rolling 20-race podium rate from full event log history</div>
  <div id="podium-all"></div>
</div>

<div class="controls">
  <label><input type="checkbox" id="normalizeY"> Normalize Y-axis across tracks (comparable slopes, compresses low-variance tracks)</label>
</div>
<div class="chart-container" id="charts"></div>

<h2 class="section-header">Time &rarr; Position Strip Charts</h2>
<div class="subtitle">Race time vs finishing position — marker shape/color = car</div>

<div class="chart-container" id="strip-charts"></div>

<h2 class="section-header">Field Composition by Track</h2>
<div class="subtitle">What cars opponents are running, by month</div>

<div class="chart-container" id="meta-charts"></div>

<div class="tooltip" id="tooltip" style="display:none;"></div>

<script>
const trackData = {embedded_json};
const metaData = {meta_json};
const eventByTrack = {event_log_json};
const allEvents = {all_events_json};
const trackNames = {track_names_json};
const carLegend = {car_legend_json};
const sortedTrackIds = {sorted_ids_json};

function symbolPath(shape) {{
  switch(shape) {{
    case 'circle': return d3.symbol().type(d3.symbolCircle).size(60)();
    case 'diamond': return d3.symbol().type(d3.symbolDiamond).size(80)();
    case 'triangle': return d3.symbol().type(d3.symbolTriangle).size(70)();
    case 'square': return d3.symbol().type(d3.symbolSquare).size(60)();
    case 'cross': return d3.symbol().type(d3.symbolCross).size(70)();
    case 'star': return d3.symbol().type(d3.symbolStar).size(80)();
    default: return d3.symbol().type(d3.symbolCircle).size(60)();
  }}
}}

// Per-car swatches now live on each individual chart (see appendChartLegend);
// this top legend only explains the shared point/line encoding.
const legend = d3.select('#legend');
legend.append('div').attr('class', 'legend-item')
  .append('span').text('Bright = podium, faded = P4–P6 | Green line = podium rate')
  .style('color', '#888').style('font-style', 'italic');

// Build a compact per-chart car legend: only the cars present in `pts`,
// ordered to match the global car ordering for visual consistency.
const carOrder = {{}};
carLegend.forEach((c, i) => {{ carOrder[c.name] = i; }});

function appendChartLegend(box, pts) {{
  const seen = {{}};
  pts.forEach(p => {{
    if (!seen[p.car_name]) seen[p.car_name] = {{name: p.car_name, color: p.color, shape: p.shape}};
  }});
  const cars = Object.values(seen).sort((a, b) =>
    (carOrder[a.name] ?? 999) - (carOrder[b.name] ?? 999));
  const lg = box.append('div').attr('class', 'chart-legend');
  cars.forEach(car => {{
    const item = lg.append('div').attr('class', 'legend-item');
    item.append('svg').attr('width', 14).attr('height', 14)
      .append('path')
      .attr('d', symbolPath(car.shape))
      .attr('transform', 'translate(7,7)')
      .attr('fill', car.color).attr('stroke', car.color).attr('stroke-width', 1);
    item.append('span').text(car.name);
  }});
}}

// Tooltip with delayed hide so the link is clickable
const tooltip = d3.select('#tooltip');
let hideTimeout = null;
let activePoint = null;

function showTooltip() {{
  clearTimeout(hideTimeout);
  tooltip.style('display', 'block');
}}

function scheduleHide() {{
  hideTimeout = setTimeout(() => {{
    tooltip.style('display', 'none');
    if (activePoint) {{
      const origOpacity = activePoint.__baseOpacity || 0.4;
      d3.select(activePoint).attr('opacity', origOpacity).attr('stroke-width', 0.5);
      activePoint = null;
    }}
  }}, 300);
}}

tooltip.on('mouseover', showTooltip)
       .on('mouseout', scheduleHide);

function positionTooltip(event) {{
  const node = tooltip.node();
  node.style.position = 'fixed';
  node.style.left = '0px';
  node.style.top = '0px';
  node.style.display = 'block';
  const ttWidth = node.offsetWidth;
  const ttHeight = node.offsetHeight;
  node.style.position = 'absolute';

  const viewW = document.documentElement.clientWidth;
  const viewH = document.documentElement.clientHeight;

  let left = event.clientX + 12;
  let top = event.clientY - 10;

  if (left + ttWidth > viewW - 10) left = event.clientX - ttWidth - 12;
  if (top + ttHeight > viewH - 10) top = event.clientY - ttHeight - 10;
  if (left < 5) left = 5;
  if (top < 5) top = 5;

  tooltip.style('left', (left + window.scrollX) + 'px')
         .style('top', (top + window.scrollY) + 'px');
}}

// === SHARED HELPERS ===
const podiumWindow = 20;

function rollingPodiumRate(events, win) {{
  if (events.length < win) return [];
  const result = [];
  for (let i = win - 1; i < events.length; i++) {{
    let podiums = 0;
    for (let j = i - win + 1; j <= i; j++) {{
      if (events[j].podium) podiums++;
    }}
    result.push({{
      date: events[i].date,
      rate: podiums / win,
      race_id: events[i].race_id,
      position: events[i].position,
      car_item_name: events[i].car_item_name,
      raceNum: i + 1,
    }});
  }}
  return result;
}}

function linReg(points) {{
  const n = points.length;
  if (n < 2) return null;
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  points.forEach(p => {{
    sx += p.x; sy += p.y; sxx += p.x * p.x; sxy += p.x * p.y;
  }});
  const denom = n * sxx - sx * sx;
  if (Math.abs(denom) < 1e-10) return null;
  const slope = (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  return {{ slope, intercept }};
}}

function fmtTime(s) {{
  const mins = Math.floor(s / 60);
  const secs = s - mins * 60;
  return mins + ':' + secs.toFixed(2).padStart(5, '0');
}}

// === ALL TRACKS PODIUM CHART (standalone) ===
(function() {{
  const container = '#podium-all';
  const cutoffMs = new Date('2025-12-12').getTime();
  const clampedEvents = allEvents.filter(e => e.date >= cutoffMs);
  if (clampedEvents.length < podiumWindow) return;
  const rolling20 = rollingPodiumRate(clampedEvents, podiumWindow);
  const rolling100 = rollingPodiumRate(clampedEvents, 100);
  const chartHeight = 300;
  const margin = {{top: 20, right: 120, bottom: 50, left: 60}};
  const chartWidth = document.getElementById('podium-all').parentElement.clientWidth - 40;
  const w = chartWidth - margin.left - margin.right;
  const h = chartHeight - margin.top - margin.bottom;

  const svg = d3.select(container).append('svg')
    .attr('width', chartWidth).attr('height', chartHeight)
    .append('g').attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

  const x = d3.scaleTime().domain(d3.extent(rolling20, d => new Date(d.date))).range([0, w]);
  const y = d3.scaleLinear().domain([0, 1]).range([h, 0]);

  svg.append('g').attr('class', 'grid').call(d3.axisLeft(y).tickSize(-w).tickFormat(''))
    .selectAll('line').attr('stroke', '#222');
  svg.append('line').attr('x1', 0).attr('x2', w).attr('y1', y(0.5)).attr('y2', y(0.5))
    .attr('stroke', '#e85d4a').attr('stroke-width', 1).attr('stroke-dasharray', '4,4').attr('opacity', 0.5);
  svg.append('g').attr('class', 'axis').attr('transform', 'translate(0,' + h + ')')
    .call(d3.axisBottom(x).tickFormat(d3.timeFormat('%b %Y')));
  svg.append('g').attr('class', 'axis').call(d3.axisLeft(y).ticks(5).tickFormat(d => Math.round(d * 100) + '%'));

  const line = d3.line().x(d => x(new Date(d.date))).y(d => y(d.rate)).curve(d3.curveMonotoneX);

  // 20-race line
  svg.append('path').datum(rolling20).attr('fill', 'none')
    .attr('stroke', '#4a90d9').attr('stroke-width', 1.5).attr('opacity', 0.6).attr('d', line);

  // 100-race line
  svg.append('path').datum(rolling100).attr('fill', 'none')
    .attr('stroke', '#50c878').attr('stroke-width', 2.5).attr('d', line);

  // Legend
  const leg = svg.append('g').attr('transform', 'translate(' + (w + 10) + ', 10)');
  [['#4a90d9', '20-race', 1.5, 0.6], ['#50c878', '100-race', 2.5, 1]].forEach(([color, label, sw, op], i) => {{
    const g = leg.append('g').attr('transform', 'translate(0,' + (i * 22) + ')');
    g.append('line').attr('x1', 0).attr('x2', 22).attr('y1', 6).attr('y2', 6)
      .attr('stroke', color).attr('stroke-width', sw).attr('opacity', op);
    g.append('text').attr('x', 28).attr('y', 10).attr('fill', '#aaa').attr('font-size', '11px').text(label);
  }});

  // Hover targets for 20-race line
  rolling20.forEach(p => {{
    svg.append('circle').attr('cx', x(new Date(p.date))).attr('cy', y(p.rate)).attr('r', 4)
      .attr('fill', 'transparent').attr('cursor', 'pointer')
      .on('mouseover', function(event) {{
        showTooltip();
        const dateStr = new Date(p.date).toLocaleDateString('en-US', {{month:'short', day:'numeric', year:'numeric'}});
        tooltip.html(
          'Podium rate (20): <b>' + Math.round(p.rate * 100) + '%</b><br>' +
          'This race: P' + p.position + ' (' + p.car_item_name + ')<br>' +
          'Race #' + p.raceNum + ' | ' + dateStr + '<br>' +
          '<a href="https://www.torn.com/page.php?sid=racing&tab=log&raceID=' + p.race_id + '" target="_blank" style="color:#4a90d9;">View race</a>'
        );
        positionTooltip(event);
      }})
      .on('mouseout', scheduleHide);
  }});

  // Hover targets for 100-race line
  rolling100.forEach(p => {{
    svg.append('circle').attr('cx', x(new Date(p.date))).attr('cy', y(p.rate)).attr('r', 5)
      .attr('fill', 'transparent').attr('cursor', 'pointer')
      .on('mouseover', function(event) {{
        showTooltip();
        const dateStr = new Date(p.date).toLocaleDateString('en-US', {{month:'short', day:'numeric', year:'numeric'}});
        tooltip.html(
          'Podium rate (100): <b>' + Math.round(p.rate * 100) + '%</b><br>' +
          'This race: P' + p.position + ' (' + p.car_item_name + ')<br>' +
          'Race #' + p.raceNum + ' | ' + dateStr + '<br>' +
          '<a href="https://www.torn.com/page.php?sid=racing&tab=log&raceID=' + p.race_id + '" target="_blank" style="color:#4a90d9;">View race</a>'
        );
        positionTooltip(event);
      }})
      .on('mouseout', scheduleHide);
  }});
}})();

// === COMBINED PER-TRACK CHARTS ===
const margin = {{top: 20, right: 60, bottom: 50, left: 60}};
const width = 680 - margin.left - margin.right;
const height = 350 - margin.top - margin.bottom;

const chartsDiv = d3.select('#charts');

// Widest race-time spread across all tracks — used only when the user opts into
// a shared (normalised) Y span so slopes are comparable between charts.
let globalYSpan = 0;
sortedTrackIds.forEach(tid => {{
  const pts = trackData[String(tid)];
  if (!pts || pts.length === 0) return;
  const ext = d3.extent(pts, d => d.race_time);
  const pad = (ext[1] - ext[0]) * 0.1 || 10;
  const span = (ext[1] + pad) - (ext[0] - pad);
  if (span > globalYSpan) globalYSpan = span;
}});

function renderTimeSeriesCharts(normalizeY) {{
  chartsDiv.selectAll('*').remove();
  sortedTrackIds.forEach(tid => {{
  const key = String(tid);
  const points = trackData[key];
  if (!points || points.length === 0) return;

  const trackName = trackNames[key] || ('Track ' + tid);

  // Group by car
  const byCar = {{}};
  points.forEach(p => {{
    if (!byCar[p.car_name]) byCar[p.car_name] = [];
    byCar[p.car_name].push(p);
  }});

  const raceCount = points.length;
  const carCount = Object.keys(byCar).length;

  // Compute podium stats from event log for subtitle
  const events = eventByTrack[key] || [];
  const podiums = events.filter(e => e.podium).length;
  const podiumPct = events.length > 0 ? Math.round(podiums / events.length * 100) : 0;

  const box = chartsDiv.append('div').attr('class', 'chart-box');
  box.append('div').attr('class', 'chart-title').text(trackName);
  box.append('div').attr('class', 'chart-subtitle')
    .text(raceCount + ' races, ' + carCount + ' car' + (carCount > 1 ? 's' : '') +
          (events.length > 0 ? ' | ' + podiumPct + '% podium (' + podiums + '/' + events.length + ' all-time)' : ''));

  appendChartLegend(box, points);

  const svgW = width + margin.left + margin.right;
  const svgH = height + margin.top + margin.bottom;
  const svg = box.append('svg')
    .attr('viewBox', '0 0 ' + svgW + ' ' + svgH)
    .attr('preserveAspectRatio', 'xMidYMid meet')
    .append('g')
    .attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

  // X scale from race time data
  const xExtent = d3.extent(points, d => d.date);
  const x = d3.scaleTime()
    .domain([new Date(xExtent[0]), new Date(xExtent[1])])
    .range([0, width]);

  // Left Y: race time. Per-track range by default; when normalizeY is on, use a
  // shared span centred on each track's midpoint so slopes compare across charts.
  const yExtent = d3.extent(points, d => d.race_time);
  let yDomain;
  if (normalizeY) {{
    const yMid = (yExtent[0] + yExtent[1]) / 2;
    yDomain = [yMid - globalYSpan / 2, yMid + globalYSpan / 2];
  }} else {{
    const yPad = (yExtent[1] - yExtent[0]) * 0.1 || 10;
    yDomain = [yExtent[0] - yPad, yExtent[1] + yPad];
  }}
  const yLeft = d3.scaleLinear().domain(yDomain).range([height, 0]);

  // Right Y: podium rate (0-100%)
  const yRight = d3.scaleLinear()
    .domain([0, 1])
    .range([height, 0]);

  // Grid (from left axis)
  svg.append('g').attr('class', 'grid')
    .call(d3.axisLeft(yLeft).tickSize(-width).tickFormat(''))
    .selectAll('line').attr('stroke', '#222');

  // Axes
  svg.append('g').attr('class', 'axis')
    .attr('transform', 'translate(0,' + height + ')')
    .call(d3.axisBottom(x).ticks(5).tickFormat(d3.timeFormat('%b %d')));

  svg.append('g').attr('class', 'axis')
    .call(d3.axisLeft(yLeft).ticks(6).tickFormat(d => fmtTime(d)));

  // Right axis for podium rate
  svg.append('g').attr('class', 'axis')
    .attr('transform', 'translate(' + width + ',0)')
    .call(d3.axisRight(yRight).ticks(5).tickFormat(d => Math.round(d * 100) + '%'))
    .selectAll('text').attr('fill', '#5a9a5a');

  // 50% podium reference line
  svg.append('line')
    .attr('x1', 0).attr('x2', width)
    .attr('y1', yRight(0.5)).attr('y2', yRight(0.5))
    .attr('stroke', '#5a9a5a').attr('stroke-width', 1)
    .attr('stroke-dasharray', '2,4').attr('opacity', 0.4);

  // Podium rate line (clipped to x domain)
  if (events.length >= podiumWindow) {{
    const rolling = rollingPodiumRate(events, podiumWindow);
    const xMin = xExtent[0], xMax = xExtent[1];
    const visible = rolling.filter(r => r.date >= xMin && r.date <= xMax);

    if (visible.length > 1) {{
      const podLine = d3.line()
        .x(d => x(new Date(d.date)))
        .y(d => yRight(d.rate))
        .curve(d3.curveMonotoneX);

      svg.append('path')
        .datum(visible)
        .attr('fill', 'none')
        .attr('stroke', '#50c850')
        .attr('stroke-width', 2.5)
        .attr('opacity', 0.7)
        .attr('d', podLine);

      // Hover targets for podium line
      visible.forEach(p => {{
        svg.append('circle')
          .attr('cx', x(new Date(p.date)))
          .attr('cy', yRight(p.rate))
          .attr('r', 4)
          .attr('fill', 'transparent')
          .attr('cursor', 'pointer')
          .on('mouseover', function(event) {{
            showTooltip();
            const dateStr = new Date(p.date).toLocaleDateString('en-US', {{month:'short', day:'numeric', year:'numeric'}});
            tooltip.html(
              'Podium rate: <b>' + Math.round(p.rate * 100) + '%</b><br>' +
              'Window: last ' + podiumWindow + ' races on this track<br>' +
              'This race: P' + p.position + ' (' + p.car_item_name + ')<br>' +
              'Race #' + p.raceNum + ' | ' + dateStr + '<br>' +
              '<a href="https://www.torn.com/page.php?sid=racing&tab=log&raceID=' + p.race_id + '" target="_blank" style="color:#4a90d9;">View race</a>'
            );
            positionTooltip(event);
          }})
          .on('mouseout', scheduleHide);
      }});
    }}
  }}

  // Trendlines per car (if >= 5 races)
  Object.entries(byCar).forEach(([carName, carPoints]) => {{
    if (carPoints.length < 5) return;
    const regPoints = carPoints.map(p => ({{ x: p.date, y: p.race_time }}));
    const reg = linReg(regPoints);
    if (!reg) return;

    const xMin = d3.min(carPoints, d => d.date);
    const xMax = d3.max(carPoints, d => d.date);
    const y1 = reg.slope * xMin + reg.intercept;
    const y2 = reg.slope * xMax + reg.intercept;

    svg.append('line')
      .attr('x1', x(new Date(xMin)))
      .attr('y1', yLeft(y1))
      .attr('x2', x(new Date(xMax)))
      .attr('y2', yLeft(y2))
      .attr('stroke', carPoints[0].color)
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '6,3')
      .attr('opacity', 0.6);
  }});

  // Data points
  points.forEach(p => {{
    const px = x(new Date(p.date));
    const py = yLeft(p.race_time);
    const isPodium = p.position >= 1 && p.position <= 3;
    const baseOpacity = isPodium ? 0.9 : 0.4;

    svg.append('path')
      .attr('d', symbolPath(p.shape))
      .attr('transform', 'translate(' + px + ',' + py + ')')
      .attr('fill', p.color)
      .attr('stroke', p.color)
      .attr('stroke-width', 0.5)
      .attr('opacity', baseOpacity)
      .attr('cursor', 'pointer')
      .each(function() {{ this.__baseOpacity = baseOpacity; }})
      .on('mouseover', function(event) {{
        if (activePoint && activePoint !== this) {{
          const prevOpacity = activePoint.__baseOpacity || 0.4;
          d3.select(activePoint).attr('opacity', prevOpacity).attr('stroke-width', 0.5);
        }}
        activePoint = this;
        d3.select(this).attr('opacity', 1).attr('stroke-width', 2);
        const dt = new Date(p.date);
        const dateStr = dt.toLocaleDateString('en-US', {{month:'short', day:'numeric', year:'numeric'}});
        showTooltip();
        tooltip.html(
            '<b>' + p.car_name + '</b> (' + p.car_item_name + ')<br>' +
            'Race time: <b>' + fmtTime(p.race_time) + '</b><br>' +
            'Position: ' + p.position + '<br>' +
            'Date: ' + dateStr + '<br>' +
            '<a href="https://www.torn.com/page.php?sid=racing&tab=log&raceID=' + p.race_id + '" target="_blank" style="color:#4a90d9;">View race</a>'
          );
        positionTooltip(event);
      }})
      .on('mouseout', function() {{
        scheduleHide();
      }});
  }});
  }});
}}

// Re-render the per-track time-series charts when the normalise toggle changes,
// persisting the choice across reloads via localStorage.
const NORMALIZE_KEY = 'racingDashboard.normalizeY';
const normalizeInit = localStorage.getItem(NORMALIZE_KEY) === 'true';
d3.select('#normalizeY')
  .property('checked', normalizeInit)
  .on('change', function() {{
    localStorage.setItem(NORMALIZE_KEY, this.checked);
    renderTimeSeriesCharts(this.checked);
  }});
renderTimeSeriesCharts(normalizeInit);

// === TIME -> POSITION STRIP CHARTS ===
const posColors = {{
  1: '#ffd700', 2: '#c0c0c0', 3: '#cd7f32',
  4: '#4a90d9', 5: '#50c878', 6: '#bb77dd'
}};
const posLabels = {{1:'1st',2:'2nd',3:'3rd',4:'4th',5:'5th',6:'6th'}};
const allPositions = [1,2,3,4,5,6];

const carStyleMap = {{}};
carLegend.forEach(c => {{ carStyleMap[c.name] = c; }});

function stripKde(kernel, thresholds, values) {{
  return thresholds.map(t => [t, d3.mean(values, d => kernel(t - d))]);
}}
function stripEpanechnikov(bw) {{
  return x => {{ x = x/bw; return Math.abs(x)<=1 ? 0.75*(1-x*x)/bw : 0; }};
}}

const stripDiv = d3.select('#strip-charts');

sortedTrackIds.forEach(tid => {{
  const key = String(tid);
  const points = trackData[key];
  if (!points || points.length < 3) return;

  // Filter out crashes (race_time > median * 2)
  const times = points.map(p => p.race_time).sort((a,b) => a-b);
  const median = times[Math.floor(times.length/2)];
  const cutoff = median * 2;
  const data = points.filter(p => p.race_time < cutoff && p.position >= 1 && p.position <= 6);
  if (data.length < 3) return;

  const trackName = trackNames[key] || ('Track ' + tid);

  const box = stripDiv.append('div').attr('class', 'chart-box');
  box.append('div').attr('class', 'chart-title').text(trackName);
  box.append('div').attr('class', 'chart-subtitle').text(data.length + ' races');

  appendChartLegend(box, data);

  const sMargin = {{top: 20, right: 60, bottom: 50, left: 60}};
  const sW = 680 - sMargin.left - sMargin.right;
  const sH = 350 - sMargin.top - sMargin.bottom;

  const svg = box.append('svg')
    .attr('viewBox', '0 0 680 350')
    .attr('preserveAspectRatio', 'xMidYMid meet')
    .append('g').attr('transform', 'translate(' + sMargin.left + ',' + sMargin.top + ')');

  const sx = d3.scaleLinear()
    .domain([d3.min(data, d=>d.race_time) - 5, d3.max(data, d=>d.race_time) + 5])
    .range([0, sW]);

  const sy = d3.scaleBand()
    .domain(allPositions)
    .range([0, sH])
    .padding(0.15);

  // Violin density shading per position
  const sThresholds = sx.ticks(100);
  const sBw = 4;

  allPositions.forEach(p => {{
    const pTimes = data.filter(d => d.position === p).map(d => d.race_time);
    if (pTimes.length < 2) return;

    const density = stripKde(stripEpanechnikov(sBw), sThresholds, pTimes);
    const maxD = d3.max(density, d => d[1]);
    if (maxD === 0) return;

    const bandH = sy.bandwidth();
    const centerY = sy(p) + bandH / 2;
    const violinScale = d3.scaleLinear().domain([0, maxD]).range([0, bandH * 0.4]);

    const area = d3.area()
      .x(d => sx(d[0]))
      .y0(d => centerY + violinScale(d[1]))
      .y1(d => centerY - violinScale(d[1]))
      .curve(d3.curveBasis);

    svg.append('path')
      .datum(density)
      .attr('d', area)
      .attr('fill', posColors[p])
      .attr('fill-opacity', 0.075)
      .attr('stroke', posColors[p])
      .attr('stroke-opacity', 0.15)
      .attr('stroke-width', 1);
  }});

  // Draw markers with car color/shape
  data.forEach(d => {{
    const bandCenter = sy(d.position) + sy.bandwidth() / 2;
    const jitter = (Math.random() - 0.5) * sy.bandwidth() * 0.5;
    const cx = sx(d.race_time);
    const cy = bandCenter + jitter;

    svg.append('path')
      .attr('d', symbolPath(d.shape))
      .attr('transform', 'translate(' + cx + ',' + cy + ')')
      .attr('fill', d.color)
      .attr('stroke', '#1a1a2e')
      .attr('stroke-width', 1)
      .attr('opacity', 0.85)
      .attr('cursor', 'pointer')
      .on('mouseover', function(event) {{
        d3.select(this).attr('stroke', '#fff').attr('stroke-width', 2);
        showTooltip();
        tooltip.html(
          '<b>' + d.car_name + '</b> (' + d.car_item_name + ')<br>' +
          'Time: <b>' + fmtTime(d.race_time) + '</b><br>' +
          'Position: ' + posLabels[d.position] + '<br>' +
          '<a href="https://www.torn.com/page.php?sid=racing&tab=log&raceID=' + d.race_id + '" target="_blank" style="color:#4a90d9;">View race</a>'
        );
        positionTooltip(event);
      }})
      .on('mouseout', function() {{
        d3.select(this).attr('stroke', '#1a1a2e').attr('stroke-width', 1);
        scheduleHide();
      }});
  }});

  // X axis
  svg.append('g').attr('class', 'axis')
    .attr('transform', 'translate(0,' + sH + ')')
    .call(d3.axisBottom(sx).ticks(8).tickFormat(d => fmtTime(d)));

  svg.append('text').attr('x', sW/2).attr('y', sH + 40)
    .attr('text-anchor','middle').attr('fill','#888').attr('font-size','12px')
    .text('Race Time');

  // Y axis — position labels
  allPositions.forEach(p => {{
    const pCount = data.filter(d => d.position === p).length;
    if (pCount === 0) return;
    svg.append('text')
      .attr('x', -10)
      .attr('y', sy(p) + sy.bandwidth()/2)
      .attr('text-anchor', 'end')
      .attr('dominant-baseline', 'central')
      .attr('fill', posColors[p])
      .attr('font-size', '12px')
      .attr('font-weight', 'bold')
      .text(posLabels[p]);
  }});

  // Count labels
  allPositions.forEach(p => {{
    const pCount = data.filter(d => d.position === p).length;
    if (pCount === 0) return;
    svg.append('text')
      .attr('x', sW + 8)
      .attr('y', sy(p) + sy.bandwidth()/2)
      .attr('dominant-baseline', 'central')
      .attr('fill', '#666')
      .attr('font-size', '10px')
      .text('n=' + pCount);
  }});

}});

// === FIELD COMPOSITION STACKED AREA CHARTS ===
const metaColors = [
  '#4a90d9', '#e85d4a', '#50c878', '#daa520', '#bb77dd',
  '#666666',  // "Other"
];

const metaChartsDiv = d3.select('#meta-charts');

sortedTrackIds.forEach(tid => {{
  const key = String(tid);
  const meta = metaData[key];
  if (!meta || meta.series.length < 2) return;

  const trackName = trackNames[key] || ('Track ' + tid);
  const cars = meta.cars;  // top 5 + "Other"
  const series = meta.series;

  // Convert to percentages
  const pctSeries = series.map(d => {{
    const out = {{ month: d.month }};
    cars.forEach(car => {{
      out[car] = d.total > 0 ? (d[car] || 0) / d.total : 0;
    }});
    return out;
  }});

  const box = metaChartsDiv.append('div').attr('class', 'chart-box');
  box.append('div').attr('class', 'chart-title').text(trackName);

  const metaMargin = {{top: 20, right: 150, bottom: 50, left: 60}};
  const metaW = 680 - metaMargin.left - metaMargin.right;
  const metaH = 280 - metaMargin.top - metaMargin.bottom;

  const svg = box.append('svg')
    .attr('viewBox', '0 0 680 280')
    .attr('preserveAspectRatio', 'xMidYMid meet')
    .append('g')
    .attr('transform', 'translate(' + metaMargin.left + ',' + metaMargin.top + ')');

  // Parse months to dates for x scale
  const parseMonth = d => new Date(d.month + '-15');
  const x = d3.scaleTime()
    .domain(d3.extent(pctSeries, parseMonth))
    .range([0, metaW]);

  const y = d3.scaleLinear()
    .domain([0, 1])
    .range([metaH, 0]);

  const color = d3.scaleOrdinal()
    .domain(cars)
    .range(metaColors.slice(0, cars.length));

  // Stack
  const stack = d3.stack()
    .keys(cars)
    .order(d3.stackOrderNone)
    .offset(d3.stackOffsetNone);

  const stacked = stack(pctSeries);

  // Area generator
  const area = d3.area()
    .x(d => x(new Date(d.data.month + '-15')))
    .y0(d => y(d[0]))
    .y1(d => y(d[1]))
    .curve(d3.curveMonotoneX);

  // Draw areas
  svg.selectAll('.layer')
    .data(stacked)
    .enter().append('path')
    .attr('class', 'layer')
    .attr('d', area)
    .attr('fill', d => color(d.key))
    .attr('opacity', 0.8);

  // Axes
  svg.append('g').attr('class', 'axis')
    .attr('transform', 'translate(0,' + metaH + ')')
    .call(d3.axisBottom(x).ticks(series.length > 6 ? 6 : series.length).tickFormat(d3.timeFormat('%b %y')));

  svg.append('g').attr('class', 'axis')
    .call(d3.axisLeft(y).ticks(5).tickFormat(d => Math.round(d * 100) + '%'));

  // Legend (right side)
  const legendG = svg.append('g')
    .attr('transform', 'translate(' + (metaW + 10) + ', 0)');

  cars.forEach((car, i) => {{
    const g = legendG.append('g')
      .attr('transform', 'translate(0,' + (i * 18) + ')');
    g.append('rect')
      .attr('width', 12).attr('height', 12)
      .attr('fill', color(car)).attr('opacity', 0.8);
    g.append('text')
      .attr('x', 16).attr('y', 10)
      .attr('fill', '#ccc').attr('font-size', '10px')
      .text(car.length > 16 ? car.slice(0, 14) + '..' : car);
  }});

  // Hover: show month breakdown
  svg.append('rect')
    .attr('width', metaW).attr('height', metaH)
    .attr('fill', 'transparent')
    .on('mousemove', function(event) {{
      const [mx] = d3.pointer(event);
      const dateAtMouse = x.invert(mx);
      // Find nearest month
      let nearest = pctSeries[0];
      let minDist = Infinity;
      pctSeries.forEach(d => {{
        const dist = Math.abs(new Date(d.month + '-15') - dateAtMouse);
        if (dist < minDist) {{ minDist = dist; nearest = d; }}
      }});
      const orig = series.find(s => s.month === nearest.month);

      let html = '<b>' + nearest.month + '</b><br>';
      cars.forEach((car, i) => {{
        const count = orig[car] || 0;
        const pct = Math.round((nearest[car] || 0) * 100);
        if (count > 0) {{
          html += '<span style="color:' + metaColors[i] + ';">■</span> ' + car + ': ' + count + ' (' + pct + '%)<br>';
        }}
      }});
      html += 'Total opponents: ' + orig.total;

      showTooltip();
      tooltip.html(html);
      positionTooltip(event);
    }})
    .on('mouseout', scheduleHide);
}});
</script>
</body>
</html>'''


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Torn racing dashboard — fetch, cache, and visualize race data"
    )
    parser.add_argument("--key", default=os.environ.get("TORN_API_KEY", ""),
                        help="Torn API key (or set TORN_API_KEY env var)")
    parser.add_argument("--output", default="racing_dashboard.html",
                        help="Output HTML file (default: racing_dashboard.html)")
    parser.add_argument("--cache", default="cache_races.json",
                        help="Cache file path (default: cache_races.json)")
    parser.add_argument("--events", default="Racing.json",
                        help="Optional Racing.json event log path")
    parser.add_argument("--no-fetch", action="store_true",
                        help="Skip API fetch, rebuild from existing cache only")
    args = parser.parse_args()

    if not args.no_fetch and not args.key:
        print("Error: API key required. Use --key, set TORN_API_KEY env var, or add it to .env", file=sys.stderr)
        sys.exit(1)

    # --- Determine user ID ---
    if args.no_fetch:
        # Try to infer from cache
        existing = load_cache(args.cache)
        if not existing:
            print("Error: --no-fetch but no cache file found.", file=sys.stderr)
            sys.exit(1)
        # Find the most common driver across all races
        driver_counts = Counter()
        for race in existing:
            for r in race.get("results", []):
                driver_counts[r["driver_id"]] += 1
        # The user appears in every race they participated in
        user_id = driver_counts.most_common(1)[0][0]
        print(f"Inferred user ID: {user_id}")
        races = existing
    else:
        print("Fetching user profile ...")
        user_id = fetch_user_id(args.key)
        print(f"User ID: {user_id}")

        # --- Fetch and merge ---
        existing = load_cache(args.cache)
        print(f"Existing cache: {len(existing)} races")

        since = latest_cache_timestamp(existing) if existing else None
        if since:
            since_str = datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M")
            print(f"Fetching races since {since_str} ...")
        else:
            print("Fetching all races from API ...")
        fresh = fetch_races(args.key, since=since)

        races = merge_and_save(existing, fresh, args.cache)
        new_count = len(races) - len(existing)
        print(f"Merged: {len(races)} races ({'+' if new_count >= 0 else ''}{new_count} net new)")

    # --- Car styles (load config or auto-generate from API + race data) ---
    print("Loading car config ...")
    car_styles = build_car_styles(args.key if not args.no_fetch else None, races, user_id)
    print(f"  {len(car_styles)} cars configured")

    # --- Extract data ---
    track_data = extract_track_data(races, user_id, car_styles)

    for tid in sorted(track_data.keys()):
        points = track_data[tid]
        cars = sorted(set(p["car_name"] for p in points))
        print(f"  {TRACK_NAMES[tid]}: {len(points)} races ({', '.join(cars)})")

    # --- Event log (optional) ---
    event_log = load_event_log(args.events)
    if event_log:
        earliest = datetime.fromtimestamp(event_log[0]["date"] / 1000)
        latest = datetime.fromtimestamp(event_log[-1]["date"] / 1000)
        print(f"\nEvent log: {len(event_log)} finishes ({earliest:%Y-%m-%d} to {latest:%Y-%m-%d})")
    else:
        print(f"\nNo event log found at {args.events}, podium rate charts will use cache data only")

    # --- Meta data ---
    meta_data = extract_meta_data(races, user_id)
    print(f"Field composition: {len(meta_data)} tracks")

    # --- Generate ---
    html = generate_html(track_data, event_log, meta_data, car_styles)
    with open(args.output, "w") as f:
        f.write(html)

    print(f"\nWritten {len(html):,} bytes to {args.output}")


if __name__ == "__main__":
    main()
