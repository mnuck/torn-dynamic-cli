---
name: oc-spawning
description: >
  Daily OC spawn planning for a Torn faction leader. Use this skill when the user
  wants to know which OC difficulty slots need to be spawned, which members need
  a next OC, or whether newly spawned OCs cover everyone. Triggers on phrases like
  "what OCs do I need to spawn", "do I need to spawn any OCs", "does that cover it",
  "what difficulty for the people finishing soon", "plan OCs for the next 24 hours",
  or any request to figure out what organized crimes to create for faction members
  who are free or about to finish their current OC.
---

# OC Spawn Planning

**All logic lives in `oc_spawn_report.py` (in this skill directory). Run it.
Do not write your own analysis script, do not call the Torn API endpoints
yourself, do not compute CPR trends or slot counts by hand.**

## The only command you need

```bash
.agents/skills/oc-spawning/generate_oc_spawn_report.sh
```

Run it from anywhere (it changes to the repo root itself). The first ever run
builds a cache of executed crimes and may take a minute; later runs take
seconds. Progress messages go to stderr; the report goes to stdout.

The script handles everything that previously went wrong when done by hand:
wall-clock reference time, full paginated history with caching and dedup,
Successful/Failure status filtering, per-(position, crime name) CPR series,
the promotion rubric, demand vs open recruiting slots, and position-fit.

## How to read the report

The report has four sections:

1. **TARGET MEMBERS** — everyone who needs a next OC: members in no
   planning/recruiting slot ("free") plus members whose planning OC fires
   within 24h ("completing"). Each line shows the recommended difficulty and
   the CPR evidence behind it.
2. **SLOTS NEEDED vs AVAILABLE** — per difficulty: who needs a slot, how many
   open recruiting slots exist, and any `SHORT` amounts.
3. **POSITION FIT** — for each open OC at a demanded difficulty, whether each
   member has at least one qualifying position (CPR ≥ 70). A difficulty can
   look "covered" by slot count while every open OC is the wrong *type* for a
   member — this section catches that.
4. **SPAWN RECOMMENDATION** — the bottom line. Relay this to the user,
   enriched with names from section 2 and any wrong-OC-type warnings from
   section 3.

Symbols in section 3: `✓` qualifies (≥ 70), `⚠` below 70, `?` no history in
that position, `~` before a number means the CPR came from a different crime
type at that difficulty (approximate — same position, different hidden
variables).

## Answering the user

- **"What do I need to spawn?"** — run the command, report the SPAWN
  RECOMMENDATION section with the member names behind each shortfall, and
  mention members who can't be placed in any currently-open OC (wrong type).
- **"I spawned some OCs — does that cover it?"** — just re-run the same
  command. It re-fetches live data; compare the new report. Do not recount
  slots by hand.
- **Recruit-rank members** — recruits can't join OCs. The script excludes
  positions named `Recruit` by default and prints a NOTE if nothing matched.
  If the user says their recruit rank has a different name, re-run with:
  `.agents/skills/oc-spawning/generate_oc_spawn_report.sh --recruit-positions "Recruit,Trainee"`
  If unsure whether the faction has recruit-rank members, ask the user.

## Domain notes (for interpreting results, not for recomputing them)

- The leader spawns OCs in difficulty bands and doesn't control exact OC
  types — that's why the report gives slot shortfalls, not OC counts, and why
  the position-fit section matters when picking which OC types to spawn.
- CPR is deterministic per (position, crime name) series; the ≥ 82 plateau →
  bump, ≥ 70 → qualified, < 70 → drop thresholds are already applied by the
  script.
- If the numbers look wildly off (e.g. hundreds of duplicate crimes), the
  cache at `~/.torn_cache/executed_crimes_cache.json` can be deleted and the
  script will rebuild it from scratch.
- Report anything the script prints as a `NOTE:` or `ERROR:` to the user
  verbatim rather than working around it.
