#!/usr/bin/env python3
"""Add the last week's finished stock-only custom races to data/stock_races_index.json.

/racing/races only reaches back ~7 days (asking for older `to=` returns one stray race
from Dec 2025), so run this at least weekly; entries accumulate across runs.
Run from repo root with TORN_API_KEY in env or .env.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from race_handicap import api_get, api_key   # noqa: E402

OUT = 'data/stock_races_index.json'
DAYS = 8

key = api_key()
index = {r['id']: r for r in json.load(open(OUT))} if os.path.exists(OUT) else {}
before = len(index)
cutoff, to, pages = int(time.time()) - DAYS * 86400, int(time.time()), 0
while True:
    races = api_get(f'/racing/races?cat=custom&limit=100&sort=DESC&to={to}', key).get('races', [])
    pages += 1
    if not races:
        break
    for r in races:
        if r['status'] == 'finished' and r['requirements']['requires_stock_car']:
            index[r['id']] = r
    oldest = min(r['schedule']['start'] or r['schedule']['join_from'] for r in races)
    if oldest < cutoff:
        break
    to = oldest - 1 if oldest < to else to - 60       # always make progress
    if pages % 25 == 0:
        print(f'  {pages} pages, back to {time.strftime("%Y-%m-%d %H:%M", time.gmtime(oldest))}', file=sys.stderr)
    time.sleep(0.8)                                   # ~60 req/min on a shared 100/min key
json.dump(sorted(index.values(), key=lambda r: r['id']), open(OUT, 'w'))
print(f'{pages} pages scanned; index {before} -> {len(index)} stock races ({OUT})')
