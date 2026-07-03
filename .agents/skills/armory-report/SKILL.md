---
id: armory-report
name: armory-report
description: Generate the faction armory restock report — checks combat armor, advanced armor, and medical supply inventory (accounting for loaned items) against target thresholds, prices each shortfall at current market value, and writes a Markdown report (`armory-report.md`) with per-item shortfalls, item-market links, and the total vault pull required to restock. Use this skill when the user asks to "refresh the armory report", "check the armory", "what do we need to buy for the armory", "generate the restock report", "how much to restock the faction", or any request to figure out what the faction armory is missing and what it will cost.
source: learned
triggers:
  - armory report
  - armory check
  - refresh the armory
  - restock report
  - what to buy for the armory
  - faction armory
  - generate armory report
  - armory restock
quality: high
---

# Armory Restock Report

## What this skill does

Runs `.agents/skills/armory-report/generate_armory_report.sh`, which:

1. Calls the `torn` CLI to pull current faction armory data:
   - `torn faction --selections armor` — combat / advanced armor (with `loaned` counts)
   - `torn faction --selections medical` — medical supplies
   - `torn torn items --ids ...` — current market prices for every tracked item
2. Subtracts loaned units from on-hand quantity (loaned items are not available to draw on).
3. Compares each item's *available* quantity against its target threshold (see below) and computes the shortfall.
4. Multiplies the shortfall by the current market price to get a per-item and grand-total restock cost.
5. Writes `armory-report.md` to the **current working directory** with a per-item breakdown, item-market links, and a "Pull $X from vault" summary line.

## Targets (hardcoded in the script — edit there to change)

| Category | Item | Target |
|----------|------|--------|
| Combat / Advanced armor | each item | **3 available** |
| Medical | Empty Blood Bag | 300 |
| Medical | Small First Aid Kit | 500 |
| Medical | First Aid Kit | 200 |
| Medical | Ipecac Syrup | 100 |
| Medical | Each blood bag (A+/-, B+/-, AB+/-, O+/-) | 300 each |

## How to run

The script must be run from the repository root (it shells out to `./torn`):

```bash
cd /path/to/torn-dynamic-cli
./.agents/skills/armory-report/generate_armory_report.sh
```

After completion the file `armory-report.md` will be written/overwritten in the cwd. The script also prints a one-line summary (total units + total cost) to stdout.

## Prerequisites

- `./torn` binary built at the repo root (run the `build-cli` skill if it's missing).
- `TORN_API_KEY` set (either exported or in `.env`) with **faction** access — required for the `faction --selections armor|medical` endpoints.
- `jq` installed (used to parse each Torn API JSON response).

## Gotchas

- **Loaned items count against availability.** The script subtracts `loaned` from `quantity` before comparing to the target, so a fully-loaned-out stock looks like 0 available.
- **Medical items have no `loaned` field**, so only `quantity` is used there.
- **Market prices are `market_price`** from `torn torn items` (not lowest listed). Real bazaar/listing prices may be lower — the totals are an upper-bound estimate for budgeting.
- **Item ID list is hardcoded.** If Torn adds a new armor or medical item you care about, add its ID to the `--ids` list and add corresponding `*_QTY` / `*_PRICE` / `*_NEED` / `*_COST` blocks plus a row in the generated Markdown template.
- **Output overwrites in cwd.** Run from the project root (not from inside the skill directory) if you want the report to land alongside other repo reports.
