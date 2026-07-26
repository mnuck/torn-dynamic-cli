---
name: fast-band-delta
description: >
  Generate a fast-band delta trace for a single Torn race — the coin-removed,
  cumulative time gap between the user (WillieMcCoy) and every opponent in that
  race, plotted across the lap. This is THE race-diagnostic instrument: it strips
  out the hidden fast/slow "coin" so the final value is true per-lap capability
  gap and the slope shows exactly where time is won or lost (flat on straights,
  stair-stepping at corners). Use this skill whenever the user asks for a "fast-band
  delta trace", a "delta trace", a "delta-t", or "where did I gain/lose vs the field"
  for a given raceID (e.g. "fast-band delta trace for raceID 19847555").
  Also holds torn_race_model.py, the generative two-coin engine simulator — use
  it for the inverse questions, where luck (not capability) is the subject:
  "what % of laps would beat my record", "is that WR reachable with my car",
  "how many laps until a new PR", "what's my car's fastest possible lap".
---

# Fast-band delta trace

Produces one "Race Analysis" dashboard per race, `generated/fastband_<raceID>.html`,
with three panels sharing the same checkpoint numbering — track map and
segment-speed side by side on top (they wrap to stacked on narrow windows),
delta trace full-width below with its own title:
- **Track map** — the track outline as a ribbon colored by the user's
  fast-band speed (red = slow corner, green = fast straight), with a dot per
  checkpoint and labels every 5th. Dots sit at 40% opacity so they don't
  obscure the ribbon color underneath; the active (hovered) checkpoint's dot
  jumps to 100% opacity alongside the highlight ring. Hover is synced both ways: hovering either
  chart lights the checkpoint's dot on the map, hovering a map dot cursors
  both charts. This is what turns "stair-step at checkpoints 31-36" into
  "the hairpin by the lake".
- **Segment speed** — the user's own fast-band speed (distance/time) at every
  checkpoint on the lap. Dips are corners, peaks are straights; runs of
  equal-distance segments are one corner's sub-splits.
- **Delta trace** — one line per opponent, cumulative coin-removed time gap.
  Rising = the user gaining time; each line's final value is the per-lap
  capability gap. Click a legend entry to hide/show that opponent (matches the
  respect/chain dashboards' convention) — the y-axis auto-rescales to whatever
  stays visible, unless "Lock y-axis range" is checked, which pins the current
  min/max so toggling series doesn't move the axis.

See `fastband_delta.py`'s docstring for the why (bimodal per-segment coin,
fast-band = upper cluster, delta = cumulative time difference).

## The other direction: `torn_race_model.py` (odds, floors, record chances)

`fastband_delta.py` removes the luck to expose capability. `torn_race_model.py`
is the inverse — it puts the luck back, generatively, so you can answer
questions the delta trace can't:

- "what % of laps would beat my record of X?"
- "is this WR even reachable with my car?"
- "how many laps until a new PR?"

```bash
python3 .agents/skills/fast-band-delta/torn_race_model.py data/docks_100lap_19608788.json --races 400
```

It prints the car's **perfect lap** (both coins fast on every segment — a real
ceiling, never achieved), then the real vs simulated lap distribution as a fit
check, then how often a race of that length produces a lap beating the real
best. Import `simulate()` / `base_speed_from()` for custom Monte Carlo.

**The engine is TWO coins, not one** (full derivation in the module docstring):
a BIG coin picking the band with a mixture dwell — 98.96% `randint(20,50)`,
**1.04% `randint(2,5)`** — and a SMALL coin re-flipped on EVERY segment that
subtracts a fixed 1.8% of base speed. So each segment has four possible times,
not two. The 1% short dwell is the entire record mechanism: on any track with
more than 50 checkpoints per lap the big coin *cannot* stay fast for a whole
lap, so every record lap is one that caught a short dwell. Fast-band "centers"
average over the small coin, which is why the old big-coin constant read 1.222
instead of the true 1.2192.

⚠️ **Needs a 100-lap race.** Resolving the small coin takes ~100 samples per
segment; at 5-15 laps it hides inside cluster spread and everything looks
merely bimodal. The per-track `data/*_telemetry.json` captures are 5-lap races
ONLY — re-fetch a 100-lapper (same snippet below) for any tail/record question.

## Two steps: fetch (claude-in-chrome) then render (python)

Per-checkpoint telemetry is **only** available from the browser `racingData`
endpoint — the CLI / API v2 (`/racing/{raceId}/race`) returns finishing results,
not the base64 per-checkpoint times. So this skill needs an authenticated
torn.com tab, same session used for all telemetry pulls.

**Always use claude-in-chrome for this**, not the in-app/sandboxed browser —
the sandboxed browser has no saved torn.com login and will hit the login wall
every time, whereas claude-in-chrome reuses the user's real, already-logged-in
Chrome session.

Load the tools once per session if deferred:

```
ToolSearch("select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__tabs_create_mcp")
```

### Step 1 — fetch the full field (claude-in-chrome `javascript_tool`)

1. `tabs_context_mcp{createIfEmpty:true}` to get a tab, `navigate` it to
   `https://www.torn.com` if not already there.
2. Verify login before fetching — an unauthenticated tab won't error cleanly,
   it just returns garbage. Check `document.cookie.includes('rfc_v')` is true.
3. Run the fetch below **as top-level code, not wrapped in an `(async () =>
   {...})()` IIFE**. The IIFE form reliably comes back as `{}` from this
   tool — the return value doesn't survive serialization. Top-level
   `await` works and returns the real result.

```javascript
const RACEID = 19847555;                          // <-- the raceID
const gc = n => (document.cookie.match(new RegExp('(?:^|; )'+n+'=([^;]*)'))||[])[1];
const j = await (await fetch('/page.php?rfcv='+gc('rfc_v')+'&sid=racingData&raceID='+RACEID,
                  {headers:{'X-Requested-With':'XMLHttpRequest'}})).json();
let result;
if (+j.raceID !== RACEID) {
  result = 'EXPIRED: endpoint returned race '+j.raceID+' (raceID is past Torn\'s ~6-month telemetry retention)';
} else {
  const rd = j.raceData, iv = rd.trackData.intervals;
  const field = {
    raceID: +j.raceID, me: j.user.playername, trackID: j.trackID,
    // meCarName: the requester's own custom car name (Torn hides this for
    // opponents, along with everything else in j.carData) -- lets the header
    // read "WillieMcCoy driving <name> (<type>)" to match the opponent legend
    // format instead of just the type.
    meCarName: (j.carData && j.carData['0'] && j.carData['0'].carName) || null,
    meta: { laps: j.laps, perLap: iv.length, intervals: iv },
    drivers: Object.keys(rd.cars).map(name => ({
      name,
      carTitle: (rd.carInfo[name]||{}).carTitle || null,   // opponents: car TYPE only; Torn hides their stats
      parts: atob(rd.cars[name]).split(',').map(Number)
    }))
  };
  // Track geometry for the map panel: the racing page embeds the track as an
  // inline svg (#Layer_1) and Torn's own player animates cars along its single
  // <path> via getPointAt(completion * length) — so distance along this path
  // is the same coordinate system as the intervals array. Only present when
  // the tab is showing this race's page; cached per-track in
  // data/track_paths.json, so it's only needed once per track.
  const svgEl = document.getElementById('Layer_1');
  const pEl = svgEl && svgEl.querySelector('path');
  if (pEl) field.track = { viewBox: svgEl.getAttribute('viewBox'), d: pEl.getAttribute('d') };
  window.__field = field;
  result = 'OK drivers='+field.drivers.length+' me='+field.me+' laps='+field.meta.laps
         +' trackID='+field.trackID+' track='+(field.track?'yes':'NO (map panel needs it unless cached)');
}
result;
```

If the result says `track=NO` and `data/track_paths.json` has no entry for this
trackID, navigate the tab to
`https://www.torn.com/page.php?sid=racing&tab=log&raceID=<raceID>` first so the
page renders that race's track svg, then re-run the snippet.

Then, in a separate call, download it from `window.__field`:

```javascript
const blob = new Blob([JSON.stringify(window.__field)], {type:'application/json'});
const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
a.download = 'field_'+window.__field.raceID+'.json'; document.body.appendChild(a); a.click(); a.remove();
'triggered download';
```

Then move it out of Downloads:

```bash
mv ~/Downloads/field_<raceID>.json /tmp/field_<raceID>.json
```

### Step 2 — render

```bash
.agents/skills/fast-band-delta/render_fastband_delta.sh /tmp/field_<raceID>.json
open generated/fastband_<raceID>.html
```

The wrapper `cd`s to repo root so `generated/` resolves there. It prints a text
summary (each opponent's per-lap gap) and writes one standalone HTML file
(Chart.js via CDN — open it in a browser, not as a sandboxed artifact).

## Gotchas

- **Reference driver** = `j.user.playername`, i.e. whoever's session the tab
  belongs to (WillieMcCoy). Only meaningful for races that driver actually ran —
  their telemetry must be in the field. If it isn't, the script errors.
- **Retention** ≈ 6 months. An expired raceID makes the endpoint silently return
  the user's *latest* race; the snippet guards against this by checking the echoed
  `j.raceID` and bailing with `EXPIRED`.
- **Opponent stats are not available** — the payload exposes detailed carStats
  only for the requesting user. Opponents get `carTitle` (car type) and `parts`
  only. That's why this compares *where* they're faster (line shape), never builds.
- Single-race fast bands rest on ~5 laps/segment, so the bimodal split is thin;
  the trace is a strong per-race diagnostic but pool many races (see
  `data/*_telemetry.json` workflow) for population-level claims.
- **JS execution in claude-in-chrome**: don't wrap the fetch snippet in an
  IIFE — the tool returns `{}` for wrapped async functions even when the
  page-side logic runs correctly. Top-level `await` avoids this.

## Related

The whole method — bimodal coin, fast-band extraction, per-track surface/skill
characterization — is documented in the `torn-racing-telemetry` memory. Raw
per-track telemetry for all 16 tracks lives in `data/<track>_telemetry.json`.
