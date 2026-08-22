#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/agent-pane.sh"

PASS=0
FAIL=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    PASS=$((PASS + 1))
    printf 'ok   %s\n' "$name"
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL %s\n     expected [%s] got [%s]\n' "$name" "$expected" "$actual"
  fi
}

processes="$(
  cat <<'EOF'
100 1 -zsh -zsh
101 100 claude claude --continue --dangerously-skip-permissions
200 1 node node /opt/homebrew/bin/codex --dangerously-bypass-approvals-and-sandbox
201 200 /opt/vendor/codex /opt/vendor/codex --dangerously-bypass-approvals-and-sandbox
300 1 copilot copilot --session-id=x
301 300 claude claude -p reviewer
400 1 -zsh -zsh
401 400 python python helper.py
EOF
)"

check 'Claude descendant detected despite shell root' claude \
  "$(ap_backend_from_processes 100 <<<"$processes")"
check 'Codex node launcher detected at pane root' codex \
  "$(ap_backend_from_processes 200 <<<"$processes")"
check 'nearest Copilot wins over nested Claude reviewer' copilot \
  "$(ap_backend_from_processes 300 <<<"$processes")"
check 'unrecognized process tree fails closed' '' \
  "$(ap_backend_from_processes 400 <<<"$processes" 2>/dev/null || true)"

claude_empty="$(
  cat <<'EOF'
────────────────────────────────────────────────────────
❯ 
────────────────────────────────────────────────────────
  Opus 5 | Ctx: 43% | 7d: 57%                     /rc
  ⏵⏵ bypass permissions on (shift+tab to cycle)
EOF
)"
check 'Claude empty prompt parsed' '' \
  "$(cl_input_region <<<"$claude_empty")"
check 'Claude loaded footer detected' yes \
  "$(cl_is_loaded <<<"$claude_empty" && echo yes || echo no)"

claude_typed="${claude_empty/❯ /❯ check mailbox; skip if empty [mb:abc]}"
check 'Claude typed prompt parsed' 'checkmailbox;skipifempty[mb:abc]' \
  "$(cl_input_signature <<<"$(cl_input_region <<<"$claude_typed")")"

esc=$'\033'
codex_empty="$(
  printf '%s\n' \
    "${esc}[1m${esc}[39m›${esc}[0m ${esc}[2mImprove documentation in @filename" \
    "" \
    "  ${esc}[38;2;246;226;183mgpt-5.6-luna medium${esc}[2m${esc}[39m · ~/workspace"
)"
check 'Codex dim placeholder is empty' '' \
  "$(cx_input_region <<<"$codex_empty")"
check 'Codex styled prompt is loaded' yes \
  "$(cx_is_loaded <<<"$codex_empty" && echo yes || echo no)"

codex_typed="$(
  printf '%s\n' \
    "${esc}[1m${esc}[39m›${esc}[0m check mailbox; skip if empty [mb:abc]" \
    "" \
    "  ${esc}[38;2;246;226;183mgpt-5.6-luna medium${esc}[39m · ~/workspace"
)"
check 'Codex typed prompt parsed' 'checkmailbox;skipifempty[mb:abc]' \
  "$(cx_input_signature <<<"$(cx_input_region <<<"$codex_typed")")"
check 'shell text is not a Codex prompt' no \
  "$(cx_is_loaded <<<'$ codex --help' && echo yes || echo no)"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

