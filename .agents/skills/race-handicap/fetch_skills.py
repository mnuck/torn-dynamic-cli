#!/usr/bin/env python3
"""Snapshot the racing skill of every driver in data/stock_e telemetry.

Skill only exists as a current value, so each snapshot is dated and build_model.py
uses the one closest to each race. A driver gets a new snapshot when they appear in a
race more than STALE_DAYS after their latest one; run this right after fetching
telemetry, while the races are still fresh. Resumable; saves every 25.
Run from repo root with TORN_API_KEY in env or .env.
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import RAW_GLOB, SKILLS, snapshots   # noqa: E402
from race_handicap import api_get, api_key            # noqa: E402

STALE_DAYS = 3

key = api_key()
store = json.load(open(SKILLS)) if os.path.exists(SKILLS) else {'skills': {}}
last_race = {}
for f in glob.glob(RAW_GLOB):
    for r in json.load(open(f))['races']:
        for c in r['carInfo'].values():
            u = str(c['userID'])
            last_race[u] = max(last_race.get(u, 0), r['timeStarted'])
need = [u for u, t in sorted(last_race.items())
        if not snapshots(store['skills'].get(u))
        or t - max(s['fetched'] for s in snapshots(store['skills'][u])) > STALE_DAYS * 86400]
print(f'{len(last_race)} drivers in telemetry, {len(need)} need a skill snapshot', file=sys.stderr)
for n, uid in enumerate(need, 1):
    rs = api_get(f'/user/{uid}/personalstats?cat=racing', key)['personalstats']['racing']
    snap = {'skill': rs.get('skill'), 'points': rs.get('points'),
            'entered': rs.get('races', {}).get('entered'), 'fetched': int(time.time())}
    store['skills'][uid] = snapshots(store['skills'].get(uid)) + [snap]
    if n % 25 == 0:
        json.dump(store, open(SKILLS, 'w'))
        print(f'  {n}/{len(need)}', file=sys.stderr)
    time.sleep(0.6)                                   # ~60 req/min on a shared 100/min key
json.dump(store, open(SKILLS, 'w'))
print(f'done; {len(store["skills"])} drivers with skill', file=sys.stderr)
