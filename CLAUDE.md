# CLAUDE.md - torn-dynamic-cli

## Project Overview

Dynamic CLI for the Torn API v2. Parses an embedded OpenAPI v2 spec (`cmd/torn/torn_openapi_v2.json`) and auto-generates Cobra commands for every GET endpoint. Written in Go.

**Spec source:** `https://www.torn.com/swagger/openapi.json` (no auth required). To update: `curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json`

## Architecture

All Go source lives under `cmd/torn/` (single `main` package). The OpenAPI spec is embedded there too.

| File | Responsibility |
|------|---------------|
| `cmd/torn/main.go` | Entry point. Embeds spec via `//go:embed`, calls LoadSpec then BuildCommands |
| `cmd/torn/loader.go` | OpenAPI structs and JSON unmarshalling (`LoadSpec`) |
| `cmd/torn/command_factory.go` | Builds Cobra command tree from spec paths. Resolves `$ref` parameters. Registers flags |
| `cmd/torn/executor.go` | HTTP execution, auth, query param assembly, pagination loop (`ExecuteRequest`) |
| `cmd/torn/env.go` | `.env` file loader |
| `cmd/torn/report.go` | `NewReportCmd()` registry, `fetchAllPages()`, `memberInfo`, `getAPIKey()` shared helpers |
| `cmd/torn/report_freeloaders.go` | `torn report freeloaders` — Xanax usage vs OC participation |
| `cmd/torn/report_goodthugs.go` | `torn report goodthugs` — Thugs with completed OCs, ready for promotion |
| `cmd/torn/report_hits.go` | `torn report hits --name <member> --days <N>` — outgoing hit history |

**Command generation pipeline:** LoadSpec -> BuildCommands -> ExecuteRequest (at runtime)

**Key patterns:**
- Path params like `{id}` become `--id` flags; omitting them strips the segment from the URL (Torn API treats `/user/profile` as "current user")
- Query params from both Operation-level and PathItem-level are registered as flags
- `--all` flag enables auto-pagination following `_metadata.links.next` or `_metadata.links.prev`
- Auth via `--key` flag or `TORN_API_KEY` env var, sent as `Authorization: ApiKey <key>` header
- Graceful pipe-break detection (e.g. `torn user events --all | grep -m 1 foo`)

## Build & Test

**Always update the spec before building:**

```bash
# 1. Pull latest OpenAPI spec
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json

# 2. Vet, test, then build
go vet ./cmd/torn/
go test ./cmd/torn/
go build -o torn ./cmd/torn/
```

**Go version:** 1.24.4
**Module:** `github.com/matthewnuckolls/torn-dynamic-cli`

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

- Unit tests in `cli_test.go` using `httptest.NewServer` to mock the Torn API
- Tests cover: happy path, HTTP error codes, malformed JSON, Torn-specific 200-with-error-body, empty path params
- No external test framework; standard `testing` package only

## Code Conventions

- All Go code is in the `main` package (single binary)
- No interfaces; concrete structs with JSON tags
- Comments explain "why" and Torn-specific API quirks, not "what"
- Error wrapping with `fmt.Errorf("context: %w", err)`
- Flags registered with nil-check to avoid duplicates when paths overlap

## Skills

`.claude/skills/` contains Claude skills and utilities:
- `late-oc/` - Late OC investigation skill
- `torn-company-status/` - Company star rating risk analysis skill
- `armory-report/generate_armory_report.sh` - Generates faction armory report
- `armory-report/armory-report.md` - Most recent armory report output

## Git Workflow

**Repo:** https://github.com/mnuck/torn-dynamic-cli (public)

**Rules:**
- Never commit directly to `main` — always use feature branches
- Branch naming: `feature/<short-description>` or `fix/<short-description>`

**Standard workflow for every change:**

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes, build locally (spec → vet → test → build)
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json
go vet ./cmd/torn/
go test ./cmd/torn/
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
