#!/usr/bin/env python3
"""Match stock Class E cars to drivers so everyone has about the same chance to win.

    race_handicap.sh [--track NAME|all] [--laps 25[,100...]] [--cars SPEC] [--faction] [DRIVER ...]

DRIVER is a faction member name, a user ID, or either with a manual skill: "Name=35".
Append "@Model" to pin a driver to a car they already own: "ladyME@Trident".
--cars limits the models on offer, optionally with counts: "Vita Bravo:2,Trident,Papani".
--faction adds every current faction member (explicit DRIVER entries still override, e.g. pins).
With no --track (or --track all) every track is ranked by how fair it can be made.

How it works (all fitted from real stock Class E races, see SKILL.md and track_model.json):
  * A driver's coin-free pace on a track = car offset[model] + b * ln(skill + 1). Stock
    builds are identical per model, and the fit leaves ~0.02% unexplained on every track.
  * Luck is Torn's two hidden coins, simulated with the constants in
    fast-band-delta/torn_race_model.py. Every car flips its own coins, so drivers with
    equal pace have exactly equal chances; the matcher therefore minimises the spread of
    pace across the field, and the simulation turns that spread into win chances.
"""
import argparse
import json
import math
import os
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'fast-band-delta'))
from torn_race_model import BIG_SLOW, LONG, P_SHORT, SHORT, SMALL_LOSS   # noqa: E402

MODEL = json.load(open(os.path.join(HERE, 'track_model.json')))
API = 'https://api.torn.com/v2'


# ---------------------------------------------------------------- inputs

def api_key():
    key = os.environ.get('TORN_API_KEY')
    if not key and os.path.exists('.env'):
        for line in open('.env'):
            if line.strip().startswith('TORN_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"\'')
    if not key:
        sys.exit('TORN_API_KEY not set (env or .env at repo root)')
    return key


_last_call = [0.0]


def api_get(path, key):
    wait = _last_call[0] + 0.4 - time.time()      # <=150/min; the code-5 backoff below covers the rest
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    # api.torn.com answers 403 to urllib's default User-Agent
    req = urllib.request.Request(API + path, headers={'Authorization': f'ApiKey {key}',
                                                      'User-Agent': 'torn-race-handicap/1.0'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 3:        # Torn's gateway throws the odd 502/504
                raise
            time.sleep(2 ** attempt); continue
        except urllib.error.URLError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt); continue
        if d.get('error', {}).get('code') == 5 and attempt < 3:   # rate limited on a shared key
            time.sleep(20); continue
        if 'error' in d:
            sys.exit(f"Torn API error on {path}: {d['error']}")
        return d


def fold(text):
    """Lower-case and strip accents, so 'stalhog' finds 'Stålhög 860'."""
    return ''.join(ch for ch in unicodedata.normalize('NFKD', text.replace('å', 'a').replace('Å', 'A'))
                   if not unicodedata.combining(ch)).lower().strip()


def match_model(text):
    """Prefix match on a model's full name or any word of it ('saxon', 'locale', 'papani')."""
    t = fold(text)
    hits = [c for c in MODEL['cars'] if any(w.startswith(t) for w in [fold(c), *fold(c).split()])]
    if len(hits) != 1:
        sys.exit(f'car {text!r} matches {hits or "no model"}; models: {", ".join(MODEL["cars"])}')
    return hits[0]


def parse_drivers(tokens):
    """-> list of dict(name, uid, skill, pin). Resolves names/skills via the API only when needed."""
    drivers, key, members = [], None, None
    for n, tok in enumerate(tokens, 1):
        if len(tokens) > 15 and n % 20 == 0:
            print(f'  looked up {n}/{len(tokens)} drivers', file=sys.stderr)
        tok, _, pin = tok.partition('@')
        ident, _, skill = tok.partition('=')
        d = {'name': ident, 'uid': int(ident) if ident.isdigit() else None,
             'skill': float(skill) if skill else None, 'pin': match_model(pin) if pin else None}
        if d['skill'] is None or d['uid'] is not None:
            key = key or api_key()
            if d['uid'] is None:
                if members is None:
                    members = {m['name'].lower(): m['id'] for m in api_get('/faction/members', key)['members']}
                if ident.lower() not in members:
                    sys.exit(f'{ident!r} is not in your faction; give their user ID or a skill ("{ident}=35")')
                d['uid'] = members[ident.lower()]
            else:
                d['name'] = api_get(f"/user/{d['uid']}/basic", key)['profile']['name']
            if d['skill'] is None:
                racing = api_get(f"/user/{d['uid']}/personalstats?cat=racing", key)['personalstats']['racing']
                d['skill'] = float(racing.get('skill') or 0)
        drivers.append(d)
    return drivers


def parse_cars(spec):
    """-> {model: count or None (unlimited)}"""
    if not spec:
        return {c: None for c in MODEL['cars']}
    caps = {}
    for part in spec.split(','):
        name, _, n = part.partition(':')
        caps[match_model(name)] = int(n) if n else None
    return caps


# ---------------------------------------------------------------- pace model

def car_offsets(track):
    """Measured offsets, plus the stat-formula estimate for any model never seen on this track."""
    t = MODEL['tracks'][track]
    return {**t['car_pct_estimated'], **t['car_pct']}


def pace(track, car, skill):
    """100*ln(coin-free lap) relative to the track's best model at skill 0. Lower = faster."""
    return car_offsets(track)[car] + MODEL['tracks'][track]['b'] * math.log(skill + 1)


def twins(car):
    """Models with identical stats run identically (measured to within 0.03%)."""
    return [c for c, s in MODEL['cars'].items() if s == MODEL['cars'][car] and c != car]


# ---------------------------------------------------------------- matching

def feasible(options, caps, lo, hi):
    """Bipartite matching: can every driver get a car whose pace lies in [lo, hi]?"""
    n = len(options)
    slots = {c: (n if cap is None else cap) for c, cap in caps.items()}
    owner = {c: [] for c in caps}               # drivers currently holding a slot of model c

    def augment(i, seen):
        for p, c in options[i]:
            if not lo - 1e-9 <= p <= hi + 1e-9 or c in seen:
                continue
            seen.add(c)
            if len(owner[c]) < slots[c]:
                owner[c].append(i); return True
            for j in list(owner[c]):
                if augment(j, seen):
                    owner[c].remove(j); owner[c].append(i); return True
        return False

    if not all(augment(i, set()) for i in range(n)):
        return None
    return {i: c for c, holders in owner.items() for i in holders}


def assign(track, drivers, caps):
    """Assignment minimising the pace spread (max - min) across the field, then its variance."""
    offs = car_offsets(track)
    options = []
    for d in drivers:
        cars = [d['pin']] if d['pin'] else [c for c in caps if c in offs]
        options.append([(pace(track, c, d['skill']), c) for c in cars])
    vals = sorted({p for o in options for p, _ in o})
    best = None
    for i, lo in enumerate(vals):
        if not feasible(options, caps, lo, vals[-1]):
            break                                 # raising lo only removes options
        a, b = i, len(vals) - 1
        while a < b:
            mid = (a + b) // 2
            if feasible(options, caps, lo, vals[mid]):
                b = mid
            else:
                a = mid + 1
        if best is None or vals[a] - lo < best[1] - best[0] - 1e-9:
            best = (lo, vals[a])
    if best is None:
        sys.exit('no assignment possible -- check --cars counts against the number of drivers')
    lo, hi = best
    pick = feasible(options, caps, lo, hi)
    # Within the window, pull everyone toward the field mean (respecting counts).
    for _ in range(10):
        used = {c: list(pick.values()).count(c) for c in caps}
        mean = sum(pace(track, pick[i], d['skill']) for i, d in enumerate(drivers)) / len(drivers)
        changed = False
        for i, d in enumerate(drivers):
            cur = pick[i]
            for p, c in sorted(options[i], key=lambda pc: abs(pc[0] - mean)):
                if not lo - 1e-9 <= p <= hi + 1e-9:
                    continue
                if c == cur:
                    break
                if caps[c] is None or used[c] < caps[c]:
                    used[cur] -= 1; used[c] += 1; pick[i] = c; changed = True
                    break
        if not changed:
            break
    return [pick[i] for i in range(len(drivers))]


# ---------------------------------------------------------------- luck

_pools = {}


def luck_pool(track, laps, n=6000, seed=1):
    """Race time / coin-free race time for n simulated races of one car.

    Same process as torn_race_model.simulate(), vectorised: the big coin starts in a random
    band with a fresh dwell, strictly alternates, and carries across lap lines; the small
    coin is a fresh flip every segment and subtracts a fixed share of base speed.
    """
    if (track, laps) in _pools:
        return _pools[(track, laps)]
    rng = np.random.default_rng(seed)
    shares = np.array(MODEL['tracks'][track]['seg_shares'])
    N = laps * len(shares)
    w = np.tile(shares, laps) / laps
    K = N // LONG[0] + 30                         # enough dwells to cover the race
    g = np.array([[1.0, 1 / (1 - SMALL_LOSS)], [1 / BIG_SLOW, 1 / (BIG_SLOW - SMALL_LOSS)]])
    out = np.empty(n)
    for s in range(0, n, 128):
        m = min(128, n - s)
        short = rng.random((m, K)) < P_SHORT
        dwell = np.where(short, rng.integers(SHORT[0], SHORT[1] + 1, (m, K)),
                         rng.integers(LONG[0], LONG[1] + 1, (m, K)))
        ends = np.cumsum(dwell, axis=1)
        assert (ends[:, -1] >= N).all()
        big = N + LONG[1] * K + 1                 # row offset keeps the flattened search sorted
        rows = np.arange(m)[:, None] * big
        idx = np.searchsorted((ends + rows).ravel(), (np.arange(N)[None, :] + rows).ravel(), side='right')
        idx = idx.reshape(m, N) - np.arange(m)[:, None] * K
        slow = (idx + (rng.random((m, 1)) < 0.5)) % 2        # random starting band
        small = (rng.random((m, N)) < 0.5).astype(int)
        out[s:s + m] = (g[slow, small] * w).sum(axis=1)
    _pools[(track, laps)] = out
    return out


def win_chances(track, laps, paces, trials=None, seed=2):
    trials = trials or max(20000, 1500 * len(paces))
    rng = np.random.default_rng(seed)
    pool = luck_pool(track, laps)
    t = np.exp(np.array(paces) / 100)[None, :] * pool[rng.integers(0, len(pool), (trials, len(paces)))]
    return np.bincount(t.argmin(axis=1), minlength=len(paces)) / trials


# ---------------------------------------------------------------- report

def resolve_track(text):
    t = text.lower().replace(' ', '')
    hits = [k for k in MODEL['tracks'] if k.startswith(t)]
    if len(hits) != 1:
        sys.exit(f'track {text!r} matches {hits or "nothing"}; tracks: {", ".join(MODEL["tracks"])}')
    return hits[0]


def fastest_model(track, caps):
    offs = car_offsets(track)
    return min((c for c in caps if c in offs), key=offs.get)


def track_detail(track, drivers, caps, laps_list):
    t = MODEL['tracks'][track]
    cars = assign(track, drivers, caps)
    paces = [pace(track, c, d['skill']) for c, d in zip(cars, drivers)]
    mean = sum(paces) / len(paces)
    n = len(drivers)
    gain = -t['b'] * (math.log(71) - math.log(2))
    print(f"{t['name']} — {n} drivers — model from {t['races']} stock Class E races "
          f"({t['dates'][0]}..{t['dates'][1]}); skill 1→70 is worth {gain:.2f}% here")
    print(f"\nRecommended cars (pace spread {max(paces) - min(paces):.2f}% after skill; fair share {100 / n:.1f}%)")
    wins = {L: win_chances(track, L, paces) for L in laps_list}
    head = '  '.join(f'win@{L}' for L in laps_list)
    print(f"  {'driver':16} {'skill':>5}  {'car':34} {'pace*':>7}  {head}")
    order = range(n) if n <= 15 else sorted(range(n), key=lambda i: -drivers[i]['skill'])
    for i in order:
        d, c = drivers[i], cars[i]
        alt = twins(c)
        label = c + (f' (or {", ".join(alt)})' if alt and not d['pin'] else '') + (' [pinned]' if d['pin'] else '')
        est = '~' if c in t['car_pct_estimated'] else ' '
        cells = '  '.join(f"{100 * wins[L][i]:{len(f'win@{L}')}.1f}" for L in laps_list)
        print(f"  {d['name']:16} {d['skill']:5.0f}  {label:34} {paces[i] - mean:+6.2f}%{est} {cells}")
    print("  * coin-free pace vs the field average; + is slower. ~ = model never seen on this track (stat-formula estimate)")
    if n > 8:
        # The announcement view: who brings what. Identical-stat models are one group.
        groups = {}
        for d, c in zip(drivers, cars):
            key = c if d['pin'] else ' / '.join(sorted([c, *twins(c)]))
            groups.setdefault(key, []).append(d)
        print('\nBy car:')
        for key, ds in sorted(groups.items(), key=lambda kv: min(d['skill'] for d in kv[1])):
            sk = [d['skill'] for d in ds]
            print(f"  {key} — {len(ds)} driver{'s' * (len(ds) > 1)}, skill {min(sk):.0f}–{max(sk):.0f}: "
                  + ', '.join(d['name'] for d in sorted(ds, key=lambda d: d['name'].lower())))
    same = fastest_model(track, caps)
    sp = [pace(track, same, d['skill']) for d in drivers]
    print(f"\nFor comparison, everyone in {same} (the track's fastest model):")
    for L in laps_list:
        w = win_chances(track, L, sp)
        print(f"  {L:3} laps: win chances {100 * w.min():.1f}%–{100 * w.max():.1f}%   "
              f"(recommended cars: {100 * wins[L].min():.1f}%–{100 * wins[L].max():.1f}%)")


def scan(drivers, caps, laps):
    rows = []
    for track, t in MODEL['tracks'].items():
        cars = assign(track, drivers, caps)
        paces = [pace(track, c, d['skill']) for c, d in zip(cars, drivers)]
        w = win_chances(track, laps, paces)
        same = fastest_model(track, caps)
        ws = win_chances(track, laps, [pace(track, same, d['skill']) for d in drivers])
        rows.append((w.max() - w.min(), t['name'], max(paces) - min(paces), w, ws, track))
    rows.sort()
    n = len(drivers)
    print(f"Every track, {laps} laps, {n} drivers (fair share {100 / n:.1f}% each), best car assignment per track:\n")
    print(f"  {'track':12} {'pace spread':>11} {'win chances':>15}   {'all in fastest model':>20}")
    for gap, name, spread, w, ws, _ in rows:
        print(f"  {name:12} {spread:10.2f}% {100 * w.min():6.1f}%–{100 * w.max():5.1f}%   "
              f"{100 * ws.min():9.1f}%–{100 * ws.max():5.1f}%")
    print()
    return rows[0][5]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('drivers', nargs='*', help='name | userID, optionally =skill and @Model')
    ap.add_argument('--faction', action='store_true', help='add every current faction member as a driver')
    ap.add_argument('--track', default='all', help='track name, or "all" to rank every track (default)')
    ap.add_argument('--laps', default='25', help='race length; comma list compares several (default 25)')
    ap.add_argument('--cars', help='models on offer, e.g. "Vita Bravo:2,Trident" (default: all, unlimited)')
    a = ap.parse_args()
    laps_list = [int(x) for x in a.laps.split(',')]
    tokens = list(a.drivers)
    if a.faction:
        listed = {t.partition('@')[0].partition('=')[0].lower() for t in tokens}
        tokens += [m['name'] for m in api_get('/faction/members', api_key())['members']
                   if m['name'].lower() not in listed]
    if not tokens:
        ap.error('give at least one driver, or --faction')
    if len(tokens) > 15:
        print(f'looking up {len(tokens)} drivers...', file=sys.stderr)
    drivers = parse_drivers(tokens)
    caps = parse_cars(a.cars)
    if a.track == 'all':
        best = scan(drivers, caps, laps_list[0])
        print('Fairest track in detail:\n')
        track_detail(best, drivers, caps, laps_list)
    else:
        track_detail(resolve_track(a.track), drivers, caps, laps_list)


if __name__ == '__main__':
    main()
