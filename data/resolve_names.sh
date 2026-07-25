#!/usr/bin/env bash
# Resolve names for ex-faction OC participants, paced to respect the rate limit.
set -euo pipefail
cd "$(dirname "$0")/.."

IDS=$(python3 -c "import json;print('\n'.join(json.load(open('data/unknown_ids.json'))))")
OUT="data/resolved_names.json"
echo "{}" > "$OUT"
SLEEP=1.2
n=0; total=$(echo "$IDS" | wc -l | tr -d ' ')

for id in $IDS; do
  name=$(./torn user profile --id "$id" 2>/dev/null \
         | python3 -c "import json,sys;print(json.load(sys.stdin)['profile'].get('name',''))" 2>/dev/null || true)
  n=$((n+1))
  if [ -n "$name" ]; then
    python3 - "$OUT" "$id" "$name" <<'PY'
import json,sys
out,i,nm=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(out)); d[i]=nm; json.dump(d,open(out,'w'))
PY
    echo "  [$n/$total] $id -> $name"
  else
    echo "  [$n/$total] $id -> (no name)"
  fi
  sleep "$SLEEP"
done
echo "Done. Resolved $(python3 -c "import json;print(len(json.load(open('$OUT'))))") of $total."
