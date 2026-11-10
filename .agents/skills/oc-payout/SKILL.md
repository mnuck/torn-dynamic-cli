---
name: oc-payout
description: >
  Pay out a Torn organized crime that has already fired. Provide a crime URL or ID, determine if it was late (≈90 s server lag), identify absent members, and split the reward (faction keeps 50 %, remainder among on‑time members). Generates payout links. Do NOT use for unfired OCs; use the late‑oc skill for pre‑execution queries.
---

# OC Payout

> **Run the commands in this doc, as written.** Don't hand-roll your own `curl` calls to
> `api.torn.com`, don't re-derive the lateness/split logic from first principles, and don't
> eyeball raw JSON instead of running the parsing snippets below. Every command and
> threshold here (the `./torn` invocations, the ~90s server-lag rule, the 30-minute grace
> period, the chain-crime handling) exists because an earlier, improvised attempt got it
> wrong. Skipping the script is how that mistake repeats.

You're helping a Torn faction leader pay out organized crimes fairly. The faction rule is
simple: **people who were not in Torn when the OC fired don't get paid.** Your job is to
tell them whether a crime was late, and if so, who to exclude and exactly how much to send
everyone else.

All `./torn` commands run from `/Users/mnuck/torn-dynamic-cli`.

## The two-step interaction this skill supports

The leader works in two beats, and you should match that rhythm:

1. **Triage** — they paste a crime URL/ID and ask "was this late?" You answer with a
   one-liner verdict so they know how to press the payout button:
   - On time → **"No — pay that one out normally."**
   - Late → **"Yes — pay out at zero, then let me know the total."**

   ("Pay out at zero" means they set the payout percentage to 0% so all the reward lands
   in the faction vault first, and then hand-distribute to only the deserving members.)

2. **Split & links** — once they've paid out at zero, they come back. You figure out the
   reward amount, split it, and hand them clickable payout links.

Don't try to do step 2 before they've paid out at zero — you need the reward to be in the
faction's hands first, and for item-reward OCs you often want to confirm the item sold.

---

## Step 1: Was it late?

**User provided a URL or ID?** Look up the crime directly — never scan the executed feed
when the user gave you an ID. The direct lookup is a single request, always works, and
avoids the time-window guessing game. A URL looks like
`https://www.torn.com/factions.php?step=your&type=1#/tab=crimes&crimeId=1685284` — the ID
is the number after `crimeId=`.

```bash
./torn faction crime --crimeId 1685284 2>&1 | python3 -c "
import json, sys, datetime
data = json.load(sys.stdin)
c = data.get('Crime') or data.get('crime')
if not c:
    print('Not found:', json.dumps(data, indent=2)); sys.exit()
ready, ex = c.get('ready_at'), c.get('executed_at')
print(f'Name:     {c.get(\"name\")}')
print(f'Status:   {c.get(\"status\")}')
print(f'Ready:    {datetime.datetime.fromtimestamp(ready, tz=datetime.timezone.utc).strftime(\"%Y-%m-%d %H:%M:%S UTC\")}')
if ex:
    delta = ex - ready
    print(f'Executed: {datetime.datetime.fromtimestamp(ex, tz=datetime.timezone.utc).strftime(\"%Y-%m-%d %H:%M:%S UTC\")}')
    print(f'Delta:    {delta}s ({delta//60}m {delta%60}s)')
    print(f'Verdict:  {\"LATE\" if delta > 90 else \"on time (server lag)\"}')
else:
    print('Not executed yet')
print(f'Prev ID:  {c.get(\"previous_crime_id\")}')
print(f'Payout:   {c.get(\"rewards\", {}).get(\"payout\")}')
"
```

**No ID provided (broad question)?** Scan for unpaid successful crimes —
`status == "Successful"` and `rewards.payout == null` means it hasn't been paid out yet.

**Chains change what "unpaid" means.** A predecessor (e.g. "No Reserve") has *no reward of its
own* — its only payoff is spawning a follow-up crime (e.g. "Bidding War"), and the follow-up's
payout covers both crimes' members. So a predecessor always shows `payout == null`, forever,
and that is NOT "awaiting payout". Rules the scan applies:

- A crime is a predecessor if **any** crime (executed *or* still planning/recruiting) lists it
  as `previous_crime_id`. Predecessors are never listed as unpaid on their own.
- Instead the scan lists the **follow-up** as the payable item, with its predecessor attached.
  If the follow-up hasn't executed yet, say "waiting on follow-up <id> (ready_at …)" — nothing
  is payable yet, and the predecessor must not be reported as a missed payout however old it is.
- A follow-up's payout covers the members of the follow-up **and** its predecessor, each judged
  against their own crime's `ready_at` (see Step 2a).

```bash
{ ./torn faction crimes --cat executed --filters executed_at; echo; ./torn faction crimes --cat available; } 2>&1 | python3 -c "
import json, sys, datetime
dec = json.JSONDecoder(); raw = sys.stdin.read(); crimes = []; i = 0
while i < len(raw):
    if raw[i].isspace(): i += 1; continue
    obj, i = dec.raw_decode(raw, i); crimes += obj.get('crimes', [])
by_id = {c['id']: c for c in crimes}
pred_ids = {c['previous_crime_id'] for c in crimes if c.get('previous_crime_id')}
fmt = lambda t: datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
def delta(c): return c['executed_at'] - c['ready_at']
payable, waiting = [], []
for c in crimes:
    pid = c.get('previous_crime_id')
    if pid and c['id'] in by_id:
        if c.get('status') == 'Successful' and c.get('rewards', {}).get('payout') is None: payable.append(c)
        elif not c.get('executed_at'): waiting.append(c)
    elif c['id'] not in pred_ids and c.get('status') == 'Successful' and c.get('rewards', {}).get('payout') is None:
        payable.append(c)
print('Unpaid successful crimes (predecessors folded into follow-ups): %d' % len(payable))
tag = lambda c: 'LATE' if delta(c) > 90 else 'on time'
for c in sorted(payable, key=lambda x: x.get('executed_at') or 0, reverse=True):
    print('  %s  %-28s delta=%ss [%s] exec=%s' % (c['id'], c['name'], delta(c), tag(c), fmt(c['executed_at'])))
    if c.get('previous_crime_id'):
        p = by_id.get(c['previous_crime_id'])
        info = '%s, delta=%ss [%s]' % (p['name'], delta(p), tag(p)) if p and p.get('executed_at') else 'not in this window; fetch it directly'
        print('      chain: prev=%s (%s)' % (c['previous_crime_id'], info))
for c in waiting:
    print('  WAITING follow-up %s %s (prev=%s) ready_at=%s - nothing payable yet' % (c['id'], c['name'], c['previous_crime_id'], fmt(c['ready_at'])))
"
```

A predecessor older than the executed feed's window won't be in `by_id`; if a follow-up's
predecessor is missing from the scan, fetch it directly with `torn faction crime --crimeId`.

**The server-lag rule (~90s).** Torn does not fire crimes on a tight tick — measured across
84 real successful firings, the on-time deltas form a continuous cluster from **~4s up to
~64s** with no internal gap, then jump straight to the thousands of seconds (the genuinely
late crimes). The median on-time delta is ~51s; only ~23% fire within 30s, while ~61% take
up to 60s. That empty band between ~65s and the next firings (minutes/hours out) is the real
dividing line. So a delta anywhere **up to ~90s is just server lag, not a member violation**
— call it on time. Only a delta well past that gap (minutes or hours) is a real delay.

(An earlier version of this skill used a 30s threshold; that was an unverified guess and
flagged the majority of normal firings as late. If you ever suspect the cadence has shifted,
re-measure: pull a wide `--from` window of executed crimes and look at the delta
distribution — the on-time cluster and the gap after it are obvious.)

Trust the timestamps over the user's hunch. The leader will sometimes be sure an OC was
late when it actually fired in ~60 seconds — say so plainly and explain it was server lag,
rather than agreeing. They rely on you to be the accurate one here.

**Chain crimes (`previous_crime_id` is set).** Some OC types (e.g. "No Reserve") spawn a
mandatory follow-up crime. When the follow-up executes, its payout covers the members of
**both** crimes — the follow-up and its predecessor. If a crime has a non-null
`previous_crime_id`, always fetch the previous crime too and check whether *it* was late.
The lateness of the previous crime affects who gets paid out of the follow-up's reward.
Use the same delta check on the previous crime's `ready_at` vs `executed_at`.

**The predecessor's own record will never show a payout or reward** (`rewards.money == 0`,
`payout == null`, no items) — that's by design, not a missed payout. When the user gives a
predecessor's ID, or a predecessor shows up in a scan, locate its follow-up (the crime whose
`previous_crime_id` equals it — check `--cat available` if it hasn't executed) and handle the
payout there. If the user gives a follow-up's ID, walk `previous_crime_id` back automatically;
the Step 2a lateness check then runs for **both** crimes' slot members, each against that
crime's own `ready_at`, and the split divides the follow-up's reward among everyone on time
across both.

---

## Step 2a: Who was on time vs late

You only need this for crimes that were actually late — it determines how many ways the
money splits. Pull the slot members and resolve their names:

```bash
./torn faction crime --crimeId 1685284 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
c = data.get('Crime') or data.get('crime')
for s in c.get('slots', []):
    u = s.get('user') or {}
    print(f\"{s.get('position'):20s} id={u.get('id')}\")
"
# Resolve names from the faction roster (fetch it if /tmp copy is stale):
# ./torn faction members > /tmp/faction_members.json
python3 -c "
import json
m = {x['id']: x['name'] for x in json.load(open('/tmp/faction_members.json'))['members']}
for i in [4125200, 3111376, 4162397, 4197212]:  # <-- slot IDs
    print(i, m.get(i, 'NOT IN FACTION'))
"
```

The leader applies a **30-minute grace period** in practice: a member who was away at
`ready_at` but returns to `Okay` status within 30 minutes still gets paid. Only exclude a
member if their first return to `Okay` after `ready_at` happens more than 30 minutes later
(or never happens at all in the data). So this is a two-part check per member:

1. **Status at `ready_at`** — last status change at or before `ready_at`. This is the same
   data source the `late-oc` skill uses; see that skill for deeper detail on the table and
   gotchas. If this is already `Okay`, the member is on time — no need for part 2.
2. **First return to `Okay` within the grace window** — if they were *not* `Okay` at
   `ready_at`, look for the earliest `Okay` row in `[ready_at, ready_at + 1800]`. If one
   exists, they're on time (grace applied). If none exists in that window, they're late.

**Always read `ready_at` directly from the crime JSON** rather than computing it from the
displayed date string — the raw integer from `c['ready_at']` is authoritative. Verify it
converts to the expected date before using it in BigQuery:

```bash
python3 -c "
import datetime
ready_at = <raw_value>
print(datetime.datetime.fromtimestamp(ready_at, tz=datetime.timezone.utc))
"
```

Then run both checks in one query — status at `ready_at`, and (for whoever wasn't `Okay`
then) the first `Okay` timestamp in the 30-minute grace window:

```bash
BQ_PROJECT=$(grep -m1 '^BQ_PROJECT=' .env | cut -d= -f2- | tr -d "\"' ")
bq query --project_id="${BQ_PROJECT:?set BQ_PROJECT in .env}" --use_legacy_sql=false --format=json \
  "WITH at_ready AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY member_name ORDER BY timestamp DESC) AS rn
    FROM \`$BQ_PROJECT.torn_rw_stats.state_changes\`
    WHERE member_name IN ('yadak','Jerventures','sykes07','LalalaLra')
      AND timestamp <= TIMESTAMP_SECONDS(<ready_at_unix>)
      AND timestamp >= TIMESTAMP_SECONDS(<ready_at_unix> - 86400 * 14)
  ),
  grace_return AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY member_name ORDER BY timestamp ASC) AS rn
    FROM \`$BQ_PROJECT.torn_rw_stats.state_changes\`
    WHERE member_name IN ('yadak','Jerventures','sykes07','LalalaLra')
      AND status_state = 'Okay'
      AND timestamp >= TIMESTAMP_SECONDS(<ready_at_unix>)
      AND timestamp <= TIMESTAMP_SECONDS(<ready_at_unix> + 1800)
  )
  SELECT
    a.member_name,
    a.status_state AS status_at_ready,
    FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', a.timestamp) AS ts_at_ready,
    g.status_state AS first_okay_in_grace,
    FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', g.timestamp) AS ts_returned
  FROM at_ready a
  LEFT JOIN grace_return g ON g.member_name = a.member_name AND g.rn = 1
  WHERE a.rn = 1
  ORDER BY a.member_name"
```

**Reading the result:**
- `status_at_ready = "Okay"` → **on time, gets paid.** (ignore the grace columns)
- `status_at_ready != "Okay"` and `ts_returned` is non-null and within 1800s of `ready_at` →
  **on time, gets paid** (grace period covers them).
- `status_at_ready != "Okay"` and `ts_returned` is null (no `Okay` row in the window) →
  **late, gets nothing.**

Watch the timestamps: a returned `ts_at_ready` on a *different day* than ready_at just means
that was their last status change (they sat "Okay" since then, which is fine — the tracker
only logs changes). If a member has **no rows at all**, tracking doesn't reach that far
back; fall back to a CSV export as described in the `late-oc` skill rather than assuming
they were absent.

This grace period is purely about a member's individual return-to-Okay timing — it's
unrelated to the crime-level **~90-second server-lag rule** in Step 1, which compares
`ready_at` to `executed_at` for the crime itself.

---

## Step 2b: How much was the reward

There are two kinds of OC reward, and they behave differently:

**Cash OCs.** The reward is money. The cleanest source is the leader: when they hit the
payout button it shows the gross total (e.g. they told you `$8,010,000`). Use that figure.
Note that the crime's `rewards.money` field reads `0` *after* a payout has been applied, so
don't trust it to recover the gross — ask the leader for the number they saw.

**Item OCs.** Some OC types (e.g. "Best of the Lot") pay an **item, not cash** — you'll see
`rewards.money == 0` and an entry under `rewards.items` even on crimes that were paid at
50%. There's no cash in the vault; the item went to the armory. The "$" the leader cares
about is what that item is worth. Look it up and get the **live market floor** (the lowest
current listing is the realistic quick-sale price):

```bash
# What is the item?
./torn torn items --ids 520 2>&1 | python3 -c "
import json,sys
for it in json.load(sys.stdin).get('items',[]):
    if it['id']==520: print(it['name'], '| ref market_price:', it['value']['market_price'])
"
# Live floor (cheapest listings first):
./torn market itemmarket --id 520 --limit 10 2>&1 | python3 -c "
import json,sys
def walk(o):
    if isinstance(o,dict):
        if 'listings' in o: return o['listings']
        for v in o.values():
            r=walk(v)
            if r is not None: return r
    return None
for l in (walk(json.load(sys.stdin)) or [])[:8]:
    print(f\"  \${l['price']:>12,}  x{l['amount']}\")
"
```

Use the lowest listing as the sale value. Mention to the leader that this assumes the item
sold at the current floor — that's usually fine, but it's their call.

---

## Step 2c: Split and generate links

The rule: **faction keeps 50%; the other 50% splits equally among on-time participants
only.** Divide the 50% pot by the number of *on-time* members — late members are simply
left out of the divisor, not paid a reduced share. Round to whole dollars.

```
per_member = round( (gross * 0.5) / number_of_on_time_members )
```

Example from a real run: gross `$1,075,361`, two on-time members (sykes07, LalalaLra) →
faction `$537,680`, and `537,680 / 2 = $268,840` each. The two late members got `$0`.

Then build **clickable Add-to-balance links** — one per on-time member. The URL format
(confirmed against the Torn wiki) pre-fills the faction "Give to User → Add to balance"
form; it does **not** submit, so the leader still clicks ADD MONEY themselves:

```
https://www.torn.com/factions.php?step=your#/tab=controls&addMoneyTo=<userID>&money=<amount>
```

Present them as markdown links so they're one click each:

```markdown
- [**Pay sykes07** [4162397] — $268,840](https://www.torn.com/factions.php?step=your#/tab=controls&addMoneyTo=4162397&money=268840)
- [**Pay LalalaLra** [4197212] — $268,840](https://www.torn.com/factions.php?step=your#/tab=controls&addMoneyTo=4197212&money=268840)
```

`addMoneyTo` = "Add to balance" (the leader's normal choice). If they ever want a direct
cash transfer instead, swap in `giveMoneyTo`. The parallel point/points params are
`addPointsTo` / `givePointsTo` with `points=` — rarely needed here.

If the leader asks you to *open* the links in tabs instead of handing them over, you can use
the browser tools (one tab per member) — but never click ADD MONEY for them. Moving money is
their confirmation to make, every time.

---

## Quick reference: the whole flow

1. **URL/ID provided?** Look up the crime directly with `torn faction crime --crimeId`.
   Always prefer this over scanning the executed feed.
2. **No ID?** Scan for `status == "Successful"` and `rewards.payout == null`.
   Already-paid crimes have `rewards.payout` populated.
3. **Chain check:** a predecessor (something another crime lists as `previous_crime_id`) never
   has its own payout and is never "unpaid" — pay it via its follow-up, which may still be
   planning (nothing payable until it fires). Given a follow-up, fetch and check the
   predecessor too; its members are judged against the predecessor's own `ready_at`.
4. Compare `ready_at` vs `executed_at`. ≤~90s = on time → "pay out normally." More = late →
   "pay out at zero, then tell me the total."
5. (Late only) Pull slot members, resolve names, query BigQuery for status at ready_at.
   `Okay` at ready_at = paid. If not `Okay`, check for a return to `Okay` within 30 minutes
   of ready_at (grace period) — found = paid; not found = excluded.
6. Reward amount: cash → ask leader for the payout-dialog total; item → live market floor.
7. Split: faction 50%, remaining 50% ÷ on-time members, rounded.
8. Hand over clickable `addMoneyTo` links for the on-time members only.
