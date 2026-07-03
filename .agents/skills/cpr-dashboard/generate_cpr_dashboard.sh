#!/usr/bin/env bash
# Refresh the OC Checkpoint Pass Rate dashboard.
#
# Pipeline:
#   1. faction members      -> id->name map for current members
#   2. faction crimes (all) -> data/oc_cache.json   (paged, rate-limit friendly)
#   3. transform            -> BY_MEMBER (one record per executed slot)
#   4. resolve ex-members   -> data/resolved_names.json  (ids seen in crimes but no longer in faction)
#   5. inject               -> cpr_dashboard.html   (template + data)
#
# Run from anywhere; paths are resolved relative to the repo root. Requires the
# built ./torn binary and a TORN_API_KEY (env or .env). python3 is used for JSON.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR/../../.."          # repo root

TORN="./torn"
DATA="data"
TEMPLATE="$SKILL_DIR/cpr_dashboard_template.html"
OUT="cpr_dashboard.html"
# Whose data is shown when the dashboard first opens.
DEFAULT_MEMBER="${CPR_DEFAULT_MEMBER:-TheKillingJoke}"

[ -x "$TORN" ] || { echo "error: $TORN not found/executable. Build it first: go build -o torn ./cmd/torn/" >&2; exit 1; }
mkdir -p "$DATA"

echo "==> [1/5] Fetching current faction members..."
"$TORN" faction members > "$DATA/_members_raw.json"
python3 - "$DATA/_members_raw.json" "$DATA/member_names.json" <<'PY'
import json, sys
raw, out = sys.argv[1], sys.argv[2]
members = json.load(open(raw)).get("members", [])
names = {str(m["id"]): m["name"] for m in members}
json.dump(names, open(out, "w"), indent=2)
print(f"    {len(names)} current members")
PY

echo "==> [2/5] Fetching faction OC history (paged)..."
LIMIT=100; SLEEP=1.5; offset=0
TMPDIR="$(mktemp -d)"; trap 'rm -rf "$TMPDIR"' EXIT
while :; do
  pf="$TMPDIR/page_$offset.json"
  "$TORN" faction crimes --cat all --limit "$LIMIT" --offset "$offset" > "$pf"
  count=$(python3 -c "import json;print(len(json.load(open('$pf')).get('crimes',[])))")
  echo "    offset=$offset -> $count crimes"
  [ "$count" -eq 0 ] && break
  offset=$((offset+LIMIT))
  [ "$count" -lt "$LIMIT" ] && break
  sleep "$SLEEP"
done
python3 - "$TMPDIR" "$DATA/oc_cache.json" <<'PY'
import json, sys, glob, os
tmpdir, out = sys.argv[1], sys.argv[2]
by_id = {}
for f in glob.glob(os.path.join(tmpdir, "page_*.json")):
    for c in json.load(open(f)).get("crimes", []):
        by_id[c["id"]] = c
crimes = sorted(by_id.values(), key=lambda c: (c.get("created_at") or 0))
json.dump({"count": len(crimes), "crimes": crimes}, open(out, "w"), indent=2)
print(f"    {len(crimes)} unique crimes cached")
PY

echo "==> [3/5] Finding ex-members who appear in crime history..."
python3 - "$DATA/oc_cache.json" "$DATA/member_names.json" "$DATA/unknown_ids.json" <<'PY'
import json, sys
crimes = json.load(open(sys.argv[1]))["crimes"]
known = set(json.load(open(sys.argv[2])).keys())
seen = set()
for c in crimes:
    for s in c.get("slots", []):
        u = s.get("user")
        if u and u.get("id"):
            seen.add(str(u["id"]))
unknown = sorted(seen - known, key=int)
json.dump(unknown, open(sys.argv[3], "w"), indent=2)
print(f"    {len(unknown)} ex-member ids to resolve")
PY

echo "==> [4/5] Resolving ex-member names (paced)..."
python3 - "$DATA/resolved_names.json" "$DATA/unknown_ids.json" <<'PY'
# Seed/merge: keep names we already resolved, only fetch genuinely new ids.
import json, sys, os
out, unk = sys.argv[1], sys.argv[2]
existing = json.load(open(out)) if os.path.exists(out) else {}
todo = [i for i in json.load(open(unk)) if i not in existing]
json.dump({"existing": list(existing.keys()), "todo": todo}, open("/tmp/_cpr_resolve_plan.json", "w"))
print(f"    {len(existing)} already known, {len(todo)} to fetch")
PY
TODO=$(python3 -c "import json;print('\n'.join(json.load(open('/tmp/_cpr_resolve_plan.json'))['todo']))")
if [ -n "$TODO" ]; then
  [ -f "$DATA/resolved_names.json" ] || echo "{}" > "$DATA/resolved_names.json"
  for id in $TODO; do
    name=$("$TORN" user profile --id "$id" 2>/dev/null \
           | python3 -c "import json,sys;print(json.load(sys.stdin)['profile'].get('name',''))" 2>/dev/null || true)
    [ -n "$name" ] && python3 - "$DATA/resolved_names.json" "$id" "$name" <<'PY'
import json,sys
out,i,nm=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(out)); d[i]=nm; json.dump(d,open(out,'w'),indent=2)
PY
    echo "    $id -> ${name:-(no name)}"
    sleep 1.2
  done
else
  echo "    nothing new to resolve"
fi
[ -f "$DATA/resolved_names.json" ] || echo "{}" > "$DATA/resolved_names.json"

echo "==> [5/5] Building BY_MEMBER and injecting into dashboard..."
python3 - "$DATA/oc_cache.json" "$DATA/member_names.json" "$DATA/resolved_names.json" \
          "$DATA/oc_by_member.json" "$TEMPLATE" "$OUT" "$DEFAULT_MEMBER" <<'PY'
import json, sys
cache, names_f, resolved_f, by_member_f, template_f, out_f, default_member = sys.argv[1:8]

names = json.load(open(names_f))
names.update(json.load(open(resolved_f)))   # ex-members override nothing; fill gaps

crimes = json.load(open(cache))["crimes"]
by_member = {}
for c in crimes:
    # `status` is the crime-level outcome (Successful / Failure / Expired). The
    # dashboard dims points where status == "Failure"; Expired crimes never
    # executed, so they carry no checkpoint data and are skipped here.
    if c.get("status") not in ("Successful", "Failure"):
        continue
    cname, diff, t, status = c.get("name"), c.get("difficulty"), c.get("executed_at"), c["status"]
    for s in c.get("slots", []):
        u = s.get("user")
        if not (u and u.get("id")):
            continue            # empty slot — nobody filled this position
        member = names.get(str(u["id"]), f"#{u['id']}")
        by_member.setdefault(member, []).append({
            "name": cname,
            "difficulty": diff,
            "role": s.get("position"),
            "cpr": s.get("checkpoint_pass_rate"),
            "t": t,
            "status": status,        # crime-level result, not the member's personal outcome
            "id": c.get("id"),
        })

# Sort each member's records oldest-first (stable timeline in the chart).
for recs in by_member.values():
    recs.sort(key=lambda r: r["t"] or 0)

json.dump(by_member, open(by_member_f, "w"))   # intermediate blob

blob = json.dumps(by_member, separators=(",", ":"))
html = open(template_f).read()
html = html.replace("__BY_MEMBER__", blob)
# Point DEFAULT_MEMBER at the requested member if present, else first member.
if default_member not in by_member and by_member:
    default_member = sorted(by_member)[0]
import re
html = re.sub(r'const DEFAULT_MEMBER = "[^"]*";',
              f'const DEFAULT_MEMBER = "{default_member}";', html, count=1)
open(out_f, "w").write(html)
print(f"    {len(by_member)} members, {sum(len(v) for v in by_member.values())} slot records")
print(f"    default member: {default_member}")
PY

rm -f "$DATA/_members_raw.json" /tmp/_cpr_resolve_plan.json
echo
echo "Done. Open ./$OUT in a browser."
