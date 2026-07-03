---
name: build-cli
description: Build the torn-dynamic-cli binary. Use this skill whenever the user asks to build the CLI, run the build, update and build, rebuild torn, or refresh the binary. Always pulls the latest OpenAPI spec before building so the generated commands reflect current Torn API endpoints.
---

# Build the torn-dynamic-cli

Run all four steps in sequence from `/Users/mnuck/torn-dynamic-cli`. Stop and report clearly on the first failure — don't continue past a broken step.

```bash
# 1. Pull latest spec
curl -s https://www.torn.com/swagger/openapi.json > cmd/torn/torn_openapi_v2.json

# 2. Vet
go vet ./cmd/torn/

# 3. Test
go test ./cmd/torn/

# 4. Build
go build -o torn ./cmd/torn/
```

On success, confirm the binary was built and note any new or changed endpoints the user might care about (compare the new spec's paths against the previous version if relevant context exists).

On failure, show the exact error output and stop. Don't attempt workarounds.
