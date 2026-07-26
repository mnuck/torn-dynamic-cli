#!/usr/bin/env python3
"""Fast-band delta trace: the coin-removed capability gap between the requesting
driver and every opponent in a single Torn race, cumulative across the lap.

Input is one race's full-field telemetry as captured from the browser racingData
endpoint (see SKILL.md for the fetch snippet), shape:

    {
      "raceID": 19847555,
      "me": "WillieMcCoy",          # requesting driver = the reference line
      "trackID": 10,
      "meta": {"laps": 5, "perLap": 82, "intervals": [ ... perLap floats ]},
      "drivers": [
        {"name": "WillieMcCoy", "carTitle": "Volt GT", "parts": [ laps*perLap floats ]},
        ...
      ]
    }

Why "fast band" and not raw laps: every segment's speed is bimodal — a hidden
per-car coin flips between a fast state and a slow state (slow = fast / 1.222).
A single race is dominated by who drew the fast state where, which is luck. The
fast-band center (mean of the upper cluster per segment) strips the coin out and
leaves car + line + skill — the part that actually means something. The delta
trace then accumulates (opponent_time - my_time) per segment, so the final value
is the true per-lap capability gap and the *slope* shows where it is built
(flat on straights, stair-stepping up at corners).

Usage:
    python3 fastband_delta.py <field.json> [--output generated/fastband_delta_<id>.html]
"""
import argparse
import json
import os
import sys
from statistics import mean

# Torn track ids -> names (website trackID, matches racingData trackID)
TRACK_NAMES = {
    6: "Uptown", 7: "Withdrawal", 8: "Underdog", 9: "Parkland", 10: "Docks",
    11: "Commerce", 12: "Two Islands", 15: "Industrial", 16: "Vector",
    17: "Mudpit", 18: "Hammerhead", 19: "Sewage", 20: "Meltdown",
    21: "Speedway", 23: "Stone Park", 24: "Convict",
}

# Distinct, colorblind-friendly-ish palette for up to ~8 opponents.
PALETTE = ["#e34948", "#2a78d6", "#1baf7a", "#eda100", "#8b5cf6",
           "#e8730a", "#d94f9a", "#5b8c5a"]


def fast_band(parts, intervals, perLap, laps):
    """Per-segment fast-band center. For each segment, split the per-lap speeds
    at the largest multiplicative gap; if a real gap exists (>= the ~1.222 coin
    signature, thresholded loosely at 1.08) take the mean of the upper (fast)
    cluster, otherwise the segment never flipped this race so take the best
    sample as the fast-state estimate."""
    out = []
    for s in range(perLap):
        speeds = sorted(intervals[s] / parts[lap * perLap + s] for lap in range(laps))
        gi, gr = -1, 1.0
        for i in range(1, len(speeds)):
            g = speeds[i] / speeds[i - 1]
            if g > gr:
                gr, gi = g, i
        out.append(mean(speeds[gi:]) if gr >= 1.08 else max(speeds))
    return out


def build(field):
    meta = field["meta"]
    iv, P, L = meta["intervals"], meta["perLap"], meta["laps"]
    me_name = field["me"]

    profiles = {}
    for d in field["drivers"]:
        if len(d["parts"]) != L * P:  # skip malformed / partial telemetry
            continue
        profiles[d["name"]] = {"fb": fast_band(d["parts"], iv, P, L),
                               "car": d.get("carTitle") or "?"}
    if me_name not in profiles:
        sys.exit(f"reference driver {me_name!r} not present / has bad telemetry")

    me_fb = profiles[me_name]["fb"]
    me_car_type = profiles[me_name]["car"]
    me_car_name = field.get("meCarName")
    me_car = f"{me_car_name} ({me_car_type})" if me_car_name else me_car_type
    t_me = [iv[s] / me_fb[s] for s in range(P)]
    speed_me = [round(iv[s] / t_me[s], 3) for s in range(P)]

    series = []
    for name, p in profiles.items():
        if name == me_name:
            continue
        t_opp = [iv[s] / p["fb"][s] for s in range(P)]
        cum, c = [], 0.0
        for s in range(P):
            c += t_opp[s] - t_me[s]  # + => reference driver is faster
            cum.append(round(c, 3))
        series.append({"name": name, "car": p["car"], "final": round(cum[-1], 2),
                       "cum": cum})
    # biggest gap first, so the legend reads worst-beaten -> closest rival
    series.sort(key=lambda x: -x["final"])
    for i, srs in enumerate(series):
        srs["color"] = PALETTE[i % len(PALETTE)]
    return series, P, speed_me, iv, me_car


# Track SVG paths (viewBox + path d) are scraped once per track from the racing
# page's inline #Layer_1 svg and cached here. Torn's own player animates cars
# with path.getPointAt(completion * length), so distance along this path is the
# same coordinate system as the intervals array (which sums to 100 = one lap).
TRACK_PATH_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "data", "track_paths.json")


def load_track_path(field):
    """Track geometry from the field JSON if the fetch grabbed it, else from the
    cache; a fresh copy in the field JSON refreshes the cache entry."""
    tid = str(field.get("trackID"))
    cache = {}
    try:
        cache = json.load(open(TRACK_PATH_CACHE))
    except (OSError, ValueError):
        pass
    tp = field.get("track")
    if tp and tp.get("d"):
        if cache.get(tid) != tp:
            cache[tid] = tp
            os.makedirs(os.path.dirname(TRACK_PATH_CACHE), exist_ok=True)
            json.dump(cache, open(TRACK_PATH_CACHE, "w"), indent=1)
        return tp
    return cache.get(tid)


def render_map_section(track_path, me):
    if not track_path:
        return ("<!-- no track path available: fetch it from the racing page's "
                "#Layer_1 svg (see SKILL.md) -->")
    return f"""<div class="panel col">
<h2>Track map</h2>
<div class="sub">Ribbon colored by {me}'s fast-band speed (red = slow corner, green = fast straight).
Hover either chart to light up the checkpoint on the map; hover a map dot to cursor both charts.</div>
<div id="mapwrap"></div>
</div>"""


def render_html(field, series, P, speed, iv, track_path, me_car):
    rid = field.get("raceID", "?")
    track = TRACK_NAMES.get(field.get("trackID"), f"track {field.get('trackID')}")
    me = field["me"]
    map_section = render_map_section(track_path, me)
    track_json = json.dumps(track_path) if track_path else "null"
    iv_json = json.dumps(iv)
    speed_json = json.dumps(speed)
    datasets = ",".join(
        "{{label:{n},data:{d},borderColor:{c},borderWidth:2,pointRadius:0,"
        "pointHoverRadius:4,tension:0.15}}".format(
            n=json.dumps(s["name"]), d=json.dumps(s["cum"]), c=json.dumps(s["color"]))
        for s in series)
    legend = "".join(
        '<span class="item" data-index="{i}"><span class="swatch" style="background:{c}"></span>'
        '{n} ({car}) {sign}{f}s</span>'.format(
            i=i, c=s["color"], n=s["name"], car=s["car"].split(" ")[0],
            sign="+" if s["final"] >= 0 else "", f=s["final"])
        for i, s in enumerate(series))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Race Analysis — race {rid}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
 :root {{ --bg:#1a1a2e; --panel:#16213e; --ink:#e0e0e0; --muted:#888; --border:#0f3460; --accent:#48dbfb; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--ink);
         font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif; }}
 header {{ padding:24px 28px 8px; text-align:center; }}
 h1 {{ margin:0; font-size:28px; font-weight:bold; }}
 h2 {{ margin:0 0 2px; font-size:18px; text-align:center; }}
 .sub {{ color:var(--muted); font-size:13px; margin-top:8px; text-align:center; }}
 .sub a {{ color:var(--accent); text-decoration:none; }}
 .sub a:hover {{ text-decoration:underline; }}
 .panel {{ background:var(--panel); border:1px solid var(--border); border-radius:10px;
           max-width:1400px; margin:22px auto; padding:20px 24px 16px; }}
 .row {{ display:flex; gap:24px; flex-wrap:wrap; align-items:flex-start;
         max-width:1400px; margin:0 auto; padding:0 16px; }}
 .row .panel.col {{ flex:1 1 480px; min-width:0; margin:22px 0; }}
 .legend {{ display:flex; justify-content:center; flex-wrap:wrap; gap:14px;
            margin-top:16px; margin-bottom:8px; font-size:12px; color:var(--muted); }}
 .legend .item {{ display:flex; align-items:center; gap:5px; cursor:pointer; user-select:none; }}
 .legend .item.hidden {{ opacity:0.35; text-decoration:line-through; }}
 .legend .swatch {{ width:14px; height:3px; display:inline-block; }}
 .axis-lock {{ text-align:center; font-size:12px; color:var(--muted); margin-bottom:10px; }}
 .axis-lock label {{ cursor:pointer; user-select:none; }}
 .axis-lock input {{ accent-color:var(--accent); vertical-align:middle; margin-right:4px; }}
 .wrap {{ position:relative; height:420px; }}
 .wrap.speed {{ position:relative; height:300px; }}
 #mapwrap svg{{width:100%;height:auto;display:block;background:#12172b;border:1px solid var(--border);border-radius:6px}}
</style></head><body>
<header>
<h1>Race Analysis</h1>
<div class="sub"><a href="https://www.torn.com/page.php?sid=racing&amp;tab=log&amp;raceID={rid}" target="_blank" rel="noopener">Race {rid}</a> &middot; {track} &middot; {me} driving {me_car}</div>
</header>
<div class="row">
{map_section}
<div class="panel col">
<h2>Per-segment fast-band speed &mdash; {me}</h2>
<div class="sub">Distance/time per checkpoint, randomness removed. Dips are corners, peaks are straights; equal-distance runs are one corner's sub-splits.</div>
<div class="wrap speed"><canvas id="c2"></canvas></div>
</div>
</div>
<div class="panel">
<h2>Fast-band delta trace &mdash; {me} vs field</h2>
<div class="sub">Randomness-removed capability gap. Rising = {me} gaining time; final value = seconds/lap faster. Flat stretches are straights, steps are corners. Without randomness, whoever's line sits lowest (including {me}'s own baseline at zero) would win every time.</div>
<div class="legend" id="deltaLegend">{legend}</div>
<div class="axis-lock"><label><input type="checkbox" id="lockAxis"> Lock y-axis range</label></div>
<div class="wrap"><canvas id="c"></canvas></div>
</div>
<script>
const TRACK = {track_json};
const IV = {iv_json};
const SPEED = {speed_json};
const CSS = getComputedStyle(document.documentElement);
const MUTED = CSS.getPropertyValue('--muted').trim();
const BORDER = CSS.getPropertyValue('--border').trim();
const INK = CSS.getPropertyValue('--ink').trim();
const PANEL = CSS.getPropertyValue('--panel').trim();
Chart.defaults.color = MUTED;
Chart.defaults.borderColor = BORDER;
const hoverSync = {{charts: [], onIndex: null}};   // filled in below
function chartHover(evt, actives) {{
  if (actives.length && hoverSync.onIndex) hoverSync.onIndex(actives[0].index, 'chart');
}}
const chartDelta = new Chart(document.getElementById('c'),{{type:'line',
 data:{{labels:Array.from({{length:{P}}},function(_,i){{return i+1;}}),datasets:[{datasets}]}},
 options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
  onHover:chartHover,
  plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:PANEL,borderColor:BORDER,borderWidth:1,titleColor:INK,bodyColor:INK,callbacks:{{
   title:function(i){{return 'through checkpoint '+i[0].label;}},
   label:function(x){{return x.dataset.label+': '+(x.parsed.y>=0?'+':'')+x.parsed.y.toFixed(2)+'s';}}}}}}}},
  scales:{{
   x:{{title:{{display:true,text:'Checkpoint (1-{P})',color:MUTED}},grid:{{display:false}},ticks:{{color:MUTED}}}},
   y:{{title:{{display:true,text:'{me} cumulative time gained (s)',color:MUTED}},ticks:{{color:MUTED}},
      grid:{{color:function(c){{return c.tick.value===0?MUTED:BORDER;}},lineWidth:function(c){{return c.tick.value===0?2:1;}}}}}}}}}}}});
const chartSpeed = new Chart(document.getElementById('c2'),{{type:'line',
 data:{{labels:Array.from({{length:{P}}},function(_,i){{return i+1;}}),
  datasets:[{{label:'fast-band speed (dist/s)',data:SPEED,
   borderColor:'#48dbfb',backgroundColor:'rgba(72,219,251,0.12)',fill:true,
   borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.2}}]}},
 options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
  onHover:chartHover,
  plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:PANEL,borderColor:BORDER,borderWidth:1,titleColor:INK,bodyColor:INK,callbacks:{{
   title:function(i){{return 'checkpoint '+i[0].label;}},
   label:function(x){{return ['speed: '+x.parsed.y.toFixed(2),'distance: '+IV[x.dataIndex].toFixed(2)];}}}}}}}},
  scales:{{
   x:{{title:{{display:true,text:'Checkpoint (1-{P})',color:MUTED}},grid:{{display:false}},ticks:{{color:MUTED}}}},
   y:{{title:{{display:true,text:'fast-band speed (dist/s)',color:MUTED}},ticks:{{color:MUTED}},grid:{{color:BORDER}}}}}}}}}});
hoverSync.charts = [chartDelta, chartSpeed];

// Click a legend entry to hide/show that opponent's line; Chart.js excludes
// hidden datasets from its y-axis min/max calc, so the axis auto-rescales to
// whatever's left visible -- unless the lock checkbox below pins the range.
document.querySelectorAll('#deltaLegend .item').forEach(el => {{
  el.addEventListener('click', () => {{
    const idx = +el.dataset.index;
    if (chartDelta.isDatasetVisible(idx)) {{
      chartDelta.hide(idx);
      el.classList.add('hidden');
    }} else {{
      chartDelta.show(idx);
      el.classList.remove('hidden');
    }}
  }});
}});

document.getElementById('lockAxis').addEventListener('change', (event) => {{
  const y = chartDelta.options.scales.y;
  if (event.target.checked) {{
    y.min = chartDelta.scales.y.min;
    y.max = chartDelta.scales.y.max;
  }} else {{
    delete y.min;
    delete y.max;
  }}
  chartDelta.update();
}});

// ---- track map: speed-colored ribbon + checkpoint dots, hover-synced ----
if (TRACK) {{
  const NS = 'http://www.w3.org/2000/svg';
  const vb = TRACK.viewBox.split(/\\s+/).map(Number);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', TRACK.viewBox);
  document.getElementById('mapwrap').appendChild(svg);

  // Measuring path (invisible): browser does the arc-length math for us,
  // exactly like Torn's own player (path.getPointAt).
  const meas = document.createElementNS(NS, 'path');
  meas.setAttribute('d', TRACK.d);
  meas.setAttribute('fill', 'none'); meas.setAttribute('stroke', 'none');
  svg.appendChild(meas);
  const L = meas.getTotalLength();
  const at = f => meas.getPointAtLength(((f % 1) + 1) % 1 * L);

  // Checkpoint boundaries as fractions of the lap (intervals sum to 100).
  const total = IV.reduce((a, b) => a + b, 0);
  const cum = []; let c = 0;
  for (const d of IV) {{ c += d; cum.push(c / total); }}

  const spMin = Math.min(...SPEED), spMax = Math.max(...SPEED);
  const spColor = s => {{
    const t = spMax > spMin ? (s - spMin) / (spMax - spMin) : 0.5;
    return 'hsl(' + Math.round(t * 120) + ',75%,52%)';
  }};

  // Base outline under the ribbon so gaps at joins don't show.
  const base = document.createElementNS(NS, 'path');
  base.setAttribute('d', TRACK.d);
  base.setAttribute('fill', 'none'); base.setAttribute('stroke', BORDER);
  base.setAttribute('stroke-width', '7'); base.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(base);

  // Speed ribbon: each checkpoint's stretch of track as a sampled polyline.
  for (let k = 0; k < cum.length; k++) {{
    const f0 = k === 0 ? 0 : cum[k - 1], f1 = cum[k];
    const n = Math.max(2, Math.ceil((f1 - f0) * L / 3));
    let pts = [];
    for (let i = 0; i <= n; i++) {{
      const p = at(f0 + (f1 - f0) * i / n);
      pts.push(p.x.toFixed(1) + ',' + p.y.toFixed(1));
    }}
    const pl = document.createElementNS(NS, 'polyline');
    pl.setAttribute('points', pts.join(' '));
    pl.setAttribute('fill', 'none');
    pl.setAttribute('stroke', spColor(SPEED[k]));
    pl.setAttribute('stroke-width', '5');
    pl.setAttribute('stroke-linecap', 'round');
    svg.appendChild(pl);
  }}

  // Start/finish marker at lap fraction 0.
  const s0 = at(0);
  const sf = document.createElementNS(NS, 'rect');
  sf.setAttribute('x', s0.x - 3); sf.setAttribute('y', s0.y - 3);
  sf.setAttribute('width', 6); sf.setAttribute('height', 6);
  sf.setAttribute('fill', INK); sf.setAttribute('stroke', BORDER);
  sf.setAttribute('stroke-width', '1.2');
  svg.appendChild(sf);

  // Checkpoint dots (dot k = END of checkpoint k) + labels every 5th.
  const dots = [];
  for (let k = 0; k < cum.length; k++) {{
    const p = at(cum[k]);
    if ((k + 1) % 5 === 0) {{
      const tx = document.createElementNS(NS, 'text');
      tx.setAttribute('x', p.x + 6); tx.setAttribute('y', p.y - 6);
      tx.setAttribute('font-size', '9'); tx.setAttribute('fill', MUTED);
      tx.setAttribute('font-family', "'Segoe UI',Tahoma,Geneva,Verdana,sans-serif");
      tx.textContent = k + 1;
      svg.appendChild(tx);
    }}
    const dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('cx', p.x); dot.setAttribute('cy', p.y);
    dot.setAttribute('r', 2.6);
    dot.setAttribute('fill', INK); dot.setAttribute('stroke', '#12172b');
    dot.setAttribute('stroke-width', '1');
    dot.setAttribute('fill-opacity', '0.4');
    dot.setAttribute('stroke-opacity', '0.4');
    dot.style.cursor = 'pointer';
    svg.appendChild(dot);
    dots.push(dot);
  }}

  // Highlight ring, moved onto whichever checkpoint is active.
  const ring = document.createElementNS(NS, 'circle');
  ring.setAttribute('r', 6); ring.setAttribute('fill', 'none');
  ring.setAttribute('stroke', '#48dbfb'); ring.setAttribute('stroke-width', '2');
  ring.setAttribute('visibility', 'hidden');
  svg.appendChild(ring);
  const ringLabel = document.createElementNS(NS, 'text');
  ringLabel.setAttribute('font-size', '11'); ringLabel.setAttribute('fill', '#48dbfb');
  ringLabel.setAttribute('font-weight', 'bold');
  ringLabel.setAttribute('font-family', "'Segoe UI',Tahoma,Geneva,Verdana,sans-serif");
  ringLabel.setAttribute('visibility', 'hidden');
  svg.appendChild(ringLabel);

  let activeDot = null;
  function highlight(idx) {{
    const p = at(cum[idx]);
    ring.setAttribute('cx', p.x); ring.setAttribute('cy', p.y);
    ring.setAttribute('visibility', 'visible');
    ringLabel.setAttribute('x', p.x + 9); ringLabel.setAttribute('y', p.y + 4);
    ringLabel.textContent = idx + 1;
    ringLabel.setAttribute('visibility', 'visible');
    if (activeDot) {{
      activeDot.setAttribute('fill-opacity', '0.4');
      activeDot.setAttribute('stroke-opacity', '0.4');
    }}
    activeDot = dots[idx];
    activeDot.setAttribute('fill-opacity', '1');
    activeDot.setAttribute('stroke-opacity', '1');
  }}

  hoverSync.onIndex = function (idx, source) {{
    highlight(idx);
    if (source === 'map') {{
      // Cursor both charts at this checkpoint, tooltip included.
      for (const ch of hoverSync.charts) {{
        const actives = ch.data.datasets.map((_, di) => ({{datasetIndex: di, index: idx}}));
        ch.setActiveElements(actives);
        ch.tooltip.setActiveElements(actives, {{x: 0, y: 0}});
        ch.update('none');
      }}
    }}
  }};

  dots.forEach((dot, k) => {{
    dot.addEventListener('mouseenter', () => hoverSync.onIndex(k, 'map'));
  }});
  svg.addEventListener('mouseleave', () => {{
    ring.setAttribute('visibility', 'hidden');
    ringLabel.setAttribute('visibility', 'hidden');
    if (activeDot) {{
      activeDot.setAttribute('fill-opacity', '0.4');
      activeDot.setAttribute('stroke-opacity', '0.4');
      activeDot = null;
    }}
    for (const ch of hoverSync.charts) {{
      ch.setActiveElements([]); ch.tooltip.setActiveElements([], {{x: 0, y: 0}});
      ch.update('none');
    }}
  }});
}}
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("field", help="race field-telemetry JSON (see SKILL.md)")
    ap.add_argument("--output", help="output HTML path (default generated/fastband_<id>.html)")
    args = ap.parse_args()

    field = json.load(open(args.field))
    series, P, speed_me, iv, me_car = build(field)
    track_path = load_track_path(field)
    if not track_path:
        print("note: no track path for this trackID — map panel omitted "
              "(fetch it from the racing page, see SKILL.md)", file=sys.stderr)

    out = args.output or f"generated/fastband_{field.get('raceID','race')}.html"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w").write(render_html(field, series, P, speed_me, iv, track_path, me_car))

    print(f"race {field.get('raceID')} ({TRACK_NAMES.get(field.get('trackID'), field.get('trackID'))}) "
          f"— {field['me']} vs {len(series)} opponents")
    print(f"{'opponent':16s}{'car':14s}{'gap/lap':>9s}")
    for s in series:
        print(f"  {s['name']:14s}{s['car']:14s}{s['final']:>+8.2f}s")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
