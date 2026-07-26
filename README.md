# torn-dynamic-cli

Tooling for running a [Torn](https://www.torn.com/) faction. It started as a
dynamic CLI over the Torn API v2 and grew into everything around it — the
analysis skills, the live dashboard hub, a price-capture CronJob, and a
browser userscript.

Four moving parts, each usable on its own:

| | What | Where |
|---|---|---|
| **CLI** | `torn` — auto-generated commands for every GET endpoint in the Torn OpenAPI spec, plus hand-written faction reports | `cmd/torn/`, `pkg/` |
| **Skills** | Agent skills that do the actual faction analysis: OC spawn planning, payouts, armory restock, war net-trade, race telemetry | `.agents/skills/` |
| **Dashboard hub** | Live D3 dashboards on Cloudflare Pages | [jokerz-oc-stats.pages.dev](https://jokerz-oc-stats.pages.dev) |
| **Capture + browser** | A k8s CronJob accumulating item-market price history; a Tampermonkey userscript | `deploy/`, `userscripts/` |

---

## The CLI

Instead of hand-coding a command per endpoint, `torn` embeds the full OpenAPI
spec at compile time and generates a Cobra command tree from it. New Torn
endpoints become new commands on the next spec pull, with no code change.

### Quick start

```bash
go build -o torn ./cmd/torn/
export TORN_API_KEY=your_api_key_here

./torn user profile --id 2048015
./torn faction members
./torn --help
```

The key is read from `--key`, then `$TORN_API_KEY`, then `.env` — in that
order — and sent as `Authorization: ApiKey <key>`.

### Generated commands

Path parameters become flags. **Omitting one strips that URL segment**, which
is how Torn expresses "the current user":

```bash
./torn user profile --id 2048015   # GET /user/2048015/profile
./torn user profile                # GET /user/profile — whoever owns the key
```

Query parameters from the spec become flags too:

```bash
./torn user events --id 2048015 --from 1700000000 --to 1700086400 --limit 100
```

Direct-by-ID endpoints take the shape `/{category}/{paramId}/{resource}` and
map to `torn <category> <resource> --<paramId> <id>`. **Prefer these over
fetching a full list whenever you already have the ID:**

```bash
./torn faction crime --crimeId 1234567   # not: fetch every crime and filter
```

### Pagination

`--all` walks every page, following `_metadata.links.next` — or `prev` for the
endpoints that only paginate backwards, decided once from page one and held
for the whole walk. Broken pipes stop the walk cleanly, so this terminates
after the first match instead of fetching your entire history:

```bash
./torn user events --all | grep -m 1 "attack"
```

### Reports

Hand-written analysis on top of the generated commands:

```bash
./torn report hits --name <member> --days 7   # outgoing hit history
./torn report freeloaders                     # faction Xanax used, but no OC participation
./torn report goodthugs                       # Thugs with a completed OC, ready to promote
./torn report late-ocs                        # OCs past their ready time
./torn report oc-risk                         # OCs predicted to go late
./torn report oc-payouts                      # completed OCs awaiting payout
./torn report company                         # company star-rating health
```

---

## Skills

`.agents/skills/` holds the agent skills — this is where most of the actual
faction analysis lives. Each has a `SKILL.md` describing when to use it and
what its numbers mean; several own a generator script. `.claude/skills` is a
symlink to this directory.

**Organized crime**

| Skill | What it answers |
|---|---|
| `oc-spawning` | Which OC difficulties to spawn today, and whether members can actually fill the open slots |
| `oc-payout` | Splitting a fired OC's reward, accounting for lateness and absent members |
| `late-oc` | Who is blocking a late OC, and who was absent when it went ready |
| `oc-dashboard` | The OC revenue dashboard — revenue, profit, win rate, person-day efficiency |
| `oc-member-progression` | Who is moving up in difficulty over time; individual member journeys |
| `cpr-dashboard` | Per-member checkpoint pass rates per crime, over time |

**War, faction, and economy**

| Skill | What it answers |
|---|---|
| `war-dashboard` | Ranked-war net trade — respect dealt minus respect given up, per member |
| `respect-dashboard` | Daily faction respect gained vs. lost, split ranked-war vs. other |
| `chain-dashboard` | Animated hit race — who is carrying a chain |
| `armory-report` | What the armory is short of, and what restocking costs |
| `torn-company-status` | Company star-rating risk and rank among peers |

**Racing**

| Skill | What it answers |
|---|---|
| `racing-dashboard` | Race finishes, podiums, per-track and per-car performance |
| `fast-band-delta` | Where a race was won or lost, with the engine's hidden coin removed — plus a generative model for record odds |

**Meta**

`build-cli` (pull spec → vet → test → build) and `publish` (deploy the hub).

### The dashboard hub

The dashboards deploy to Cloudflare Pages at
**[jokerz-oc-stats.pages.dev](https://jokerz-oc-stats.pages.dev)**. The OC
revenue dashboard is the home page; the rest are served from `generated/`.

```bash
.agents/skills/publish/deploy.sh
```

`deploy.sh` stages a curated `MANIFEST` and runs `wrangler pages deploy`. It
**regenerates nothing** — refresh each dashboard through its own skill first.
It pins the Pages branch and verifies a manifest file actually serves from the
live hub afterwards, because a preview-only deploy returns 200 for every path
and otherwise looks like success.

---

## Price capture (`deploy/`)

A Kubernetes CronJob that snapshots the item market every 30 minutes and
appends to a `prices.jsonl` on a PVC. It exists because item prices are only
available *now* — the API has no price-history endpoint — so the series has to
be accumulated by something that keeps running.

`deploy/capture.py` is the source of truth; `configmap.yaml` is generated from
it by `render-configmap.sh`. See [deploy/README.md](deploy/README.md).

## Userscript (`userscripts/`)

`torn-race-standings.user.js` adds a button that reveals a race's final
standings instantly, decoding the per-segment times Torn already delivered in
the page payload. See [userscripts/README.md](userscripts/README.md).

## Data (`data/`)

Fetched API dumps and telemetry used by the skills. **Not tracked** — it's tens
of megabytes of other players' game records and this repo is public. The fetch
scripts are tracked; [data/README.md](data/README.md) maps every file to the
command that recreates it.

---

## Development

### Build

Always pull the spec first — the generated command tree comes from it:

```bash
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json
go vet ./...
go test ./...
go build -o torn ./cmd/torn/
```

Go 1.24.4. Current spec version: **6.2.0**.

### Layout

```
cmd/torn/                      # main package — CLI wiring and report commands
  main.go                      #   entry point; embeds the spec
  loader.go                    #   OpenAPI unmarshalling
  command_factory.go           #   spec → Cobra command tree, $ref resolution
  executor.go                  #   HTTP, auth, query assembly, pagination
  report*.go                   #   one file per `torn report` subcommand
  torn_openapi_v2.json         #   the embedded spec
pkg/                           # hexagonal core, for the reports
  domain/                      #   models and pure analysis services
  ports/                       #   TornClient, FactionRepository, DataRepository
  adapters/                    #   HTTP + faction implementations of those ports
.agents/skills/                # agent skills (symlinked as .claude/skills)
deploy/                        # k8s market-capture CronJob
userscripts/                   # Tampermonkey scripts
data/ · generated/             # working data and output — both gitignored
```

Report logic lives in `pkg/domain/services` behind the `pkg/ports` interfaces,
so it is unit-testable against mocks with no network. `cmd/torn` holds the CLI
wiring that binds real adapters to those ports. The generated-command path
(`command_factory.go` → `executor.go`) does not go through `pkg/` at all.

### Tests

```bash
go test ./...
```

`cmd/torn` tests drive real command execution against `httptest` servers,
covering the happy path, HTTP errors, malformed JSON, Torn's 200-with-error-body
shape, empty path params, and both pagination directions.
`pkg/domain/services` tests use hand-written mocks.

### Contributing

Never commit to `main` — branch as `feature/…` or `fix/…`, then PR. Full
workflow and per-skill notes are in [AGENTS.md](AGENTS.md).

## Resources

- [Torn API docs](https://www.torn.com/api.php) · [OpenAPI spec](https://www.torn.com/swagger/openapi.json)
- Built on [cobra](https://github.com/spf13/cobra), [pflag](https://github.com/spf13/pflag), and [gjson](https://github.com/tidwall/gjson)
