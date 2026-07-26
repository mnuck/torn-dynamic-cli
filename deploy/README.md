# deploy/

Kubernetes manifests for `torn-market-capture`: a CronJob that snapshots the
item market every 30 minutes and appends one JSON line per item to a
`prices.jsonl` on a PVC. Nothing else in this repo runs in a cluster.

It exists because item prices are only available *now* — the API has no price
history endpoint — so the series has to be accumulated by something that keeps
running whether or not a laptop is open.

## Files

| File | Role |
|---|---|
| `capture.py` | **the source of truth.** The capture script itself |
| `configmap.yaml` | **generated** from `capture.py` — do not edit by hand |
| `render-configmap.sh` | regenerates `configmap.yaml`; `--check` verifies it hasn't drifted |
| `cronjob.yaml` | the schedule (`3,33 * * * *`), pod spec, and secret wiring |
| `pvc.yaml` | 100 Mi `ReadWriteOnce` volume holding `prices.jsonl` and `capture.log` |

### Why the script is duplicated into the ConfigMap

The CronJob mounts the ConfigMap at `/scripts` and runs `python3
/scripts/capture.py`, so the script has to be *inside* the manifest. That copy
is generated, never hand-edited — the two versions had already drifted apart on
their default paths, and neither side noticed because each only ever ran where
its own defaults happened to be right.

Edit `capture.py`, then:

```bash
./deploy/render-configmap.sh
kubectl apply -f deploy/configmap.yaml
```

`./deploy/render-configmap.sh --check` exits non-zero if they've diverged.

## Running it locally

Same script, no cluster:

```bash
python3 deploy/capture.py
```

`APP_DIR` and `OUTPUT_DIR` default to this repo and `data/market-snapshots/`
respectively; in-cluster the CronJob overrides them to `/app` and `/data`. The
API key comes from `$TORN_API_KEY` or `$APP_DIR/.env`.

## First-time install

```bash
kubectl create secret generic torn-market-capture-secrets \
    --from-literal=TORN_API_KEY=<key>
kubectl apply -f deploy/pvc.yaml
kubectl apply -f deploy/configmap.yaml
kubectl apply -f deploy/cronjob.yaml
```

The secret is deliberately **not** in this repo. Pod runs non-root (65532) with
all capabilities dropped and a read-only script mount.

## Getting the data back

`prices.jsonl` lives on the PVC, not in git. Copy it down into
`data/market-snapshots/` (which is gitignored) when you want to analyze it:

```bash
kubectl cp <pod>:/data/prices.jsonl data/market-snapshots/prices.jsonl
```

## Gotchas

- **Rate limiting is expected, not an error.** Torn returns error code 5 when
  the key is busy elsewhere; `capture.py` logs and skips that item rather than
  retrying, since the next run is only 30 minutes out. A gap in the series
  costs less than a retry storm against a key that other tooling shares.
- **`prices.jsonl` is append-only.** The point is the series over time — no run
  ever rewrites an earlier line.
- **`concurrencyPolicy: Forbid`** — a slow run must not overlap the next one and
  double up on the same key.
