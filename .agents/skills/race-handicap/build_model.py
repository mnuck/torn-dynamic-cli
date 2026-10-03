#!/usr/bin/env python3
"""Fit the stock Class E race model from telemetry and write track_model.json.

Inputs (gitignored, see data/README.md):
  data/stock_e/racing_stock_e_<track>_batchNN.json   raw racingData lanes + carInfo
  data/stock_e_results.json                           {"skills": {userID: [dated snapshots]}}

Per track the model is

    100 * ln(perfect_lap) = car[model] + b * ln(skill + 1)

where perfect_lap is the coin-free lap (per-segment minimum over >=16 flying laps).
Stock builds are identical within a model, so this separates car from skill cleanly:
on every track the per-driver residual is ~0.02%, i.e. timing quantisation.

Only aggregates are written (car offsets, the skill slope, segment time shares), so
the output is safe to commit to a public repo; the raw lanes stay in data/.

Run from repo root:  python3 .agents/skills/race-handicap/build_model.py
"""
import base64
import collections
import glob
import json
import math
import os
import statistics
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_GLOB = 'data/stock_e/racing_stock_e_*.json'
SKILLS = 'data/stock_e_results.json'
OUT = os.path.join(HERE, 'track_model.json')
MIN_LAPS = 17          # t0-by-minimum needs >=16 flying laps: P(miss) = 0.75^16 ~ 1%

TRACKS = {6: 'Uptown', 7: 'Withdrawal', 8: 'Underdog', 9: 'Parkland', 10: 'Docks', 11: 'Commerce',
          12: 'Two Islands', 15: 'Industrial', 16: 'Vector', 17: 'Mudpit', 18: 'Hammerhead',
          19: 'Sewage', 20: 'Meltdown', 21: 'Speedway', 23: 'Stone Park', 24: 'Convict'}

# Class E base stats (top, acc, brk, hnd) from `torn racing cars`. Every Class E car has
# 40 points across these four and identical grip, so no model is better overall.
CARS = {'Edomondo Localé': (15, 10, 10, 5), 'Trident': (10, 10, 5, 15), 'Limoen Saxon': (5, 15, 10, 10),
        'Nano Pioneer': (10, 10, 5, 15), 'Vita Bravo': (5, 10, 10, 15), 'Zaibatsu Macro': (10, 10, 15, 5),
        'Çagoutte 10-6': (10, 15, 5, 10), 'Papani Colé': (15, 5, 10, 10), 'Bedford Racer': (5, 10, 15, 10),
        'Stålhög 860': (15, 5, 10, 10)}


def slug(name):
    return name.lower().replace(' ', '')


def snapshots(entry):
    """A driver's dated skill snapshots. (The first collection stored one dict, not a list.)"""
    if not entry:
        return []
    return entry if isinstance(entry, list) else [entry]


def skill_at(store, uid, when):
    """Skill from the snapshot fetched closest to `when` -- skill only exists as a current value."""
    snaps = [s for s in snapshots(store.get(str(uid))) if s.get('skill') is not None]
    return min(snaps, key=lambda s: abs(s['fetched'] - when))['skill'] if snaps else None


def load_lanes(store):
    """One record per (race, driver): model, skill at race time, per-segment coin-free times."""
    by_track = collections.defaultdict(list)
    seen = set()
    for path in sorted(glob.glob(RAW_GLOB)):
        for race in json.load(open(path))['races']:
            if race['raceID'] in seen:
                continue
            seen.add(race['raceID'])
            iv = [float(x) for x in race['intervals']]
            P, L = len(iv), int(race['laps'])
            if L < MIN_LAPS:
                continue
            for name, lane in race['cars'].items():
                info = race['carInfo'][name]
                skill = skill_at(store, info['userID'], race['timeStarted'])
                parts = [float(x) for x in base64.b64decode(lane).decode().split(',')]
                if len(parts) != L * P or info['car'] not in CARS or skill is None:
                    continue      # crashed/partial lane, non-Class-E car, or unknown skill
                t0 = [min(parts[l * P + s] for l in range(1, L)) for s in range(P)]   # lap 0 = standing start
                by_track[int(race['trackID'])].append(dict(
                    race=race['raceID'], started=race['timeStarted'], uid=info['userID'], car=info['car'],
                    skill=skill, t0=t0, perfect=sum(t0), intervals=iv))
    return by_track


def fit_track(lanes):
    cars = sorted({x['car'] for x in lanes})
    y = np.array([100 * math.log(x['perfect']) for x in lanes])
    X = np.zeros((len(lanes), len(cars) + 1))
    for i, x in enumerate(lanes):
        X[i, cars.index(x['car'])] = 1
        X[i, -1] = math.log(x['skill'] + 1)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ coef
    eff = dict(zip(cars, coef[:-1]))
    base = min(eff.values())
    car_pct = {c: eff[c] - base for c in cars}

    # Unseen models: linear in stat points (top is implied, since all sum to 40). Only a
    # fallback -- measured offsets beat it by 0.2-0.3%, which is a whole fairness margin.
    estimated = {}
    missing = [c for c in CARS if c not in car_pct]
    if missing and len(cars) >= 5:
        A = np.array([[1, *CARS[c][1:]] for c in cars])
        w, *_ = np.linalg.lstsq(A, np.array([car_pct[c] for c in cars]), rcond=None)
        for c in missing:
            estimated[c] = float(np.array([1, *CARS[c][1:]]) @ w)

    groups = collections.defaultdict(list)
    for x, r in zip(lanes, res):
        groups[x['race']].append(r)
    multi = [statistics.mean(v) for v in groups.values() if len(v) >= 3]

    # Share of the coin-free lap spent on each segment. Luck is applied per segment, so the
    # simulator needs these weights -- not the absolute speeds.
    shares = np.median([np.array(x['t0']) / x['perfect'] for x in lanes], axis=0)
    shares = shares / shares.sum()

    skills = [x['skill'] for x in lanes]
    return dict(
        car_pct={c: round(float(v), 4) for c, v in car_pct.items()},
        car_pct_estimated={c: round(v, 4) for c, v in estimated.items()},
        car_n=dict(collections.Counter(x['car'] for x in lanes)),
        b=round(float(coef[-1]), 5),
        base_log_lap=round(float(base), 5),          # 100*ln(perfect lap, s) for the best model at skill 0
        resid_sd_pct=round(float(np.std(res)), 4),
        race_sd_pct=round(float(np.std(multi)), 4) if len(multi) > 2 else None,
        seg_shares=[round(float(s), 6) for s in shares],
        races=len(groups), lanes=len(lanes), drivers=len({x['uid'] for x in lanes}),
        skill_range=[min(skills), max(skills)], lanes_skill_55_plus=sum(s >= 55 for s in skills),
        dates=[time.strftime('%Y-%m-%d', time.gmtime(min(x['started'] for x in lanes))),
               time.strftime('%Y-%m-%d', time.gmtime(max(x['started'] for x in lanes)))])


def main():
    by_track = load_lanes(json.load(open(SKILLS))['skills'])
    model = {'built': time.strftime('%Y-%m-%d'), 'class': 'E', 'stock_only': True,
             'cars': {c: dict(zip(('top', 'acc', 'brk', 'hnd'), s)) for c, s in CARS.items()},
             'tracks': {}}
    print(f"{'track':11} {'races':>5} {'lanes':>5} {'skill 1->70':>11} {'resid':>7} {'car spread':>10}  estimated")
    for tid, name in sorted(TRACKS.items(), key=lambda kv: kv[1]):
        lanes = by_track.get(tid, [])
        if len(lanes) < 10:
            print(f'{name:11} only {len(lanes)} usable lanes -- skipped')
            continue
        t = fit_track(lanes)
        t.update(name=name, track_id=tid, cp_per_lap=len(lanes[0]['intervals']))
        model['tracks'][slug(name)] = t
        gain = -t['b'] * (math.log(71) - math.log(2))
        print(f"{name:11} {t['races']:5} {t['lanes']:5} {gain:10.2f}% {t['resid_sd_pct']:6.3f}% "
              f"{max(t['car_pct'].values()):9.2f}%  {', '.join(t['car_pct_estimated']) or '-'}")
    json.dump(model, open(OUT, 'w'), indent=1, ensure_ascii=False)
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
