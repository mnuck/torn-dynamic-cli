#!/bin/bash
APP_DIR="${APP_DIR:-/Users/mnuck/torn-dynamic-cli}"
OUTPUT_DIR="${OUTPUT_DIR:-$APP_DIR/data/market-snapshots}"
cd "$APP_DIR"

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LOG="$OUTPUT_DIR/capture.log"

log() { echo "[$TS] $*" >> "$LOG"; }

fetch_item() {
    local id=$1
    for attempt in 0; do
        result=$(./torn market itemmarket --id "$id" 2>&1)
        error_code=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error',{}).get('code',''))" 2>/dev/null)
        if [ "$error_code" = "5" ]; then
            log "item $id rate limited, skipping"
            return 1
        fi
        if echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(1 if 'error' in d else 0)" 2>/dev/null; then
            compact=$(echo "$result" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)))")
            echo "{\"timestamp\":\"$TS\",\"item_id\":$id,\"data\":$compact}" >> "$OUTPUT_DIR/prices.jsonl"
            log "item $id OK"
            return 0
        fi
        log "item $id non-retryable error: $(echo "$result" | head -3)"
        return 1
    done
}

fetch_item 552
sleep 5
fetch_item 541
