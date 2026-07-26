#!/usr/bin/env python3
"""Generative model of Torn's racing engine — the two-coin segment simulator.

This is the counterpart to fastband_delta.py. That script REMOVES the luck from
a race to expose capability; this one PUTS THE LUCK BACK, so you can ask what a
given car is statistically capable of: "what fraction of laps beat my record",
"is this WR reachable at all", "how many laps until a new PR".

The engine, reverse-engineered from 100-lap races (the only ones with enough
samples per segment to resolve it — see SKILL.md):

Every segment's time is set by exactly two independent fair coins, so each
segment has exactly FOUR possible times, not two. Sorted t0<t1<t2<t3:

    t0  both fast          t1  small coin slow      (t1/t0 ~ 1.018)
    t2  big coin slow      t3  both slow            (t2/t0 ~ 1.219)

  BIG coin   — the band. Strictly ALTERNATES fast/slow (a flip never re-rolls
               the same band, which is why dwells are a clean flat 20-50 and
               not a geometric smear). Persists ACROSS the lap line: nothing
               resets at the start/finish straight. On a track with more
               checkpoints per lap than the 50-segment max dwell (every track
               except Speedway's 23), an all-fast lap is therefore impossible
               through the normal rule -- which is what makes the 1% short
               dwell below the entire record mechanism.

  SMALL coin — a fresh fair flip on EVERY segment, no persistence at all.
               It SUBTRACTS A FIXED SPEED rather than scaling it; a multiplier
               model is rejected by the data. Same absolute loss in both bands
               over a smaller denominator is exactly why the split reads
               x1.018 in the fast band but x1.022 in the slow one.

Invariant across 2 tracks / 3 cars / 6 months. Only `base_speed` carries the
car: build, racing skill and track geometry set the ceiling, the coins do the
rest. Usage:

    python3 torn_race_model.py <field.json> [--races 400]
"""
import argparse
import json
import random
import sys
from statistics import mean, pstdev

# Engine constants. Measured 0.82019 +/- 0.00087 and 0.01797 +/- 0.00024 — both
# within noise of a round 0.82 / 0.018, which is very likely what Torn actually
# ships. The big-coin ratio implied here is 1/0.82019 = 1.2192; the 1.222 quoted
# in earlier work was fast-band-center / slow-band-center, and each of those
# centers silently averages over the small coin, so it lands between the true
# 1.2194 (t2/t0) and 1.2247 (t3/t1).
BIG_SLOW = 0.82019     # speed multiplier while the big coin sits in the slow band
SMALL_LOSS = 0.01797   # speed subtracted, as a fraction of base, when small lands slow

# The big-coin dwell is a two-component mixture with a hard gap: over 23,084 runs
# from 99 drivers there are ZERO runs of length 1, and ZERO of length 6-19.
P_SHORT = 240 / 23084  # 1.04%
SHORT = (2, 5)
LONG = (20, 50)


def big_dwell(rng):
    """Segments the big coin stays in its current band before flipping."""
    lo, hi = SHORT if rng.random() < P_SHORT else LONG
    return rng.randint(lo, hi)


def simulate(base_speed, intervals, laps, rng):
    """Per-segment times for one car over `laps` laps.

    base_speed[s] is the car's both-coins-fast speed on segment s: the ceiling
    it never actually reaches, since the big coin cannot stay fast for a whole
    lap on any real track.
    """
    P = len(base_speed)
    big_fast = rng.random() < 0.5
    left = big_dwell(rng)
    times = []
    for i in range(laps * P):
        s = i % P                      # the coins do NOT reset at the lap line
        if left == 0:
            big_fast = not big_fast    # bands strictly alternate; never repeat
            left = big_dwell(rng)
        left -= 1

        v = base_speed[s] * (1.0 if big_fast else BIG_SLOW)
        if rng.random() < 0.5:                     # fresh flip every segment
            v -= base_speed[s] * SMALL_LOSS        # fixed speed loss, NOT a ratio

        times.append(round(intervals[s] / v, 3))   # Torn stores ms precision
    return times


def base_speed_from(parts, intervals, perLap, laps):
    """Recover base_speed[s] from real telemetry.

    Both coins land fast with p=0.25, so the MINIMUM segment time over N pooled
    flying laps IS t0 once N is comfortably large -- exact from N>=16 (P(miss) =
    0.75^N), no clustering needed. Lap 0 is excluded: the standing start makes
    its early segments meaningless.
    """
    if laps < 17:
        print(f"warning: {laps - 1} flying laps — t0 needs >=16 to be unbiased; "
              f"pool more races of this car on this track", file=sys.stderr)
    t0 = [min(parts[l * perLap + s] for l in range(1, laps)) for s in range(perLap)]
    return [intervals[s] / t0[s] for s in range(perLap)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('field', help='field_<raceID>.json (see SKILL.md fetch snippet)')
    ap.add_argument('--races', type=int, default=400, help='simulated races (default 400)')
    ap.add_argument('--driver', help='reference driver (default: field["me"])')
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()

    F = json.load(open(a.field))
    P, L, iv = F['meta']['perLap'], F['meta']['laps'], F['meta']['intervals']
    name = a.driver or F['me']
    d = next((x for x in F['drivers'] if x['name'] == name), None)
    if d is None or len(d['parts']) != L * P:
        sys.exit(f"driver {name!r} missing or has partial telemetry")

    base = base_speed_from(d['parts'], iv, P, L)
    laps_of = lambda parts: [sum(parts[l * P + s] for s in range(P)) for l in range(1, L)]
    real = laps_of(d['parts'])

    rng = random.Random(a.seed)
    sims, bests = [], []
    for _ in range(a.races):
        lt = laps_of(simulate(base, iv, L, rng))
        sims += lt
        bests.append(min(lt))

    rec = min(real)
    print(f"{name} — race {F.get('raceID')}, track {F.get('trackID')}, {L} laps x {P} checkpoints")
    print(f"perfect lap (both coins fast every segment — unreachable): {sum(iv[s]/base[s] for s in range(P)):.3f}s\n")
    print(f"{'':16} {'mean':>8} {'sd':>6} {'min':>8} {'p5':>7} {'max':>8}")
    print(f"  real  ({len(real):5d}) {mean(real):8.2f} {pstdev(real):6.2f} {min(real):8.2f} "
          f"{sorted(real)[len(real)//20]:7.2f} {max(real):8.2f}")
    print(f"  model ({len(sims):5d}) {mean(sims):8.2f} {pstdev(sims):6.2f} {min(sims):8.2f} "
          f"{sorted(sims)[len(sims)//20]:7.2f} {max(sims):8.2f}")
    beat = sum(1 for b in bests if b < rec)
    print(f"\nbest lap of this race: {rec:.2f}s")
    print(f"over {a.races} simulated races of the same length: best-lap mean {mean(bests):.2f}s, "
          f"outright best {min(bests):.2f}s")
    print(f"races whose best lap beats {rec:.2f}s: {beat}/{a.races} = {100*beat/a.races:.1f}%")


if __name__ == '__main__':
    main()
