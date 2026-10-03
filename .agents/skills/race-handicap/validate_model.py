#!/usr/bin/env python3
"""Check the handicap model against real results: are predicted win chances calibrated?

Fits pace on races started before a cutoff, then predicts every later race from its
drivers' models and skills alone (pace + simulated luck) and compares with who won.
Run from repo root after build_model.py:
    python3 .agents/skills/race-handicap/validate_model.py [--holdout-days 2]
"""
import argparse
import base64
import collections
import glob
import json
import math
import time

import numpy as np

import build_model as bm
import race_handicap as rh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--holdout-days', type=float, default=2.0, help='predict races from the last N days')
    a = ap.parse_args()

    skills = json.load(open(bm.SKILLS))['skills']
    races = {}
    for path in sorted(glob.glob(bm.RAW_GLOB)):
        for r in json.load(open(path))['races']:
            races[r['raceID']] = r
    cutoff = max(r['timeStarted'] for r in races.values()) - a.holdout_days * 86400

    # Fit on the older races only.
    by_track = bm.load_lanes(skills)
    fits = {}
    for tid, lanes in by_track.items():
        train = [x for x in lanes if x['started'] < cutoff]
        if len(train) >= 10 and len({x['car'] for x in train}) >= 2:
            fits[tid] = bm.fit_track(train)

    results, skipped = [], collections.Counter()      # per race: (predicted chances, winner index)
    for r in races.values():
        if r['timeStarted'] < cutoff:
            continue
        tid, laps = int(r['trackID']), int(r['laps'])
        if tid not in fits:
            skipped['track not fitted'] += 1; continue
        f = fits[tid]
        offs = {**f['car_pct_estimated'], **f['car_pct']}
        field = []
        for name, lane in r['cars'].items():
            info = r['carInfo'][name]
            skill = bm.skill_at(skills, info['userID'], r['timeStarted'])
            parts = [float(x) for x in base64.b64decode(lane).decode().split(',')]
            if len(parts) != laps * len(r['intervals']) or info['car'] not in offs or skill is None:
                field = None; break           # a driver we can't model could be the winner
            field.append((offs[info['car']] + f['b'] * math.log(skill + 1), sum(parts)))
        if not field or len(field) < 2:
            skipped['incomplete field'] += 1; continue
        p = rh.win_chances(bm.slug(bm.TRACKS[tid]), laps, [pc for pc, _ in field], trials=4000)
        results.append((p, min(range(len(field)), key=lambda i: field[i][1])))

    P = np.concatenate([p for p, _ in results])
    O = np.concatenate([np.arange(len(p)) == w for p, w in results]).astype(float)
    U = np.concatenate([np.full(len(p), 1 / len(p)) for p, _ in results])
    print(f'held out: races after {time.strftime("%Y-%m-%d %H:%M", time.gmtime(cutoff))} UTC -> '
          f'{len(results)} races, {len(P)} driver-races predicted; skipped {dict(skipped)}')
    print(f"\n{'predicted win chance':>20} {'drivers':>8} {'predicted':>10} {'actual':>8}")
    for lo, hi in ((0, .02), (.02, .1), (.1, .25), (.25, .45), (.45, .55), (.55, .75), (.75, .9), (.9, .98), (.98, 1.01)):
        m = (P >= lo) & (P < hi)
        if m.sum():
            print(f'{100 * lo:7.0f}% – {100 * min(hi, 1):4.0f}% {m.sum():8d} {100 * P[m].mean():9.1f}% {100 * O[m].mean():7.1f}%')
    ll = lambda q: -np.mean(O * np.log(np.clip(q, 1e-4, 1)) + (1 - O) * np.log(np.clip(1 - q, 1e-4, 1)))
    fav = [int(np.argmax(p) == w) for p, w in results]
    print(f'\nfavourite won {sum(fav)}/{len(fav)} races ({100 * np.mean(fav):.1f}%); '
          f'model expected {100 * np.mean([p.max() for p, _ in results]):.1f}%')
    print(f'log loss {ll(P):.4f} per driver-race vs {ll(U):.4f} for "everyone equally likely"')


if __name__ == '__main__':
    main()
