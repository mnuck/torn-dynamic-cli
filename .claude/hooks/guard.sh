#!/usr/bin/env bash
# Claude Code PreToolUse guard for this repo (wired up in .claude/settings.json).
#
# Exit 2 blocks the tool call and hands stderr back to the agent. Each rule
# backs an AGENTS.md rule that used to be prose only: the repo is PUBLIC, main
# is never committed to directly, some files are generated, and moving money is
# always the leader's click. String matching on shell commands is a tripwire,
# not a sandbox — .githooks/ and the GitHub ruleset are the later layers.
#
# Tests: .claude/hooks/guard_test.sh
set -uo pipefail

input=$(cat)
tool=$(jq -r '.tool_name // ""' <<<"$input")
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || true

deny() {
    echo "BLOCKED by .claude/hooks/guard.sh: $1" >&2
    exit 2
}

# ERE for "end of a shell word": whitespace, a command separator, or end.
E='([[:space:];&|)]|$)'

# Heredoc bodies (commit messages, PR bodies) are data, not commands: a commit
# message that *describes* the --no-verify rule must not trip it.
strip_heredocs() {
    awk '
        term != "" { if ($0 ~ "^[ \t]*" term "[ \t]*$") term = ""; next }
        { print }
        match($0, /<<-?[ \t]*["'\'']?[A-Za-z_][A-Za-z0-9_]*/) {
            term = substr($0, RSTART, RLENGTH); sub(/^<<-?[ \t]*["'\'']?/, "", term)
        }'
}

check_bash() {
    local cmd branch
    cmd=$(jq -r '.tool_input.command // ""' <<<"$input" | strip_heredocs)
    branch=$(git branch --show-current 2>/dev/null || true)
    # grep matches line by line, so no pattern can reach across lines.
    has() { grep -qE "$1" <<<"$cmd"; }

    # Commits and pushes from main. A command that branches first
    # (`git checkout -b x && git commit`) is fine.
    if [[ $branch == main ]] && has "git[[:space:]]+(commit|push)$E" \
        && ! has "git[[:space:]]+(checkout|switch)[[:space:]]+-[bcB][[:space:]]"; then
        deny "on main — create a feature/ or fix/ branch first (AGENTS.md Git Workflow)"
    fi
    if has "git[[:space:]]+push[^;&|]*([[:space:]]|:)(refs/heads/)?main$E"; then
        deny "push targets main — open a PR instead"
    fi
    # --force-with-lease stays allowed: it's the safe way to update a rebased PR branch.
    if has "git[[:space:]]+push[^;&|]*[[:space:]](--force|-[a-zA-Z]*f[a-zA-Z]*)$E"; then
        deny "force push — use --force-with-lease on your own branch if you must"
    fi
    if has "git[[:space:]][^;&|]*--no-verify"; then
        deny "--no-verify skips the .githooks secret and branch checks"
    fi

    # Blanket staging in a public repo sweeps in whatever is lying around.
    if has "git[[:space:]]+add([[:space:]]+[^;&|]*)?[[:space:]](-A|--all|\.|\./|-f|--force)$E"; then
        deny "stage explicit paths — no 'git add -A', '.', or '-f' in this public repo"
    fi

    # Discarding uncommitted work (AGENTS.md: commit before reset).
    if has "git[[:space:]]+(reset[[:space:]][^;&|]*--hard|checkout[[:space:]]+(-f|--force)$E|checkout[[:space:]]+(--[[:space:]]+)?\.$E|restore[[:space:]]([^;&|]*[[:space:]])?\.$E)" \
        && [[ -n $(git status --porcelain --untracked-files=no 2>/dev/null) ]]; then
        deny "this discards uncommitted changes — commit them first (git stash also works)"
    fi
    if has "git[[:space:]]+clean[[:space:]][^;&|]*-[a-zA-Z]*f" \
        && [[ -n $(git clean -nd 2>/dev/null) ]]; then
        deny "git clean would delete untracked files: $(git clean -nd | tr '\n' ' ')"
    fi

    # Publishing: deploy.sh pins the production branch and verifies the live hub.
    if has "wrangler[[:space:]]+pages[[:space:]]+deploy"; then
        deny "run .agents/skills/publish/deploy.sh instead — raw wrangler can ship a preview and report success"
    fi

    # The ConfigMap is generated from deploy/capture.py.
    if has "kubectl[[:space:]]+apply[^;&|]*configmap" \
        && ! deploy/render-configmap.sh --check >/dev/null 2>&1; then
        deny "deploy/configmap.yaml has drifted from capture.py — run deploy/render-configmap.sh first"
    fi

    # Secrets about to be committed. Scans every tracked change (covers `commit -a`);
    # new untracked files are caught by .githooks/pre-commit.
    if has "git[[:space:]]+commit$E"; then
        local diff key
        diff=$(git diff HEAD 2>/dev/null; git diff --cached 2>/dev/null)
        key=$(grep -m1 '^TORN_API_KEY=' .env 2>/dev/null | cut -d= -f2- | tr -d "\"' ")
        if [[ -n $key ]] && grep -qF "$key" <<<"$diff"; then
            deny "the diff contains the TORN_API_KEY from .env"
        fi
        if grep -qE '^\+.*(key=|API_KEY=|ApiKey )["'\'']?[A-Za-z0-9]{16}([^A-Za-z0-9]|$)' <<<"$diff"; then
            deny "the diff contains what looks like a Torn API key"
        fi
    fi
}

check_file() {
    local path base
    path=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // ""' <<<"$input")
    base=${path##*/}
    if [[ $path == deploy/configmap.yaml || $path == */deploy/configmap.yaml ]]; then
        deny "configmap.yaml is generated — edit deploy/capture.py, then run deploy/render-configmap.sh"
    fi
    if [[ ($base == .env || $base == .env.*) && $base != .env.example ]]; then
        deny "$base holds secrets — ask the user to edit it"
    fi
}

check_browser() {
    # Covers navigate, preview_start, and URLs nested inside browser_batch actions.
    local urls
    urls=$(jq -r '[.. | objects | .url? // empty | strings] | join("\n")' <<<"$input")
    if grep -qE '(add|give)(Money|Points)To=' <<<"$urls"; then
        deny "payout links are for the faction leader to open and click — hand them over, don't open them"
    fi
}

case "$tool" in
    Bash) check_bash ;;
    Edit | Write | NotebookEdit) check_file ;;
    mcp__*) check_browser ;;
esac
exit 0
