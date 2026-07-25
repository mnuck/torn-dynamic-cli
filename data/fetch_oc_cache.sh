#!/usr/bin/env bash
# Build a local cache of every organized crime the faction has attempted.
# Pages through /faction/crimes manually with a sleep between calls so we
# never trip the Torn rate limit (deliberately NOT using --all).
set -euo pipefail

cd "$(dirname "$0")/.."

OUT="data/oc_cache.json"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

LIMIT=100
SLEEP=1.5          # ~40 req/min, well under Torn's 100/min cap
CAT="all"
offset=0
page=0

echo "Fetching faction OC history (cat=$CAT, limit=$LIMIT, sleep=${SLEEP}s)..."

while :; do
  page_file="$TMPDIR/page_$offset.json"
  ./torn faction crimes --cat "$CAT" --limit "$LIMIT" --offset "$offset" > "$page_file"

  count=$(python3 -c "import json,sys;print(len(json.load(open('$page_file')).get('crimes',[])))")
  echo "  offset=$offset -> $count crimes"

  if [ "$count" -eq 0 ]; then
    break
  fi

  page=$((page+1))
  offset=$((offset+LIMIT))

  if [ "$count" -lt "$LIMIT" ]; then
    break
  fi

  sleep "$SLEEP"
done

# Merge all pages, dedupe by id, sort by created_at ascending.
python3 - "$TMPDIR" "$OUT" <<'PY'
import json, sys, glob, os
tmpdir, out = sys.argv[1], sys.argv[2]
by_id = {}
for f in glob.glob(os.path.join(tmpdir, "page_*.json")):
    for c in json.load(open(f)).get("crimes", []):
        by_id[c["id"]] = c
crimes = sorted(by_id.values(), key=lambda c: (c.get("created_at") or 0))
json.dump({"count": len(crimes), "crimes": crimes}, open(out, "w"), indent=2)
print(f"Wrote {len(crimes)} unique crimes to {out}")
PY
