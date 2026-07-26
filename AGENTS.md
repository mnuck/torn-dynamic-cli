# AGENTS.md - torn-dynamic-cli

## Project Overview

This repo is the faction's whole toolchain, not just the CLI. Four parts:

| Part | Where | What |
|---|---|---|
| **CLI** | `cmd/torn/`, `pkg/` | Go binary — commands auto-generated from an embedded OpenAPI spec, plus hand-written `torn report *` analysis |
| **Skills** | `.agents/skills/` | Where most faction analysis actually lives (see Skills below). `.claude/skills` symlinks here |
| **Dashboard hub** | `.agents/skills/publish/` | Cloudflare Pages deployment of the generated dashboards |
| **Capture + browser** | `deploy/`, `userscripts/` | k8s price-capture CronJob; Tampermonkey userscript |

Working directories `data/` and `generated/` are both gitignored; each has a README explaining what belongs there.

**Spec source:** `https://www.torn.com/swagger/openapi.json` (no auth required). To update: `curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json`

## Architecture (Go)

Two layers. `cmd/torn/` is the `main` package holding CLI wiring, the spec, and the report commands. `pkg/` is a hexagonal core used **only by the reports** — the generated-command path never touches it.

| File | Responsibility |
|------|---------------|
| `cmd/torn/main.go` | Entry point. Embeds spec via `//go:embed`, calls LoadSpec then BuildCommands |
| `cmd/torn/loader.go` | OpenAPI structs and JSON unmarshalling (`LoadSpec`) |
| `cmd/torn/command_factory.go` | Builds Cobra command tree from spec paths. Resolves `$ref` parameters. Registers flags |
| `cmd/torn/executor.go` | HTTP execution, auth, query param assembly, pagination loop (`ExecuteRequest`) |
| `cmd/torn/api_types.go` | Shared response shapes |
| `cmd/torn/env.go` | `.env` file loader |
| `cmd/torn/report.go` | `NewReportCmd()` registry, `fetchAllPages()`, `memberInfo`, `getAPIKey()` shared helpers |
| `cmd/torn/report_*.go` | One file per subcommand: `freeloaders`, `goodthugs`, `hits`, `late_ocs`, `oc_payouts`, `oc_risk`, `company_status` |
| `pkg/domain/` | Models and pure analysis services — no network, no CLI |
| `pkg/ports/` | `TornClient`, `FactionRepository`, `DataRepository` interfaces |
| `pkg/adapters/` | HTTP and faction implementations of those ports |

**Command generation pipeline:** LoadSpec -> BuildCommands -> ExecuteRequest (at runtime)

**Report pipeline:** `cmd/torn/report_*.go` binds a real adapter to a port, then calls a `pkg/domain/services` function. Put analysis logic in the service (testable against `mocks_test.go` with no network), not in the command.

**Key patterns:**
- Path params like `{id}` become `--id` flags; omitting them strips the segment from the URL (Torn API treats `/user/profile` as "current user")
- Query params from both Operation-level and PathItem-level are registered as flags
- `--all` enables auto-pagination. **Direction is locked in from page one** and never changes mid-walk: `next` normally, or `prev` for endpoints that expose only `prev`. Do not reintroduce a `prev` fallback when `next` empties — `next` going empty is the end of the range, and falling back to `prev` re-walks pages in reverse and drifts out of the requested window (see the comments in `executor.go` and `report.go`)
- Auth via `--key` flag or `TORN_API_KEY` env var, sent as `Authorization: ApiKey <key>` header
- Graceful pipe-break detection (e.g. `torn user events --all | grep -m 1 foo`)
- Direct-by-ID endpoints follow the shape `/{category}/{paramId}/{resource}` (e.g. `/faction/{crimeId}/crime`), which maps to `torn <category> <resource> --<paramId> <id>`. Always prefer these over fetching the full list when you have an ID.

## Build & Test

**Always update the spec before building:**

```bash
# 1. Pull latest OpenAPI spec
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json

# 2. Vet, test, then build (./... — pkg/ has tests too)
go vet ./...
go test ./...
go build -o torn ./cmd/torn/
```

**Go version:** 1.24.4
**Module:** `github.com/mnuck/torn-dynamic-cli`
**Current spec version:** 6.2.0

## Dependencies

- `github.com/spf13/cobra` - CLI framework
- `github.com/spf13/pflag` - Flag parsing
- `github.com/tidwall/gjson` - JSON path queries for pagination metadata

## Usage

```bash
# Set API key via env (preferred)
export TORN_API_KEY=<your_key>

# Examples
torn user profile --id 2048015
torn user attacks --all --from 1700000000
torn faction members
torn market items
torn --help
```

## Testing Conventions

- `cmd/torn/` tests use `httptest.NewServer` to mock the Torn API and drive real command execution. Coverage: happy path, HTTP error codes, malformed JSON, Torn-specific 200-with-error-body, empty path params, both pagination directions
- `pkg/domain/services/` tests run against hand-written mocks in `mocks_test.go` — no network
- No external test framework; standard `testing` package only

## Code Conventions

- `cmd/torn/` is one `main` package; `pkg/` is split by hexagonal layer
- Concrete structs with JSON tags at the CLI edge; interfaces only at `pkg/ports`
- Comments explain "why" and Torn-specific API quirks, not "what"
- Error wrapping with `fmt.Errorf("context: %w", err)`
- Flags registered with nil-check to avoid duplicates when paths overlap

## Skills

`.agents/skills/` contains agent skills and utilities. `.claude/skills` is a symlink to it, so both paths reach the same files.

**Organized crime**
- `late-oc/` - Late OC investigation skill
- `oc-payout/` - Splitting a fired OC's reward; lateness and absent-member handling
- `oc-spawning/generate_oc_spawn_report.sh` - OC spawn planning report; all fetch/CPR/demand logic lives in `oc_spawn_report.py` (agents run the script and interpret output, never reimplement the analysis). Caches executed crimes at `~/.torn_cache/executed_crimes_cache.json`. `oc_probability.py` wraps the **unofficial, third-party** tornprobability.com API — best-effort enrichment only, never something the pipeline depends on; `backfill_win_probability.py` is the idempotent, rate-limited backfill over cached crimes
- `cpr-dashboard/generate_cpr_dashboard.sh` - Refreshes `generated/cpr_dashboard.html`, the D3 checkpoint-pass-rate visualization. Each record's `status` is the crime-level outcome (`Successful`/`Failure`), not the per-slot member outcome; the dashboard dims `Failure` points. All per-crime cards share one x-axis (earliest data → now) so cards are comparable at a glance and stale crimes show as trailing empty space
- `oc-dashboard/` - The faction Organized Crime revenue dashboard. Holds `dashboard.html` and `update_data.py` plus a `generate_oc_dashboard.sh` wrapper. **`dashboard.html` is an intentionally tracked HTML file** (not `generated/` output): it is both the page and the datastore — `update_data.py` injects and *freezes* each historical week's item rewards/costs into it in place, so old weeks are never repriced. Incremental by default (~10s, current week only); full rebuild only on schema migration. Each refresh is committed with a `Data refresh: N crimes...` message. `update_data.py` is self-contained (stdlib + `certifi`, no `torn` binary) and reads `TORN_API_KEY` from env or the repo-root `.env`
- `oc-member-progression/` - Analytics skill (SKILL.md only) for OC member movement over time; reuses `oc-dashboard`'s `update_data.py` helpers via `sys.path`

**War, faction, and economy**
- `torn-company-status/` - Company star rating risk analysis skill
- `armory-report/generate_armory_report.sh` - Generates `generated/armory-report.md`; run from project root. Covers armor, medical, and grenades. Armor needs `loaned` subtracted from `quantity` by hand; the `temporary` selection (grenades) already returns a computed `available` field — don't subtract twice
- `respect-dashboard/generate_respect_dashboard.sh` - Refreshes `generated/respect_dashboard.html`, the daily faction respect-gain visualization. Shows respect *lost* to incoming attacks below the axis as well as gained above it; both sides split ranked-war vs. other
- `chain-dashboard/generate_chain_dashboard.sh` - Refreshes `generated/chain_dashboard.html`, an animated hit race over a chain. Ordering comes from each attack's `chain` field (running count after that hit); non-counting results report `chain: 0` and are dropped. Defaults to the live chain, `--chain-id` for a past one
- `war-dashboard/` - Ranked-war net-trade dashboard (see the dedicated entry below)

**Racing**
- `racing-dashboard/` - Self-contained: holds `racing_dashboard.py` and a `generate_racing_dashboard.sh` wrapper that `cd`s to repo root and forwards args to the Python script. Refreshes `generated/racing_dashboard.html`. `Racing.json` (optional extended history) is manually exported from torn.report, not auto-fetched. The `*.py` gitignore rule has a `!.agents/skills/**/*.py` exception so the generator is tracked with the skill
- `fast-band-delta/` - `fastband_delta.py` removes the engine's hidden per-segment coin to expose true capability gap per race; `torn_race_model.py` is the inverse — a generative two-coin simulator for record odds and car ceilings. **The engine is two coins, not one**: a big band coin with a mixture dwell (98.96% `randint(20,50)`, 1.04% `randint(2,5)`) plus a small coin re-flipped every segment worth 1.8% of base speed. The 1% short dwell is the entire record mechanism. The model needs a **100-lap** race; `data/*_telemetry.json` captures are 5-lap only. Per-checkpoint telemetry exists only on the browser `racingData` endpoint — fetch with claude-in-chrome (the user's real logged-in session), not the sandboxed browser

**Meta**
- `build-cli/` - Pull spec → vet → test → build
- `publish/` - Deploys the faction dashboard hub to Cloudflare Pages (see Dashboard Hub below)

## Dashboard Hub / Deployment

The faction runs a live dashboard hub on Cloudflare Pages. The OC revenue dashboard (`.agents/skills/oc-dashboard/dashboard.html`) is the home page (`index.html`); the other dashboards (cpr, racing, chain, respect, track_odds, fastband, streakiness) are served from `generated/`.

**The project name and hub URL are not in this repo.** This repo is public and the Pages project name is also the public hostname, so it lives in `.env` as `PAGES_PROJECT` (see `.env.example`); `deploy.sh` derives the URL as `https://$PAGES_PROJECT.pages.dev` and exits with a clear error if it's unset. Don't hardcode it back in — that applies to the faction name and hub URL generally, in code, docs, and skill files alike.

`.agents/skills/publish/deploy.sh` assembles a temp staging dir from a curated `MANIFEST` (edit the array in the script to change what ships) plus the OC dashboard as `index.html`, then runs `wrangler pages deploy`. It regenerates nothing — refresh each dashboard via its own skill first. Requires `wrangler` on `PATH` (the script sources nvm to find it). `.wrangler/` local state is gitignored. Use the `publish` skill for the full refresh → preview → deploy flow.

**Deploys are verified, not assumed.** Cloudflare Pages only treats its configured production branch as production, and `wrangler` infers the branch from git — so deploying from a feature branch publishes to a *preview* URL while reporting success, and the live hub silently keeps serving the old build. `deploy.sh` pins `--branch` (`PAGES_BRANCH`, default `main`) and then fetches a manifest file from the live hub and compares its content against what was staged. A preview-only deploy returns 200 for every path (falling back to `index.html`), so only a content comparison catches it. The script exits non-zero on mismatch — don't tell anyone it's live until it passes.

## Price Capture (`deploy/`)

Kubernetes CronJob `torn-market-capture`, snapshotting the item market every 30 min onto a PVC. It exists because item prices are only available *now* — the API has no price-history endpoint.

**`deploy/capture.py` is the single source of truth; `configmap.yaml` is generated from it** by `deploy/render-configmap.sh`. The CronJob mounts the ConfigMap at `/scripts`, so the copy must exist — but never hand-edit it. The two had already drifted apart once (different default paths), and neither side noticed because each copy only ever ran where its own defaults were right. `render-configmap.sh --check` exits non-zero on drift. Full detail in `deploy/README.md`.

Torn error code 5 (rate limited) is logged and skipped, not retried — the next run is 30 minutes out, and a retry storm against a shared key costs more than a gap in the series.

## Userscripts (`userscripts/`)

Tampermonkey scripts that run against torn.com itself, for data that only exists in the page. Plain ES5, `@grant none`, no build step. `torn-race-standings.user.js` decodes the per-segment times Torn already delivers in the `racingData` payload to show final standings instantly; the request only ever fires on a manual click. See `userscripts/README.md`.

## Data (`data/`)

Fetched API dumps and telemetry for the skills. **Not tracked** — `.gitignore` drops `data/**/*.{json,jsonl,csv,log}` at any depth, since it's tens of megabytes of other players' game records and this repo is public. The fetch scripts *are* tracked, and `data/README.md` maps every file to the command that recreates it.

`cars.json`, `track_paths.json`, and `Racing.json` are **not refetchable** (hand-maintained reference data and a manual torn.report export). Don't assume anything under `data/` can be regenerated without checking that table first.

## Git Workflow

**Repo:** https://github.com/mnuck/torn-dynamic-cli (public)

**Rules:**
- Never commit directly to `main` — always use feature branches
- Branch naming: `feature/<short-description>` or `fix/<short-description>`
- **Commit before switching branches.** Uncommitted edits ride along across `checkout`, so a later `git reset --hard origin/main` silently destroys them. When splitting a large working tree into several PRs, commit each slice on its branch before moving on — don't carry the remainder through a reset. (If it happens anyway: `git stash` writes a real commit, and `git stash pop` prints its SHA on the way out, so `git checkout <sha> -- <paths>` gets the work back.)

**Standard workflow for every change:**

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes, build locally (spec → vet → test → build)
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json
go vet ./...
go test ./...
go build -o torn ./cmd/torn/

# 3. User accepts the feature — then commit, push, open PR
git add <files>
git commit -m "feat: description"
git push -u origin feature/my-feature
gh pr create --title "..." --body "..."

# 4. Watch for tests to pass, then merge
gh pr merge <number> --squash --delete-branch

# 5. Clean up locally
git checkout main
git pull
git branch -d feature/my-feature
```
