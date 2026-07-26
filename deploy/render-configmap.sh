#!/usr/bin/env bash
# Regenerate configmap.yaml from capture.py.
#
# capture.py is the single source of truth. The ConfigMap embeds a copy of it
# because that is how the CronJob gets the script into the container -- but a
# hand-edited copy drifts, and it did: the two versions disagreed on their
# default paths for months without anyone noticing, because each one only ran
# in the environment where its own defaults were right.
#
# Run this after every capture.py change, then apply:
#   ./deploy/render-configmap.sh && kubectl apply -f deploy/configmap.yaml
#
# Pass --check to verify configmap.yaml is current without writing (exit 1 if
# it has drifted).
set -euo pipefail

cd "$(dirname "$0")"

render() {
    cat <<'HEADER'
---
# GENERATED FILE -- DO NOT EDIT.
# Rendered from deploy/capture.py by deploy/render-configmap.sh.
apiVersion: v1
kind: ConfigMap
metadata:
  name: torn-market-capture-script
  namespace: default
  labels:
    app: torn-market-capture
data:
  capture.py: |
HEADER
    # Indent by 4 to sit under the `capture.py: |` block scalar. Blank lines
    # stay blank rather than becoming trailing whitespace, which some YAML
    # linters reject.
    sed 's/^\(.\)/    \1/' capture.py
}

if [[ "${1:-}" == "--check" ]]; then
    if diff -q <(render) configmap.yaml >/dev/null; then
        echo "configmap.yaml is up to date with capture.py"
    else
        echo "configmap.yaml has drifted from capture.py; run $0" >&2
        diff <(render) configmap.yaml >&2 || true
        exit 1
    fi
else
    render > configmap.yaml
    echo "Wrote configmap.yaml from capture.py"
fi
