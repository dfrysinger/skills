#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/mailbox-poke.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mailbox-poke-test.XXXXXX")"
FAKE_BIN="$ROOT/bin"
MAILBOX_ROOT="$ROOT/mailbox"
MAILBOX_STATE_ROOT="$ROOT/mailbox-state"
trap '/bin/rm -rf -- "$ROOT"' EXIT
mkdir -p "$FAKE_BIN" "$MAILBOX_ROOT" "$MAILBOX_STATE_ROOT"

fail() {
  echo "mailbox-poke test: $*" >&2
  exit 1
}

cat >"$FAKE_BIN/ps" <<'EOF'
#!/usr/bin/env bash
printf '100 1 zsh zsh\n'
printf '101 100 %s %s\n' "$FAKE_BACKEND" "$FAKE_BACKEND"
EOF
chmod +x "$FAKE_BIN/ps"

cat >"$FAKE_BIN/node" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_NODE_CALLS"
if [[ "$1" == "-e" ]]; then
  exit "${FAKE_IDENTITY_VALID:-0}"
fi
if [[ "$1" == */mailbox.mjs && "$2" == poke ]]; then
  recipient="$3"
  case "${FAKE_MAILBOX_NODE_STATUS:-0}" in
    0) printf 'poked: %s (SDK wakeup accepted)\n' "$recipient" ;;
    3) printf "UNVERIFIED: '%s' did not acknowledge the SDK wakeup; the mail remains queued.\n" "$recipient" >&2 ;;
    4) printf "UNAVAILABLE: no active Copilot session named '%s'.\n" "$recipient" >&2 ;;
    5) printf 'poke: deferred to mailbox watcher on other-machine\n' ;;
  esac
  exit "${FAKE_MAILBOX_NODE_STATUS:-0}"
fi
exit 99
EOF
chmod +x "$FAKE_BIN/node"

cat >"$FAKE_BIN/tmux" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  list-panes)
    printf '%s\t%%1\t1\t1\n' "$FAKE_RECIPIENT"
    ;;
  display-message)
    format="${@: -1}"
    case "$format" in
      '#{session_name}') printf '%s\n' "$FAKE_RECIPIENT" ;;
      '#{pane_pid}') printf '100\n' ;;
      '#{pane_current_command}') printf '%s\n' "$FAKE_BACKEND" ;;
      *) exit 1 ;;
    esac
    ;;
  capture-pane)
    state="$(cat "$FAKE_PANE_STATE" 2>/dev/null || printf empty)"
    prompt="$(cat "$FAKE_TYPED_PROMPT" 2>/dev/null || true)"
    case "$state" in
      typed)
        printf 'Session: 1 AIC used\n❯ %s\n────────────────\nCtx: 10%%\n' "$prompt"
        ;;
      submitted)
        printf 'Session: 1 AIC used\n● %s\n❯ \n────────────────\nCtx: 10%%\n' "$prompt"
        ;;
      *)
        printf 'Session: 1 AIC used\n❯ \n────────────────\nCtx: 10%%\n'
        ;;
    esac
    ;;
  send-keys)
    printf '%s\n' "$*" >>"$FAKE_TMUX_CALLS"
    if printf '%s\n' "$*" | grep -q -- ' -l -- '; then
      printf '%s' "${@: -1}" >"$FAKE_TYPED_PROMPT"
      printf typed >"$FAKE_PANE_STATE"
    else
      printf submitted >"$FAKE_PANE_STATE"
    fi
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$FAKE_BIN/tmux"

make_mail() {
  local recipient="$1"
  local id="$2"
  mkdir -p "$MAILBOX_ROOT/$recipient/pending"
  printf '{}\n' >"$MAILBOX_ROOT/$recipient/pending/$id.json"
}

export PATH="$FAKE_BIN:$PATH"
export MAILBOX_ROOT
export MAILBOX_STATE_ROOT
export FAKE_NODE_CALLS="$ROOT/node-calls"
export FAKE_TMUX_CALLS="$ROOT/tmux-calls"
export FAKE_PANE_STATE="$ROOT/pane-state"
export FAKE_TYPED_PROMPT="$ROOT/typed-prompt"
: >"$FAKE_NODE_CALLS"
: >"$FAKE_TMUX_CALLS"

FAKE_RECIPIENT=hotel
FAKE_BACKEND=copilot
FAKE_MAILBOX_NODE_STATUS=0
export FAKE_RECIPIENT FAKE_BACKEND FAKE_MAILBOX_NODE_STATUS
make_mail hotel 20260827T000000Z-sdkproof
output="$("$SCRIPT" hotel)"
grep -Fq 'poked: hotel (SDK wakeup accepted)' <<<"$output" ||
  fail "Copilot SDK success was not reported"
grep -Fq 'mailbox.mjs poke hotel' "$FAKE_NODE_CALLS" ||
  fail "Copilot path did not use the portable Node mailbox"
grep -Fq -- '--mode immediate' "$SCRIPT" ||
  fail "Copilot path did not request immediate SDK delivery"
grep -Fq 'SDK wakeup accepted' "$SCRIPT_DIR/mailbox.mjs" ||
  fail "portable Node mailbox does not report SDK acceptance"
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "Copilot mailbox path used tmux send-keys"

FAKE_RECIPIENT=lima
FAKE_BACKEND=copilot
FAKE_MAILBOX_NODE_STATUS=3
export FAKE_RECIPIENT FAKE_BACKEND FAKE_MAILBOX_NODE_STATUS
make_mail lima 20260827T000001Z-sdkfail
if "$SCRIPT" lima >"$ROOT/sdk-failure.out" 2>&1; then
  fail "failed Copilot SDK request was reported as delivered"
fi
grep -Fq "did not acknowledge the SDK wakeup" "$ROOT/sdk-failure.out" ||
  fail "failed Copilot SDK request was not surfaced"
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "failed Copilot SDK request fell back to tmux"

FAKE_RECIPIENT=india
FAKE_BACKEND=copilot
FAKE_MAILBOX_NODE_STATUS=4
export FAKE_RECIPIENT FAKE_BACKEND FAKE_MAILBOX_NODE_STATUS
make_mail india 20260827T000001Z-noheartbeat
if "$SCRIPT" india >"$ROOT/no-heartbeat.out" 2>&1; then
  fail "missing Copilot heartbeat was reported as delivered"
fi
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "missing Copilot heartbeat bypassed the definitive receipt gate"

FAKE_RECIPIENT=lima
FAKE_BACKEND=copilot
export FAKE_RECIPIENT FAKE_BACKEND
printf empty >"$FAKE_PANE_STATE"
: >"$FAKE_TYPED_PROMPT"
FAKE_IDENTITY_VALID=0
export FAKE_IDENTITY_VALID
output="$("$SCRIPT" lima --terminal-only \
  --expected-session-id lima-session \
  --expected-generation lima-generation \
  --expected-host-pid 101)"
grep -Fq 'poked: lima (submission observed)' <<<"$output" ||
  fail "eligible Copilot terminal fallback was not verified"
grep -Fq -- '-l -- check mailbox; skip if empty [mb:sdkfail]' \
  "$FAKE_TMUX_CALLS" || fail "Copilot terminal fallback did not type the mailbox prompt"
: >"$FAKE_TMUX_CALLS"

FAKE_IDENTITY_VALID=1
export FAKE_IDENTITY_VALID
printf empty >"$FAKE_PANE_STATE"
make_mail lima 20260827T000002Z-staleidentity
if "$SCRIPT" lima --terminal-only \
  --expected-session-id old-session \
  --expected-generation old-generation \
  --expected-host-pid 101 >"$ROOT/stale-identity.out" 2>&1; then
  fail "stale Copilot fallback identity was reported as delivered"
fi
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "stale Copilot fallback identity sent tmux keys"
FAKE_IDENTITY_VALID=0
export FAKE_IDENTITY_VALID

FAKE_RECIPIENT=hotel
FAKE_BACKEND=copilot
FAKE_MAILBOX_NODE_STATUS=5
export FAKE_RECIPIENT FAKE_BACKEND FAKE_MAILBOX_NODE_STATUS
make_mail hotel@other-machine 20260827T000002Z-remoteproof
if "$SCRIPT" hotel@other-machine >"$ROOT/remote-pending.out" 2>&1; then
  fail "remote qualified poke was reported as locally delivered"
else
  remote_status=$?
fi
[ "$remote_status" -eq 5 ] ||
  fail "remote qualified poke did not preserve deferred status"
grep -Fq 'deferred to mailbox watcher on other-machine' "$ROOT/remote-pending.out" ||
  fail "remote qualified poke did not report deferral"
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "remote qualified poke fell back to tmux"

FAKE_RECIPIENT=claude-kilo
FAKE_BACKEND=claude
FAKE_MAILBOX_NODE_STATUS=4
export FAKE_RECIPIENT FAKE_BACKEND FAKE_MAILBOX_NODE_STATUS
printf empty >"$FAKE_PANE_STATE"
: >"$FAKE_TYPED_PROMPT"
make_mail claude-kilo 20260827T000002Z-claudeproof
node_call_count="$(wc -l <"$FAKE_NODE_CALLS" | tr -d '[:space:]')"
output="$("$SCRIPT" claude-kilo)"
grep -Fq 'poked: claude-kilo (submission observed)' <<<"$output" ||
  fail "Claude fallback submission was not verified"
[ "$(wc -l <"$FAKE_NODE_CALLS" | tr -d '[:space:]')" = "$((node_call_count + 1))" ] ||
  fail "Claude fallback made an unexpected Node call"
grep -Fq -- '-l -- check mailbox; skip if empty [mb:claudeproof]' \
  "$FAKE_TMUX_CALLS" || fail "Claude fallback did not type the mailbox prompt"
grep -Fq 'send-keys -t %1 Enter' "$FAKE_TMUX_CALLS" ||
  grep -Fq -- '-t %1 Enter' "$FAKE_TMUX_CALLS" ||
  fail "Claude fallback did not submit the verified prompt"
[ "$(cat "$MAILBOX_STATE_ROOT/watermarks/claude-kilo.txt")" = \
  20260827T000002Z-claudeproof ] ||
  fail "Claude fallback did not advance the watermark"

tmux_call_count="$(wc -l <"$FAKE_TMUX_CALLS" | tr -d '[:space:]')"
"$SCRIPT" claude-kilo
[ "$(wc -l <"$FAKE_TMUX_CALLS" | tr -d '[:space:]')" = "$tmux_call_count" ] ||
  fail "watermark dedupe repeated a Claude wakeup"

FAKE_RECIPIENT=hotel
FAKE_BACKEND=claude
FAKE_MAILBOX_NODE_STATUS=4
export FAKE_RECIPIENT FAKE_BACKEND FAKE_MAILBOX_NODE_STATUS
printf empty >"$FAKE_PANE_STATE"
: >"$FAKE_TYPED_PROMPT"
make_mail hotel@surface-pro 20260827T000003Z-qualifiedproof
output="$("$SCRIPT" hotel@surface-pro)"
grep -Fq 'poked: hotel@surface-pro (submission observed)' <<<"$output" ||
  fail "qualified Claude fallback submission was not verified"
grep -Fq -- '-l -- check mailbox; skip if empty [mb:qualifiedproof]' \
  "$FAKE_TMUX_CALLS" || fail "qualified fallback did not type the mailbox prompt"
[ "$(cat "$MAILBOX_STATE_ROOT/watermarks/hotel@surface-pro.txt")" = \
  20260827T000003Z-qualifiedproof ] ||
  fail "qualified fallback did not retain the full-address watermark"

bash -n "$SCRIPT"
echo "mailbox-poke tests: pass"
