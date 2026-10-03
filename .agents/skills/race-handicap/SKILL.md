---
name: race-handicap
description: >
  Match stock Class E cars to drivers so every driver in a race has about the same
  chance to win, and rank tracks by how fair they can be made. Use this skill when the
  user wants to set up a fair or handicapped race, asks which car each driver should
  bring, which track is fairest for a group, what each driver's win chances are with a
  given car lineup, or wants to refresh the race-handicap model from new races. Covers
  stock-only Class E custom races (the faction's event format); not upgraded cars or
  other classes.
---

# Race handicap

Run the tool, then relay its tables. Don't recompute pace or win chances by hand.

```bash
.agents/skills/race-handicap/race_handicap.sh [--track NAME|all] [--laps 25[,100]] [--cars SPEC] [--faction] [DRIVER...]
```

- **DRIVER** is a faction member name (resolved through `/faction/members`), a user ID,
  or either with a manual skill (`Guest=12`, which makes no API call). Append `@Model`
  to pin someone to a car they already own: `ladyME@Trident`.
- **`--faction`** adds every current member (one API call each, paced; ~40 s for 78).
  Explicit DRIVER entries still apply on top, e.g. pins or manual skills.
- **`--track`** defaults to `all`. That ranks every track by the fairest assignment
  possible for this roster, then details the best one. Names match on a prefix
  (`stone`, `two`).
- **`--laps`** takes a comma list to compare race lengths. The car assignment doesn't
  depend on length; only the win chances do.
- **`--cars`** limits the models on offer, optionally with counts:
  `"vita:1,bedford:1,trident,papani"`. Names match on any word, with or without
  accents (`saxon`, `locale`, `stalhog`). The default is all 10 models, unlimited.

## Reading the output

- **pace\*** is each driver's luck-free pace against the field average, in %.
  `+` is slower. `~` marks a model never seen on that track (stat-formula estimate).
- **win@N** is each driver's simulated chance to win an N-lap race. The fair share is
  100% ÷ drivers.
- **"(or X)"** means the two models have identical stats and run identically (measured
  within 0.03%). Either one works, so drivers can use whichever they own.
- **By car** (printed for more than 8 drivers) is the announcement view: who brings
  which model, with identical-stat models merged into one group. Big fields are sorted
  by skill.
- **The comparison block** shows the same drivers all in the track's fastest model. Use
  it to show how much the assignment helps.

When relaying results that name faction members, follow the tone rule in AGENTS.md.
State numbers plainly ("skill 5, so they get the faster car") and never label a
driver.

## How it works

Everything is fitted from real stock Class E races (`track_model.json` records how
many, and when).

- **Pace is deterministic.** Per track: `100·ln(luck-free lap) = car[model] + b·ln(skill+1)`.
  Stock builds are identical within a model, and the fit leaves ~0.02% unexplained on
  every track. Nothing varies from race to race.
- **Skill helps everywhere, including at full speed.** Skill 1→70 is worth ~0.65–0.9%,
  and 1.15% on Mudpit (all dirt).
- **Car choice usually matters more than skill.** The worst model trails the best by
  0.5% (Stone Park) to 9.2% (Speedway). The ranking changes completely with the track:
  top speed wins Speedway, braking and handling win Parkland.
- **Luck is Torn's two hidden coins.** They're simulated with the constants in
  `fast-band-delta/torn_race_model.py`, vectorised, and match `simulate()` exactly.
  Each car flips its own coins, so equal pace means exactly equal chances. The matcher
  minimises the pace spread across the field (a bottleneck assignment with car counts),
  and the simulation turns the spread into win chances.
- **Validated on races it wasn't fitted on.** On 158 races from the final 2 days
  (`validate_model.py`), predicted win chances matched outcomes in every band. The
  favourite won 59.5% of races against 60.2% expected.
- **Fairness depends on the track.** A best-car-to-weakest-driver handicap can only fully
  close the gap where the car spread is within the skill range: Stone Park, Underdog
  and Vector. Elsewhere the tool picks the closest subset of models. Shorter races
  and tracks with fewer segments per lap add luck, which also evens chances. Big fields
  need tighter pace: to win against 77 others a driver needs a lucky run, which magnifies
  small pace gaps. So a 78-driver field at 0.12% spread still ranges from 0.8× to 1.4× the fair share.

## Refreshing the model

`/racing/races` only reaches back ~7 days, so data only accumulates if this is run
weekly. All data stays in the gitignored `data/` (see `data/README.md`). Only
`track_model.json`, which holds aggregates only, is committed. Run from the repo root:

1. `python3 .agents/skills/race-handicap/collect_index.py`: adds the week's finished
   stock-only races to `data/stock_races_index.json`.
2. `python3 .agents/skills/race-handicap/telemetry_queue.py`: prints the missing
   Class E races (≥17 laps) as a JSON object.
3. In the user's logged-in Chrome (claude-in-chrome, on
   `https://www.torn.com/page.php?sid=racing`), run `grab_telemetry.js` with `Q` set to
   that object. It runs detached: poll `window.__done` and `window.__log` until
   `ALL DONE`, then `mv ~/Downloads/racing_stock_e_*.json data/stock_e/`. Get the user's
   OK for the downloads first.
4. `python3 .agents/skills/race-handicap/fetch_skills.py`: skill snapshots for new
   drivers, and for anyone whose latest snapshot is >3 days older than their newest
   race. Do this promptly, since skill only exists as a current value.
5. `python3 .agents/skills/race-handicap/build_model.py`, then `validate_model.py`.
   Commit `track_model.json` only if validation is still calibrated.

## Limits

- **Stock Class E only.** Upgraded cars have unknown builds, and other classes aren't fitted.
- **Few drivers are above skill ~55.** The top of the skill curve is the least certain part.
- **The standing start on lap 1 isn't simulated.** It costs every model 4–5s, within
  0.4s of each other, which is negligible for races of 25 laps or more but slightly
  favours high-acceleration cars in very short races.
