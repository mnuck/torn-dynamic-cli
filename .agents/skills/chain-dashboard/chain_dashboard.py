#!/usr/bin/env python3
"""Chain Hit Race dashboard generator.

Fetches every hit in the faction's current (or a given) chain from the Torn
API v2 and renders an animated bar-chart-race: horizontal bars, one per
attacker, showing cumulative hits as of a scrubbable point in the chain.

Usage:
    python3 chain_dashboard.py --key YOUR_API_KEY
    python3 chain_dashboard.py                    # uses TORN_API_KEY from .env or env var
    python3 chain_dashboard.py --chain-id 61682092  # a past (completed) chain

Options:
    --key KEY        Torn API key (or set TORN_API_KEY in .env or env var)
    --output FILE    Output HTML path (default: generated/chain_dashboard.html)
    --chain-id ID    Chain id to render (default: the faction's current live chain)
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error

API_BASE = "https://api.torn.com/v2"

# Dark-mode categorical palette (dataviz skill reference palette, 8-hue fixed
# order). Cycled across attackers in order of first appearance -- with every
# bar directly labeled by name, color here is a secondary/decorative identity
# channel, not the only one, so cycling past 8 is acceptable.
PALETTE = [
    "#3987e5",  # blue
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#008300",  # green
    "#9085e9",  # violet
    "#e66767",  # red
    "#d55181",  # magenta
    "#d95926",  # orange
]


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


def api_get(url, api_key, retries=5):
    headers = {
        "Authorization": f"ApiKey {api_key}",
        "User-Agent": "TornChainDashboard/1.0",
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


def fetch_current_chain(api_key):
    data = api_get(f"{API_BASE}/faction/chain", api_key)
    return data.get("chain", {})


def fetch_chain_attacks(api_key, faction_id, chain_start, chain_end=None):
    """Fetch every outgoing attack from chain_start onward, following
    pagination, filtered to hits landed by our own faction members."""
    url = f"{API_BASE}/faction/attacks?limit=1000&filters=attack&sort=asc&from={chain_start}"
    if chain_end:
        url += f"&to={chain_end}"

    by_chain_num = {}
    page = 0
    while url:
        page += 1
        print(f"  Fetching attacks page {page} ...", end=" ", flush=True)
        data = api_get(url, api_key)
        attacks = data.get("attacks", [])
        print(f"{len(attacks)} records")
        for a in attacks:
            attacker = a.get("attacker")
            if not attacker:
                continue
            fac = attacker.get("faction")
            if not fac or fac.get("id") != faction_id:
                continue
            n = a.get("chain", 0)
            if n <= 0:
                continue  # non-counting result (miss/lost/escape/interrupt/etc.)
            by_chain_num[n] = {
                "chain": n,
                "ts": a.get("started"),
                "id": attacker["id"],
                "name": attacker.get("name", f"#{attacker['id']}"),
            }
        url = (data.get("_metadata", {}) or {}).get("links", {}).get("next")

    return [by_chain_num[k] for k in sorted(by_chain_num)]


def assign_colors(hits):
    colors = {}
    order = []
    for h in hits:
        if h["id"] not in colors:
            colors[h["id"]] = PALETTE[len(order) % len(PALETTE)]
            order.append(h["id"])
    return colors


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Chain Hit Race</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  :root {{ --bg:#1a1a2e; --panel:#16213e; --ink:#e0e0e0; --muted:#888; --border:#0f3460; --accent:#48dbfb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif; }}
  header {{ padding:24px 28px 8px; text-align:center; }}
  h1 {{ margin:0; font-size:28px; font-weight:bold; }}
  .sub {{ color:var(--muted); font-size:14px; margin-top:8px; }}
  .badge {{ display:inline-block; margin-left:8px; padding:2px 10px; border-radius:10px;
            font-size:11px; font-weight:bold; letter-spacing:0.03em; vertical-align:middle; }}
  .badge.live {{ background:#008300; color:#eaffea; }}
  .badge.done {{ background:var(--border); color:var(--muted); }}
  .progress-wrap {{ max-width:900px; margin:18px auto 0; padding:0 28px; }}
  .progress-track {{ background:var(--panel); border:1px solid var(--border); border-radius:8px;
                      height:22px; overflow:hidden; position:relative; }}
  .progress-fill {{ background:linear-gradient(90deg,#3987e5,#199e70); height:100%;
                     transition:width .2s ease; }}
  .progress-label {{ text-align:center; font-size:12px; color:var(--muted); margin-top:6px; }}
  .panel {{ background:var(--panel); border:1px solid var(--border); border-radius:10px;
            max-width:900px; margin:22px auto; padding:20px 24px 16px; }}
  .controls {{ display:flex; align-items:center; gap:14px; margin-bottom:14px; flex-wrap:wrap; }}
  .controls button {{ background:var(--bg); color:var(--ink); border:1px solid var(--border);
                       border-radius:6px; padding:8px 16px; font-size:14px; cursor:pointer;
                       font-family:inherit; }}
  .controls button:hover {{ border-color:var(--accent); }}
  .controls input[type=range] {{ flex:1; min-width:200px; accent-color:var(--accent); }}
  .controls select {{ background:var(--bg); color:var(--ink); border:1px solid var(--border);
                       border-radius:6px; padding:6px 10px; font-size:13px; font-family:inherit; }}
  .scrub-readout {{ text-align:center; font-size:13px; color:var(--muted); margin:0 0 10px; }}
  .scrub-readout b {{ color:var(--ink); }}
  #chart {{ display:block; margin:0 auto; }}
  .bar-label {{ font-size:13px; fill:var(--ink); }}
  .bar-value {{ font-size:12px; fill:var(--muted); font-variant-numeric:tabular-nums; }}
  .axis text {{ fill:var(--muted); font-size:11px; }}
  .axis path, .axis line {{ stroke:#333; }}
  .toggle-table {{ text-align:center; margin:6px 0 16px; }}
  .toggle-table button {{ background:none; border:none; color:var(--accent); cursor:pointer;
                           font-size:13px; text-decoration:underline; font-family:inherit; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; display:none; }}
  table.shown {{ display:table; }}
  th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:normal; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; padding:10px 0 30px; }}
</style>
</head>
<body>
<header>
  <h1>Chain Hit Race <span class="badge {live_class}">{live_text}</span></h1>
  <div class="sub">{faction_name} &middot; chain #{chain_id} &middot; started {start_str}</div>
</header>

<div class="progress-wrap">
  <div class="progress-track"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
  <div class="progress-label" id="progressLabel"></div>
</div>

<div class="panel">
  <div class="controls">
    <button id="playBtn">&#9654; Play</button>
    <input type="range" id="scrub" min="0" max="{max_index}" value="{max_index}" step="1">
    <select id="speed">
      <option value="400">Slow</option>
      <option value="150" selected>Normal</option>
      <option value="60">Fast</option>
      <option value="15">Ludicrous</option>
    </select>
  </div>
  <div class="scrub-readout" id="readout"></div>
  <svg id="chart"></svg>
  <div class="toggle-table">
    <button id="tableToggle">Show full leaderboard table</button>
  </div>
  <table id="leaderboard">
    <thead><tr><th>#</th><th>Member</th><th class="num">Hits</th><th class="num">Share</th></tr></thead>
    <tbody></tbody>
  </table>
</div>

<footer>Bar color is stable per member across the whole timeline &mdash; it does not encode rank.</footer>

<script>
const HITS = {hits_json};
const COLORS = {colors_json};
const GOAL = {goal};

const N = HITS.length;
const TOP_N = 14;
const barH = 30, barGap = 6, margin = {{top: 10, right: 70, bottom: 10, left: 150}};
const width = 852;
const chartHeight = TOP_N * (barH + barGap) + margin.top + margin.bottom;

const svg = d3.select('#chart').attr('width', width).attr('height', chartHeight);
const plot = svg.append('g').attr('transform', `translate(${{margin.left}},${{margin.top}})`);

const x = d3.scaleLinear().range([0, width - margin.left - margin.right]);
// Row position is a fixed function of rank index, not a re-flowing
// scaleBand: with a band scale, bandwidth (and therefore the label's
// vertical-center offset, set once at enter time) depends on how many
// entries are ranked, which grows over the timeline -- an offset baked in
// early drifts out of alignment once more rows are present later.
const rowStep = barH + barGap;
const yPos = i => i * rowStep;

const scrub = document.getElementById('scrub');
const readout = document.getElementById('readout');
const progressFill = document.getElementById('progressFill');
const progressLabel = document.getElementById('progressLabel');
const playBtn = document.getElementById('playBtn');
const speedSel = document.getElementById('speed');

function computeTotals(index) {{
  const totals = new Map();
  for (let i = 0; i < index; i++) {{
    const h = HITS[i];
    totals.set(h.id, (totals.get(h.id) || 0) + 1);
  }}
  return totals;
}}

function render(index) {{
  index = Math.max(0, Math.min(N, index));
  scrub.value = index;
  const totals = computeTotals(index);
  const ranked = Array.from(totals, ([id, count]) => ({{
    id, count, name: nameFor(id), color: COLORS[id] || '#666'
  }})).sort((a, b) => b.count - a.count).slice(0, TOP_N);
  ranked.forEach((d, i) => {{ d.rank = i; }});

  x.domain([0, Math.max(1, ranked.length ? ranked[0].count : 1)]);

  const bars = plot.selectAll('g.row').data(ranked, d => d.id);

  const enter = bars.enter().append('g').attr('class', 'row')
    .attr('transform', d => `translate(0,${{yPos(d.rank)}})`)
    .style('opacity', 1);
  enter.append('rect').attr('x', 0).attr('height', barH)
    .attr('rx', 4).attr('ry', 4).attr('fill', d => d.color).attr('width', 0);
  enter.append('text').attr('class', 'bar-label').attr('x', -10).attr('text-anchor', 'end')
    .attr('y', barH / 2).attr('dy', '0.35em').text(d => d.name);
  enter.append('text').attr('class', 'bar-value').attr('y', barH / 2)
    .attr('dy', '0.35em');

  // Rows can leave the top-N and later rejoin it; a rejoining row reuses its
  // old (keyed) DOM node via the update selection rather than enter(), so its
  // exit fade-out must be cancelled and opacity restored here or it stays
  // invisible forever after its first exit.
  const merged = enter.merge(bars);
  merged.interrupt().style('opacity', 1);
  merged.transition().duration(180).ease(d3.easeLinear)
    .attr('transform', d => `translate(0,${{yPos(d.rank)}})`);
  merged.select('rect').transition().duration(180).ease(d3.easeLinear)
    .attr('width', d => x(d.count));
  merged.select('text.bar-value')
    .attr('x', d => x(d.count) + 8)
    .text(d => d.count.toLocaleString());

  bars.exit().interrupt().transition().duration(150).style('opacity', 0).remove();

  const ts = index > 0 ? HITS[index - 1].ts * 1000 : (HITS[0] ? HITS[0].ts * 1000 : Date.now());
  const dt = new Date(ts);
  readout.innerHTML = `Hit <b>${{index.toLocaleString()}}</b> of <b>${{N.toLocaleString()}}</b> &middot; ${{dt.toLocaleString()}}`;

  const pct = Math.min(100, (index / GOAL) * 100);
  progressFill.style.width = pct + '%';
  progressLabel.textContent = `${{index.toLocaleString()}} / ${{GOAL.toLocaleString()}} toward the ${{GOAL.toLocaleString()}} milestone`;

  renderTable(totals);
}}

const namesCache = new Map();
function nameFor(id) {{
  if (namesCache.has(id)) return namesCache.get(id);
  const h = HITS.find(h => h.id === id);
  const nm = h ? h.name : ('#' + id);
  namesCache.set(id, nm);
  return nm;
}}

function renderTable(totals) {{
  const tbody = document.querySelector('#leaderboard tbody');
  const grandTotal = Array.from(totals.values()).reduce((a, b) => a + b, 0) || 1;
  const rows = Array.from(totals, ([id, count]) => ({{ id, count, name: nameFor(id) }}))
    .sort((a, b) => b.count - a.count);
  tbody.innerHTML = rows.map((r, i) => `
    <tr><td>${{i + 1}}</td><td>${{r.name}}</td><td class="num">${{r.count.toLocaleString()}}</td>
    <td class="num">${{(100 * r.count / grandTotal).toFixed(1)}}%</td></tr>
  `).join('');
}}

document.getElementById('tableToggle').addEventListener('click', () => {{
  const t = document.getElementById('leaderboard');
  t.classList.toggle('shown');
}});

let playing = false, timer = null;
function stepPlay() {{
  let idx = parseInt(scrub.value, 10) + Math.max(1, Math.round(N / 400));
  if (idx >= N) {{ idx = N; stopPlay(); }}
  render(idx);
}}
function startPlay() {{
  if (parseInt(scrub.value, 10) >= N) render(0);
  playing = true;
  playBtn.innerHTML = '&#10074;&#10074; Pause';
  timer = setInterval(stepPlay, parseInt(speedSel.value, 10));
}}
function stopPlay() {{
  playing = false;
  playBtn.innerHTML = '&#9654; Play';
  clearInterval(timer);
}}
playBtn.addEventListener('click', () => playing ? stopPlay() : startPlay());
speedSel.addEventListener('change', () => {{ if (playing) {{ stopPlay(); startPlay(); }} }});
scrub.addEventListener('input', () => {{ stopPlay(); render(parseInt(scrub.value, 10)); }});

render(N);
</script>
</body>
</html>
"""


def build_html(faction_id, faction_name, chain, hits, output_path):
    colors = assign_colors(hits)
    is_live = chain.get("timeout", 0) > 0 and not chain.get("cooldown")
    start_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(chain.get("start", 0)))
    goal = chain.get("max") or (((len(hits) // 2500) + 1) * 2500) or 2500

    html = HTML_TEMPLATE.format(
        faction_name=faction_name,
        chain_id=chain.get("id", "?"),
        start_str=start_str,
        live_class="live" if is_live else "done",
        live_text="LIVE" if is_live else "COMPLETE",
        max_index=len(hits),
        hits_json=json.dumps([{"id": h["id"], "name": h["name"], "ts": h["ts"]} for h in hits]),
        colors_json=json.dumps({str(k): v for k, v in colors.items()}),
        goal=goal,
    )

    _ensure_parent_dir(output_path)
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Wrote {output_path} ({len(hits)} hits, {len(colors)} attackers)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", default=os.environ.get("TORN_API_KEY", ""),
                         help="Torn API key (or set TORN_API_KEY env var)")
    parser.add_argument("--output", default="generated/chain_dashboard.html", help="Output HTML path")
    parser.add_argument("--chain-id", type=int, default=None,
                         help="Specific chain id to render (default: current live chain)")
    args = parser.parse_args()

    load_dotenv()
    api_key = args.key or os.environ.get("TORN_API_KEY", "")
    if not api_key:
        print("Error: API key required. Use --key, set TORN_API_KEY env var, or add it to .env", file=sys.stderr)
        sys.exit(1)

    print("Fetching faction info ...")
    faction_id, faction_name = fetch_faction_basic(api_key)

    if args.chain_id:
        chain = {"id": args.chain_id}
        report = api_get(f"{API_BASE}/faction/chainreport?chainId={args.chain_id}", api_key)
        cr = report.get("chainreport", {})
        chain["start"] = cr.get("start")
        chain["end"] = cr.get("end")
        chain["timeout"] = 0
        chain["max"] = cr.get("details", {}).get("chain")
    else:
        print("Fetching current chain status ...")
        chain = fetch_current_chain(api_key)
        if not chain or not chain.get("id"):
            print("No active chain found. Pass --chain-id to render a past chain.", file=sys.stderr)
            sys.exit(1)

    print(f"Chain #{chain['id']}, start={chain.get('start')}")
    hits = fetch_chain_attacks(api_key, faction_id, chain["start"], chain.get("end"))
    print(f"Collected {len(hits)} hits from {len(set(h['id'] for h in hits))} attackers")

    build_html(faction_id, faction_name, chain, hits, args.output)


if __name__ == "__main__":
    main()
