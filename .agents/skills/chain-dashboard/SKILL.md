---
name: chain-dashboard
description: >
  Refresh the Torn chain hit-race dashboard — an animated D3 visualization
  showing cumulative hits per faction member over the course of a chain, with
  a scrubbable timeline and play/pause. Use this skill when the user wants to
  "refresh the chain dashboard", "rebuild the chain hit race", "update
  chain_dashboard.html", or visualize who's carrying a live or past chain.
---

# Chain Hit Race Dashboard

Regenerates `generated/chain_dashboard.html`: a self-contained D3 bar-chart
race. Horizontal bars, one per attacker, stacked with the longest at top,
animating as a timeline slider scrubs (or auto-plays) through every hit in
the chain.

## How to refresh

```bash
.agents/skills/chain-dashboard/generate_chain_dashboard.sh
open generated/chain_dashboard.html
```

By default it renders the faction's **current live chain**. To render a
past, already-completed chain instead:

```bash
.agents/skills/chain-dashboard/generate_chain_dashboard.sh --chain-id 61682092
```

## How it works

Pulls `/faction/chain` for the live chain's start time (or `/faction/chainreport`
for a past chain's start/end), then walks `/faction/attacks?filters=attack`
from that timestamp, paginating via `_metadata.links.next`. Each attack record
carries a `chain` field — the running chain count immediately after that hit —
which is unique and monotonic for every hit that actually counted (`Attacked`
or `Mugged`); non-counting results (`Lost`, `Escape`, `Stalemate`, `Timeout`,
`Interrupted`, `Assist`) report `chain: 0` and are dropped. Records are also
filtered to attacks landed by our own faction's members (`attacker.faction.id`),
since incoming/unrelated attacks can slip into that endpoint's results.

The resulting ordered hit list is embedded directly in the HTML; the page
computes cumulative per-attacker totals client-side as the slider moves, so no
server or build step is needed to view or scrub it.

Each attacker gets a stable color (cycled from the project's 8-hue dark
palette, assigned in order of first appearance) that holds for the whole
timeline — color never re-encodes rank, only identity — and every bar carries
a direct name + count label, so color is a secondary channel, not the only
way to tell members apart.
