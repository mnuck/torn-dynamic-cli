# torn-dynamic-cli

A powerful dynamic CLI tool for the Torn API v2. Instead of hand-coding commands for each endpoint, **torn** embeds the full OpenAPI spec at compile time and auto-generates Cobra commands for every GET endpoint. Works with the official Torn game API.

## Quick Start

```bash
# Build from source
go build -o torn ./cmd/torn/

# Set your API key
export TORN_API_KEY=your_api_key_here

# Try it
./torn user profile --id 2048015
./torn faction members
./torn --help
```

## What It Does

**torn** is built on auto-generation, not manual configuration:

- **Reads the OpenAPI spec** at compile time and embeds it in the binary
- **Auto-generates commands** for every GET endpoint (no hand-coded endpoints)
- **Smart parameter handling**: Path params become `--flag` options
- **Auto-pagination**: Use `--all` to fetch every page of results
- **Custom reports**: High-level analytical commands for faction data

### Example Commands

```bash
# Auto-generated commands (from OpenAPI spec)
torn user profile --id 2048015
torn user events --all --from 1700000000
torn faction members
torn faction news --all
torn market items --id 1

# Custom reports
torn report hits --name BizzyTheBeast --days 7
torn report freeloaders
torn report goodthugs

# Get help
torn --help
torn user --help
```

## Installation

### Prerequisites

- **Go 1.24.4** or later
- **A Torn API key** (get one at https://www.torn.com/preferences.php?cat=api)

### Build from Source

```bash
git clone https://github.com/matthewnuckolls/torn-dynamic-cli.git
cd torn-dynamic-cli
go build -o torn ./cmd/torn/
```

**Optional:** Add `torn` to your `$PATH`

```bash
sudo mv torn /usr/local/bin/
```

## Configuration

### API Key

Set your API key in one of these ways:

**Option 1: Environment variable (recommended)**
```bash
export TORN_API_KEY=your_api_key_here
./torn user profile
```

**Option 2: .env file**
Create a `.env` file in the project root:
```bash
echo "TORN_API_KEY=your_api_key_here" > .env
./torn user profile
```

**Option 3: Command-line flag**
```bash
./torn user profile --key your_api_key_here
```

## Usage

### Auto-Generated Commands

The CLI reads the embedded OpenAPI spec and generates commands dynamically. Each path becomes a command, each operation becomes a subcommand.

**Path parameters** (like `{id}`) are converted to `--flag` options:

```bash
# GET /user/{id}/profile → torn user profile --id 2048015
torn user profile --id 2048015

# GET /faction/{id}/members → torn faction members --id 12345
torn faction members --id 12345
```

**Omitting a path parameter** strips that segment from the URL. This is how Torn API handles "current user":

```bash
# Omit --id → /user/profile (current user, no ID needed)
torn user profile
```

### Query Parameters

Query parameters from the OpenAPI spec become flags:

```bash
# GET /user/{id}/events?from=X&to=Y&limit=Z
torn user events --id 2048015 --from 1700000000 --to 1700086400 --limit 100
```

### Pagination

Use `--all` to automatically fetch every page of results. The CLI follows `_metadata.links.next` (or `_metadata.links.prev`) until no more pages exist:

```bash
# Fetch all events
torn user events --all

# Combine with other filters
torn user events --all --from 1700000000
```

**Note:** Pagination respects graceful pipe-breaks (e.g., stopping when grep finds a match):

```bash
# Stops automatically when grep finds the first match
torn user events --all | grep -m 1 "attack"
```

### Help

```bash
# Top-level help
torn --help

# Command help
torn user --help
torn faction --help

# Subcommand help
torn user profile --help
```

## Custom Reports

Beyond auto-generated commands, **torn** includes high-level analytical reports:

### Hits Report

Track outgoing attacks for a specific member:

```bash
torn report hits --name BizzyTheBeast --days 7
```

Shows all attacks over the last N days with targets, outcomes, and timestamps.

### Freeloaders Report

Identify faction members who are using Xanax but not participating in Organized Crime:

```bash
torn report freeloaders
```

Useful for identifying members not pulling their weight. Displays:
- Member name and level
- Xanax usage (hits they've received)
- OC participation status
- Days in faction

### Good Thugs Report

Identify Thugs who have completed at least one OC and are ready for promotion:

```bash
torn report goodthugs
```

## Development

### Update the OpenAPI Spec

The spec is embedded at build time. To update to the latest Torn API definition:

```bash
# Fetch the latest spec from Torn
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json

# Vet, test, then build
go vet ./cmd/torn/
go test ./cmd/torn/
go build -o torn ./cmd/torn/
```

Current spec version: **5.5.3**

### Run Tests

```bash
go test ./cmd/torn/
```

Tests use `httptest` to mock the Torn API. Coverage includes:
- Happy path command execution
- HTTP error codes (4xx, 5xx)
- Malformed JSON responses
- Torn-specific error handling (200 status with error body)
- Missing/empty path parameters

### Project Structure

```
torn-dynamic-cli/
├── cmd/torn/
│   ├── main.go                    # Entry point, spec loading
│   ├── loader.go                  # OpenAPI struct unmarshalling
│   ├── command_factory.go         # Auto-generates Cobra commands
│   ├── executor.go                # HTTP execution, auth, pagination
│   ├── env.go                     # .env file loading
│   ├── report.go                  # Report command registry
│   ├── report_hits.go             # Hits report implementation
│   ├── report_freeloaders.go      # Freeloaders report implementation
│   ├── report_goodthugs.go        # Good Thugs report implementation
│   ├── cli_test.go                # Unit tests
│   └── torn_openapi_v2.json       # Embedded OpenAPI spec
├── go.mod / go.sum                # Go dependencies
├── CLAUDE.md                      # Development notes
└── README.md
```

## Dependencies

- **[cobra](https://github.com/spf13/cobra)** - CLI framework
- **[pflag](https://github.com/spf13/pflag)** - Flag parsing
- **[gjson](https://github.com/tidwall/gjson)** - JSON path queries (pagination metadata)

## Architecture Highlights

### Command Generation

1. **LoadSpec** parses the embedded OpenAPI JSON
2. **BuildCommands** walks the spec and creates Cobra commands for each path
3. Path parameters are resolved via `$ref` and registered as flags
4. At runtime, **ExecuteRequest** assembles the URL, sets auth headers, and makes the HTTP call

### Authentication

API calls include an `Authorization: ApiKey <key>` header:

```
Authorization: ApiKey your_api_key_here
```

The key is read from the `--key` flag, `TORN_API_KEY` env var, or `.env` file (in that order).

### Error Handling

The CLI gracefully handles:
- Broken pipes (when piping to grep, head, etc.)
- HTTP errors (4xx, 5xx)
- Malformed JSON responses
- Torn API errors (200 status with error body)
- Missing API keys

## Troubleshooting

**"API key required"**
```bash
export TORN_API_KEY=your_key_here
```

**"command not found: torn"**
Make sure you built it first:
```bash
go build -o torn ./cmd/torn/
```

**Spec is outdated**
Update and rebuild:
```bash
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json
go build -o torn ./cmd/torn/
```

## License

See LICENSE file (if included in repository).

## Resources

- [Torn Official API Docs](https://www.torn.com/api.php)
- [OpenAPI Spec Source](https://www.torn.com/swagger/openapi.json)
- [Torn Game](https://www.torn.com/)
