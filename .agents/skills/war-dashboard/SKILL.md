---
name: war-dashboard
description: Build a Torn ranked-war net-trade dashboard — respect dealt vs. respect given up per faction member, the cumulative war margin, and the cost of exposure without offence. Use this skill when the user wants to "build the war dashboard", "analyse war <id>", "how did we do in the war", "who traded up in the war", "where did the war margin go", or wants a per-member breakdown of a finished ranked war. Needs only Python and a Torn API key.
---

# War net-trade dashboard

Analyses a finished ranked war by **net respect trade** — respect dealt minus respect
given up, per member — and renders a self-contained HTML page.

Self-contained: Python 3.9+, the standard library, and a Torn API key. No other tooling,
no manual data entry, no spreadsheet.

## Files

| File | Role |
|---|---|
| `war_dashboard.py` | fetches from the Torn API v2, computes, renders |
| `template.html` | the page — style + markup + charting, with a `__DATA__` placeholder |

## Run it

```bash
python3 war_dashboard.py <war_id>
```

The API key is read from `--key`, `$TORN_API_KEY`, or a `.env` file in the working
directory or next to the script. A **limited**-access key or better is required (faction
attack log + ranked war report).

Useful flags:

- `--cache FILE` — store/reuse the raw attack log. A full war is ~10k records over ~100
  requests; a finished war is immutable, so the cache never goes stale. **Use this while
  iterating on presentation.**
- `--fragment` — emit without the `<html>`/`<head>` wrapper, for embedding somewhere that
  supplies its own document shell.
- `--faction ID` — override which combatant is "us" (defaults to the key's own faction).
- `--json FILE` — also write the computed data, for checking numbers independently.

Stdout prints the totals and the full reconciliation walk. Read it — it's the check that
the run is sound.

## The framing (read before changing any copy)

In a ranked war the enemy scores respect for **every hit they land on us**. So respect
absorbed is a **cost**, not a contribution:

- Dealing damage *and* taking it is **holding ground** — exposure is the unavoidable price
  of attacking, and these members are usually net-positive.
- Being exposed *without* attacking is **net-negative** for the faction, however many hits
  were soaked. That absorbed respect is pure enemy score.

An earlier version used targeted / frontline / striker / quiet quadrants. That model was
dropped: it framed being farmed as something happening *to* a member, when exposure is
largely a choice (hospitalise before logging off, travel, sit in jail). Net trade says the
same thing in one number and points at the fix.

## No money, on purpose

**This dashboard deliberately contains nothing about pay.** It exists to inform how payouts
*should* work, so feeding existing payouts back into it would be circular — the model would
end up justifying whatever the last formula did.

Everything here is contribution and activity measured straight from the attack log. If
someone asks to add paycheck, $/respect, or payout share, that is the circularity the
omission is protecting against — say so before adding it.

## Tone — non-negotiable

Faction members are teammates who are improving. Never disparage anyone, and never build a
"worst offenders" list. The exposure finding is framed as **war discipline everyone can
execute** and as an **aggregate opportunity**, not a per-member indictment. Keep the numbers
honest and the language constructive.

Two guardrails already in the page — keep them:

- The counterfactual is labelled an **upper bound**, with copy stating it is not a target:
  you cannot always reach safety before the first hit lands.
- The roster table sorts by net descending. That is a deliberate default, but it does rank
  people, so don't stack further ranking devices on top of it.

## How the numbers are derived

Everything comes from two endpoints:

- `/faction/{war_id}/rankedwarreport` — war window, official scores, our roster
- `/faction/attacks?from=&to=` — every attack in the window

Per member, over records where `is_ranked_war` is true: **dealt** is `respect_gain` on
attacks they made, **absorbed** is `respect_gain` the enemy earned on attacks against them.

### Three traps

1. **Never use `respect_loss`.** It tracks the faction's persistent accumulated respect
   balance outside ranked war (roughly a quarter of the attacker's gain). Ranked war is
   purely a tug of war over `respect_gain`. Using it understates the cost side ~4×.

2. **Don't page with `_metadata.links.next`.** It stops early and repeats records — on war
   45796 it quit 12 hours before the war ended and returned 81 duplicate ids, losing ~27%
   of the log. Page by the last record's timestamp and dedupe by attack id, which is what
   `fetch_attacks()` does.

3. **Chain-milestone bonuses need separating.** A milestone record carries the bonus amount
   in `modifiers.chain` *and* an identical `respect_gain`; an ordinary chained hit has a
   fractional multiplier there (1.37, 2.0, …). That test is exact — it reproduced all 76
   members' bonuses on war 45796 with zero error. Note `modifiers.chain > 1` alone is
   **not** a valid test; it matches every chained hit.

4. **The API is not perfectly reproducible.** Two fetches of the same finished war can
   disagree on a record or two: Torn sometimes returns a stealth attack with
   `attacker: null` and `is_ranked_war: false`, and sometimes with the attacker named and
   the war flag set — which flips whether it counts at all. Observed at 1 record in 9,565
   (0.01%) on war 45796, moving one member's total by a single hit. Immaterial to any
   conclusion, but it means two runs can differ slightly. Use `--cache` if you need a
   stable artifact to point at.

### Chain bonuses are excluded from BOTH sides

They count toward the official score, but they cluster wherever a chain happened to tick
over and say nothing about a trade. Excluding them symmetrically keeps the comparison
honest.

**Consequence: the margin reads below Torn's official score by design.** For war 45796,
+8,605 against an official +9,665. The reconciliation panel shows the whole walk:

```
official margin − bonuses we earned + bonuses they earned off us − residual = net trade
        +9,665  −            3,610  +                      2,560  −       10 =    +8,605
```

The script asserts this closes and aborts if it doesn't. **Don't "fix" the gap** — it's the
exclusion working as intended. A residual under ~1% of the official score is expected
(timing edges at the window boundary); a large one means something is wrong.

## Design notes

Dark-only theme (navy panels, gold + cyan accents), committed deliberately rather than by
omission. Tokens are defined on `.hub` rather than `:root` and the ground is pinned on
`html,body`, so a light-themed host can't bleed through; `cvar()` reads tokens off `.hub`
to match. Semantic green/red for net trade is kept separate from the cyan accent.

Sections run summary → detail: stat tiles, the margin waterfall, the dealt-vs-given-up
scatter, the exposure counterfactual, then the full roster.

## Adapting it

- **Different faction:** nothing is hardcoded — the roster, names, and both factions come
  from the war report. `--faction` only matters if the key belongs to neither combatant.
- **Different threshold** for "not attacking": `QUIET_THRESHOLD` is the `dealt < 50` cut in
  `build()`. It drives the leak stat and the counterfactual.
- **Restyling:** `template.html` is standalone. Keep `__DATA__` and `__WAR__` intact and
  the shape of the objects in `DATA.members`.
