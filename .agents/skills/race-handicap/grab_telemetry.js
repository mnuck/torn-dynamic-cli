// Fetch racingData telemetry for queued races and save it as JSON downloads.
//
// Run in a logged-in torn.com tab (claude-in-chrome javascript_tool, on
// https://www.torn.com/page.php?sid=racing). Replace Q with telemetry_queue.py's output.
// It runs detached: poll window.__log / window.__done, then move the files from
// ~/Downloads into data/stock_e/.
//
// Why a download: page JS can't POST to localhost, tool output truncates at ~50 KB, and
// one 100-lap race can be several MB. Each file is capped at ~4 MB of lane data.
// racingData accepts any raceID (you needn't have raced), but an expired ID (~6 months)
// silently returns YOUR latest race instead -- hence the raceID echo check.
const Q = {/* "speedway": [20883138, ...], ... */};

window.__log = []; window.__done = 0; window.__total = Object.values(Q).reduce((a, v) => a + v.length, 0);
const rfc = document.cookie.match(/rfc_v=([^;]+)/)[1];
const tag = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');   // keeps new files from clobbering old ones
const save = (fname, races, bad) => {
  const blob = new Blob([JSON.stringify({fetched: Math.floor(Date.now() / 1000), races, bad})], {type: 'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = fname;
  document.body.appendChild(a); a.click(); a.remove();
  window.__log.push(`${fname} races=${races.length} bad=${JSON.stringify(bad)}`);
};
(async () => {
  for (const [track, ids] of Object.entries(Q)) {
    let buf = [], bad = [], bytes = 0, n = 1;
    const name = () => `racing_stock_e_${track}_${tag}_${String(n++).padStart(2, '0')}.json`;
    for (const id of ids) {
      try {
        const j = await fetch(`/page.php?rfcv=${rfc}&sid=racingData&raceID=${id}`,
                              {headers: {'X-Requested-With': 'XMLHttpRequest'}}).then(r => r.json());
        if (String(j.raceID) !== String(id)) bad.push([id, 'echoed ' + j.raceID]);
        else {
          const ci = {};
          for (const [nm, c] of Object.entries(j.raceData.carInfo || {}))
            ci[nm] = {userID: c.userID, itemID: c.imteID, car: c.carTitle};   // "imteID" is Torn's spelling
          buf.push({raceID: j.raceID, trackID: j.trackID, laps: j.laps, info: j.info, timeStarted: j.timeData.timeStarted,
                    title: j.raceData.title, intervals: j.raceData.trackData.intervals, carInfo: ci, cars: j.raceData.cars});
          bytes += Object.values(j.raceData.cars).reduce((a, s) => a + s.length, 0);
        }
      } catch (e) { bad.push([id, String(e)]); }
      window.__done++;
      if (bytes > 4e6) { save(name(), buf, bad); buf = []; bad = []; bytes = 0; }
      await new Promise(r => setTimeout(r, 700));
    }
    if (buf.length || bad.length) save(name(), buf, bad);
  }
  window.__log.push('ALL DONE');
})();
`started ${window.__total} races`;
