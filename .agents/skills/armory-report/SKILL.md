---
id: armory-report
name: armory-report
description: Generate the faction armory restock report — checks combat armor, advanced armor, medical supplies, and grenades (accounting for loaned items) against target thresholds, prices each shortfall at current market value, and writes a Markdown report (`generated/armory-report.md`) with per-item shortfalls, item-market links, and the total vault pull required to restock. Use this skill when the user asks to "refresh the armory report", "check the armory", "what do we need to buy for the armory", "generate the restock report", "how much to restock the faction", or any request to figure out what the faction armory is missing and what it will cost.
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

1. Pulls current faction armory data:
   - `https://api.torn.com/v1/faction/info?selections=armor,medical,temporary` via `curl` — combat / advanced armor, medical supplies, and grenades in one request. Armor and grenades both expose `available` and `loaned` counts. **These selections were removed from the v2 API (error 22), so they must go to v1 directly** — the `torn` CLI (v2-only) returns an error body for them, and a failed fetch here is a hard error, not zero stock.
   - `torn torn items --ids ...` — current market prices for every tracked item (v2 still serves these fine)
2. Uses the API’s `available` counts for armor and grenades, and `quantity` for medical supplies. Loaned items are already excluded from `available`.
3. Compares each item's *available* quantity against its target threshold (see below) and computes the shortfall.
4. Multiplies the shortfall by the current market price to get a per-item and grand-total restock cost.
5. Writes `generated/armory-report.md` (relative to the repo root) with a per-item breakdown, item-market links, and a "Pull $X from vault" summary line.

## Targets (hardcoded in the script — edit there to change)

| Category | Item | Target |
|----------|------|--------|
| Combat / Advanced armor | each item | **3 available** |
| Medical | Empty Blood Bag | 300 |
| Medical | Small First Aid Kit | 500 |
| Medical | First Aid Kit | 200 |
| Medical | Ipecac Syrup | 100 |
| Medical | Each blood bag (A+/-, B+/-, AB+/-, O+/-) | 300 each |
| Grenades | HEG, Tear Gas, Smoke Grenade, Pepper Spray, Flash Grenade | 1000 each |

## How to run

The script must be run from the repository root (it shells out to `./torn`):

```bash
cd /path/to/torn-dynamic-cli
./.agents/skills/armory-report/generate_armory_report.sh
```

After successful validation and rendering, the file `generated/armory-report.md` is replaced atomically (the script creates the `generated/` directory if needed). Failed inventory or price requests leave the previous report untouched. The script also prints a one-line summary (total units + total cost) to stdout.

## Prerequisites

- `./torn` binary built at the repo root (run the `build-cli` skill if it's missing) — used for the market-price fetch.
- `TORN_API_KEY` set (either exported or in `.env`) with **faction** access — required for the v1 `faction/info?selections=armor,medical,temporary` calls.
- `curl` and `jq` installed (used to fetch inventory and validate/parse JSON responses).

## Gotchas

- **Inventory comes from the v1 API.** The v2 `faction` endpoint rejects the `armor`/`medical`/`temporary` selections (error 22: "This selection is only available in API v1"). The script curls v1 once for all three. API errors, missing selections, and malformed stock fail the run; valid empty arrays mean zero stock.
- **Loaned items count against availability.** Armor and grenades both return pre-computed `available` counts; do not subtract loans again. A fully-loaned-out stock has 0 available.
- **Medical items have no `loaned` field**, so only `quantity` is used there.
- **Market prices are `market_price`** from `torn torn items` (not lowest listed). Every tracked item must have exactly one positive integer price or the run fails. Actual listing prices may be lower or higher; this is a budgeting estimate, not a guaranteed upper bound.
- **Item ID list is hardcoded.** If Torn adds a new armor, medical, or grenade item you care about, add its ID to the `--ids` list and add corresponding `*_QTY` / `*_PRICE` / `*_NEED` / `*_COST` blocks plus a row in the generated Markdown template. Grenade item IDs: HEG=242, Tear Gas=256, Smoke Grenade=226, Pepper Spray=392, Flash Grenade=222.
- **Output overwrites in `generated/`.** Run from the project root (not from inside the skill directory) so `generated/armory-report.md` lands alongside other generated reports. `generated/` is gitignored — it holds regenerable output, not source.

## Regression checks

Run offline integration checks with:

```bash
python3 -m unittest discover -s .agents/skills/armory-report -p 'test_*.py'
```

These use mocked inventory and price responses and verify stock/loan calculations, empty inventories, and preservation of the previous report on request or validation failures.
