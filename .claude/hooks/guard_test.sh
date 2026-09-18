#!/usr/bin/env bash
# Tests for .claude/hooks/guard.sh and .githooks/. Run from anywhere:
#   .claude/hooks/guard_test.sh
# Builds throwaway git repos under mktemp; never touches this checkout's state.
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
GUARD="$REPO/.claude/hooks/guard.sh"
pass=0 fail=0

# A 16-char key-shaped string, built at runtime so this file never contains one.
FAKE_KEY=$(printf 'Q%.0s' {1..16})

check() { # check <allow|block> <dir> <json> <label>
    local want=$1 dir=$2 json=$3 label=$4 got
    CLAUDE_PROJECT_DIR=$dir "$GUARD" <<<"$json" >/dev/null 2>&1
    [[ $? == 2 ]] && got=block || got=allow
    if [[ $got == "$want" ]]; then pass=$((pass + 1)); else
        fail=$((fail + 1)); echo "FAIL: expected $want, got $got — $label"; fi
}
bash_cmd() { check "$1" "$2" "$(jq -n --arg c "$3" '{tool_name:"Bash",tool_input:{command:$c}}')" "$3"; }
file_op() { check "$1" "$REPO" "$(jq -n --arg t "$2" --arg p "$3" '{tool_name:$t,tool_input:{file_path:$p}}')" "$2 $3"; }
browse() { check "$1" "$REPO" "$2" "$3"; }

new_repo() {
    local d; d=$(mktemp -d)
    git -C "$d" init -q -b main
    git -C "$d" config user.email t@example.com; git -C "$d" config user.name t
    echo hi >"$d/tracked.txt"; git -C "$d" add tracked.txt; git -C "$d" commit -qm init
    echo "$d"
}

# --- On main ---------------------------------------------------------------
M=$(new_repo)
bash_cmd block "$M" 'git commit -m "x"'
bash_cmd block "$M" 'git push'
bash_cmd block "$M" 'git push -u origin'
bash_cmd allow "$M" 'git checkout -b feature/x && git commit -m "x"'
bash_cmd allow "$M" 'git status'
bash_cmd allow "$M" 'git pull'

# --- On a feature branch -----------------------------------------------------
F=$(new_repo); git -C "$F" checkout -qb feature/x
bash_cmd allow "$F" 'git commit -m "feat: x"'
bash_cmd allow "$F" 'git push -u origin feature/x'
bash_cmd allow "$F" 'git push -u origin fix/main-menu'
bash_cmd block "$F" 'git push origin main'
bash_cmd block "$F" 'git push origin HEAD:main'
bash_cmd block "$F" 'git push origin refs/heads/main'
bash_cmd block "$F" 'git push --force origin feature/x'
bash_cmd block "$F" 'git push -f origin feature/x'
bash_cmd block "$F" 'git push -uf origin feature/x'
bash_cmd allow "$F" 'git push --force-with-lease origin feature/x'
bash_cmd block "$F" 'git commit --no-verify -m x'
bash_cmd block "$F" 'git add -A'
bash_cmd block "$F" 'git add --all && git commit -m x'
bash_cmd block "$F" 'git add .'
bash_cmd block "$F" 'git add -- .'
bash_cmd block "$F" 'git add -f data/x.json'
bash_cmd allow "$F" 'git add AGENTS.md .agents/skills/publish/SKILL.md'
bash_cmd allow "$F" 'git add ./foo.go'
bash_cmd allow "$F" 'git add -u'

# Heredoc bodies are data: messages that *mention* blocked commands are fine...
NL=$'\n'
bash_cmd allow "$F" "git commit -F - <<'EOF'${NL}feat: block --no-verify and git push origin main${NL}${NL}Also git add -A and wrangler pages deploy.${NL}EOF"
bash_cmd allow "$F" "gh pr create --title t --body \"\$(cat <<'EOF'${NL}Stops git reset --hard and git push --force.${NL}EOF${NL})\""
# ...but a real command after the heredoc still counts.
bash_cmd block "$F" "git commit -F - <<EOF${NL}msg${NL}EOF${NL}git push origin main"
bash_cmd block "$F" "cat <<EOF${NL}msg${NL}EOF${NL}git commit --amend --no-verify"

# Clean tree: resets are harmless.
bash_cmd allow "$F" 'git reset --hard origin/main'
bash_cmd allow "$F" 'git checkout -- .'
# Dirty tracked file: resets would destroy work.
echo changed >>"$F/tracked.txt"
bash_cmd block "$F" 'git reset --hard origin/main'
bash_cmd block "$F" 'git fetch && git reset --hard HEAD'
bash_cmd block "$F" 'git checkout -- .'
bash_cmd block "$F" 'git checkout .'
bash_cmd block "$F" 'git checkout -f main'
bash_cmd block "$F" 'git restore .'
bash_cmd block "$F" 'git restore --staged --worktree .'
bash_cmd allow "$F" 'git restore tracked.txt'
bash_cmd allow "$F" 'git checkout main'
git -C "$F" checkout -q -- tracked.txt
# Untracked files: git clean would delete them.
bash_cmd allow "$F" 'git clean -fd'
touch "$F/untracked.txt"
bash_cmd block "$F" 'git clean -fd'
bash_cmd allow "$F" 'git clean -n'

# Secrets in the diff about to be committed.
echo "url = 'https://api.torn.com/user/?key=$FAKE_KEY'" >>"$F/tracked.txt"
bash_cmd block "$F" 'git commit -am "oops"'
git -C "$F" checkout -q -- tracked.txt
echo "TORN_API_KEY=${FAKE_KEY}" >"$F/.env"
echo "line using $FAKE_KEY" >>"$F/tracked.txt"
bash_cmd block "$F" 'git commit -am "oops"'
git -C "$F" checkout -q -- tracked.txt
bash_cmd allow "$F" 'git commit -m "clean"'

# --- Deploy and cluster --------------------------------------------------------
bash_cmd block "$REPO" 'npx wrangler pages deploy /tmp/x --project-name p'
bash_cmd allow "$REPO" 'wrangler whoami'
bash_cmd allow "$REPO" '.agents/skills/publish/deploy.sh'
bash_cmd allow "$REPO" 'kubectl apply -f deploy/configmap.yaml'   # in sync right now
bash_cmd block "$F" 'kubectl apply -f deploy/configmap.yaml'      # no render script = can't verify
bash_cmd allow "$REPO" 'kubectl get pods'

# --- File edits ----------------------------------------------------------------
file_op block Write "$REPO/deploy/configmap.yaml"
file_op block Edit deploy/configmap.yaml
file_op allow Edit "$REPO/deploy/capture.py"
file_op block Edit "$REPO/.env"
file_op block Write "$REPO/.env.local"
file_op allow Edit "$REPO/.env.example"
file_op allow Edit "$REPO/.envrc"
file_op allow Edit "$REPO/AGENTS.md"

# --- Browser -------------------------------------------------------------------
PAY='https://www.torn.com/factions.php?step=your#/tab=controls&addMoneyTo=1&money=5'
browse block "{\"tool_name\":\"mcp__claude-in-chrome__navigate\",\"tool_input\":{\"url\":\"$PAY\"}}" "chrome navigate to payout"
browse block "{\"tool_name\":\"mcp__Claude_Browser__navigate\",\"tool_input\":{\"url\":\"${PAY/add/give}\"}}" "pane navigate to giveMoneyTo"
browse block "{\"tool_name\":\"mcp__Claude_Browser__browser_batch\",\"tool_input\":{\"actions\":[{\"name\":\"navigate\",\"input\":{\"url\":\"$PAY\"}}]}}" "payout nested in batch"
browse allow '{"tool_name":"mcp__claude-in-chrome__navigate","tool_input":{"url":"https://www.torn.com/factions.php?step=your#/tab=crimes"}}' "ordinary torn page"

# --- .githooks -------------------------------------------------------------------
G=$(new_repo); git -C "$G" config core.hooksPath "$REPO/.githooks"
hook() { # hook <allow|block> <label> <cmd...>
    local want=$1 label=$2 got; shift 2
    if (cd "$G" && "$@" >/dev/null 2>&1); then got=allow; else got=block; fi
    if [[ $got == "$want" ]]; then pass=$((pass + 1)); else
        fail=$((fail + 1)); echo "FAIL: expected $want, got $got — githook: $label"; fi
}
echo a >>"$G/tracked.txt"; git -C "$G" add tracked.txt
hook block "commit on main" git commit -qm x
git -C "$G" checkout -qb feature/x
hook allow "normal commit on branch" git commit -qm x
echo "?key=$FAKE_KEY" >"$G/a.txt"; git -C "$G" add a.txt
hook block "new file with key" git commit -qm x
git -C "$G" rm -q --cached a.txt; rm "$G/a.txt"
echo "TORN_API_KEY=x" >"$G/.env"; git -C "$G" add -f .env
hook block ".env force-added" git commit -qm x
git -C "$G" rm -q --cached .env
mkdir -p "$G/data"; echo '{}' >"$G/data/dump.json"; git -C "$G" add -f data/dump.json
hook block "data/*.json force-added" git commit -qm x
git -C "$G" rm -q --cached data/dump.json
pp() { printf 'refs/heads/x %s %s %s\n' "$(git -C "$G" rev-parse HEAD)" "$1" 0000000000000000000000000000000000000000 | "$REPO/.githooks/pre-push" origin url; }
hook block "pre-push to main" pp refs/heads/main
hook allow "pre-push to feature" pp refs/heads/feature/x

rm -rf "$M" "$F" "$G"
echo "$pass passed, $fail failed"
[[ $fail == 0 ]]
