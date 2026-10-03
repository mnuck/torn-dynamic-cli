#!/usr/bin/env python3
"""Print the stock Class E races still missing telemetry, as the Q object grab_telemetry.js takes.

Only races of >= 17 laps are useful: the coin-free lap is a per-segment minimum over
flying laps and needs >= 16 of them. Run from repo root.
"""
import glob
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import MIN_LAPS, RAW_GLOB, TRACKS, slug   # noqa: E402

have = {r['raceID'] for f in glob.glob(RAW_GLOB) for r in json.load(open(f))['races']}
q = {}
for r in json.load(open('data/stock_races_index.json')):
    if (r['requirements']['car_class'] == 'E' and r['laps'] >= MIN_LAPS and r['id'] not in have
            and r['track_id'] in TRACKS):
        q.setdefault(slug(TRACKS[r['track_id']]), []).append(r['id'])
print(f'{sum(map(len, q.values()))} races to fetch: ' +
      ', '.join(f'{t} {len(v)}' for t, v in sorted(q.items())), file=sys.stderr)
print(json.dumps(q, separators=(',', ':')))
