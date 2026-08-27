#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/mailbox-poke.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mailbox-poke-test.XXXXXX")"
FAKE_BIN="$ROOT/bin"
MAILBOX_ROOT="$ROOT/mailbox"
trap '/bin/rm -rf -- "$ROOT"' EXIT
mkdir -p "$FAKE_BIN" "$MAILBOX_ROOT"

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
prompt=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--prompt-file" ]; then
    prompt="$(cat "$2")"
    break
  fi
  shift
done
printf '%s' "$prompt" >>"$FAKE_NODE_PROMPTS"
if [ "${FAKE_NODE_STATUS:-0}" -eq 0 ]; then
  printf '{"status":"completed","result":{"delivery":"%s"}}\n' \
    "${FAKE_NODE_DELIVERY:-idle}"
fi
exit "${FAKE_NODE_STATUS:-0}"
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
        printf '❯ %s\n────────────────\nCtx: 10%%\n' "$prompt"
        ;;
      submitted)
        printf '● %s\n❯ \n────────────────\nCtx: 10%%\n' "$prompt"
        ;;
      *)
        printf '❯ \n────────────────\nCtx: 10%%\n'
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
export FAKE_NODE_CALLS="$ROOT/node-calls"
export FAKE_NODE_PROMPTS="$ROOT/node-prompts"
export FAKE_TMUX_CALLS="$ROOT/tmux-calls"
export FAKE_PANE_STATE="$ROOT/pane-state"
export FAKE_TYPED_PROMPT="$ROOT/typed-prompt"
: >"$FAKE_NODE_CALLS"
: >"$FAKE_NODE_PROMPTS"
: >"$FAKE_TMUX_CALLS"

FAKE_RECIPIENT=hotel
FAKE_BACKEND=copilot
FAKE_NODE_STATUS=0
FAKE_NODE_DELIVERY=idle
export FAKE_RECIPIENT FAKE_BACKEND FAKE_NODE_STATUS FAKE_NODE_DELIVERY
make_mail hotel 20260827T000000Z-sdkproof
output="$("$SCRIPT" hotel)"
grep -Fq 'poked: hotel (SDK idle delivery verified)' <<<"$output" ||
  fail "Copilot SDK success was not reported"
grep -Fq 'send --target-tmux hotel --prompt-file' "$FAKE_NODE_CALLS" ||
  fail "Copilot request did not target the tmux alias"
grep -Fq -- '--mode immediate --dedupe-key mailbox:hotel:20260827T000000Z-sdkproof --timeout 15' \
  "$FAKE_NODE_CALLS" || fail "Copilot request options changed"
[ "$(cat "$FAKE_NODE_PROMPTS")" = \
  'check mailbox; skip if empty [mb:sdkproof]' ] ||
  fail "Copilot mailbox prompt changed"
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "Copilot mailbox path used tmux send-keys"
[ "$(cat "$MAILBOX_ROOT/hotel/.last-poked-id")" = \
  20260827T000000Z-sdkproof ] ||
  fail "Copilot SDK success did not advance the watermark"

FAKE_RECIPIENT=lima
FAKE_BACKEND=copilot
FAKE_NODE_STATUS=2
export FAKE_RECIPIENT FAKE_BACKEND FAKE_NODE_STATUS
make_mail lima 20260827T000001Z-sdkfail
if "$SCRIPT" lima >"$ROOT/sdk-failure.out" 2>&1; then
  fail "failed Copilot SDK request was reported as delivered"
fi
grep -Fq "did not acknowledge the SDK wakeup" "$ROOT/sdk-failure.out" ||
  fail "failed Copilot SDK request was not surfaced"
[ ! -e "$MAILBOX_ROOT/lima/.last-poked-id" ] ||
  fail "failed Copilot SDK request advanced the watermark"
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "failed Copilot SDK request fell back to tmux"

FAKE_RECIPIENT=november
FAKE_BACKEND=copilot
FAKE_NODE_STATUS=0
FAKE_NODE_DELIVERY=steering
export FAKE_RECIPIENT FAKE_BACKEND FAKE_NODE_STATUS FAKE_NODE_DELIVERY
make_mail november 20260827T000002Z-nonidle
if "$SCRIPT" november >"$ROOT/sdk-nonidle.out" 2>&1; then
  fail "non-idle Copilot SDK delivery was reported as verified"
fi
grep -Fq 'received the SDK wakeup outside an idle boundary' "$ROOT/sdk-nonidle.out" ||
  fail "non-idle Copilot SDK delivery was not surfaced"
[ ! -e "$MAILBOX_ROOT/november/.last-poked-id" ] ||
  fail "non-idle Copilot SDK delivery advanced the watermark"
[ ! -s "$FAKE_TMUX_CALLS" ] ||
  fail "non-idle Copilot SDK delivery fell back to tmux"

FAKE_RECIPIENT=claude-kilo
FAKE_BACKEND=claude
FAKE_NODE_STATUS=0
FAKE_NODE_DELIVERY=idle
export FAKE_RECIPIENT FAKE_BACKEND FAKE_NODE_STATUS
printf empty >"$FAKE_PANE_STATE"
: >"$FAKE_TYPED_PROMPT"
make_mail claude-kilo 20260827T000002Z-claudeproof
node_call_count="$(wc -l <"$FAKE_NODE_CALLS" | tr -d '[:space:]')"
output="$("$SCRIPT" claude-kilo)"
grep -Fq 'poked: claude-kilo (submission observed)' <<<"$output" ||
  fail "Claude fallback submission was not verified"
[ "$(wc -l <"$FAKE_NODE_CALLS" | tr -d '[:space:]')" = "$node_call_count" ] ||
  fail "Claude fallback called the Copilot SDK helper"
grep -Fq -- '-l -- check mailbox; skip if empty [mb:claudeproof]' \
  "$FAKE_TMUX_CALLS" || fail "Claude fallback did not type the mailbox prompt"
grep -Fq 'send-keys -t %1 Enter' "$FAKE_TMUX_CALLS" ||
  grep -Fq -- '-t %1 Enter' "$FAKE_TMUX_CALLS" ||
  fail "Claude fallback did not submit the verified prompt"
[ "$(cat "$MAILBOX_ROOT/claude-kilo/.last-poked-id")" = \
  20260827T000002Z-claudeproof ] ||
  fail "Claude fallback did not advance the watermark"

tmux_call_count="$(wc -l <"$FAKE_TMUX_CALLS" | tr -d '[:space:]')"
"$SCRIPT" claude-kilo
[ "$(wc -l <"$FAKE_TMUX_CALLS" | tr -d '[:space:]')" = "$tmux_call_count" ] ||
  fail "watermark dedupe repeated a Claude wakeup"

bash -n "$SCRIPT"
echo "mailbox-poke tests: pass"
