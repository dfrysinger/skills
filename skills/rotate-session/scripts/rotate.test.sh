#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rotate.sh"
HELPER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rotate-after-turn.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/rotate-session-test.XXXXXX")"
trap '/bin/rm -rf -- "$ROOT"' EXIT

mkdir -p "$ROOT/home/.copilot/session-state" "$ROOT/tmp" "$ROOT/bin"

cat >"$ROOT/bin/tmux" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
command="$1"
shift
last=""
for value in "$@"; do last="$value"; done
case "$command" in
  display-message)
    case "$last" in
      '#{session_name}') printf '%s\n' "${MOCK_TMUX_SESSION_NAME:-sierra}" ;;
      '#{pane_current_path}') printf '%s\n' "$MOCK_TMUX_CWD" ;;
      *) exit 1 ;;
    esac
    ;;
  new-session)
    /bin/bash -c "$last" &
    printf '%s\n' "$!" >"$MOCK_TMUX_PID_FILE"
    ;;
  kill-session)
    if [ -r "$MOCK_TMUX_PID_FILE" ]; then
      /bin/kill "$(/bin/cat "$MOCK_TMUX_PID_FILE")" 2>/dev/null || true
    fi
    ;;
  select-pane)
    printf '%s\n' "$*" >>"$MOCK_TMUX_CALLS"
    ;;
  respawn-pane)
    if [ -n "${MOCK_TMUX_RACE_EVENTS:-}" ]; then
      printf '%s\n' \
        '{"type":"user.message","data":{"content":"boundary work","delivery":"idle"}}' \
        >>"$MOCK_TMUX_RACE_EVENTS"
    fi
    /bin/bash "$last" &
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$ROOT/bin/tmux"

cat >"$ROOT/bin/ps" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-ww" ] && [ "${2:-}" = "-o" ] &&
  [ "${3:-}" = "command=" ]; then
  printf '%s\n' "${MOCK_PS_COMMAND:-$MOCK_COPILOT_BIN --remote --yolo --session-id test-session}"
  exit 0
fi
exec /bin/ps "$@"
EOF
chmod +x "$ROOT/bin/ps"

cat >"$ROOT/fake-copilot.mjs" <<'EOF'
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const value = (name) => {
  const equals = args.find((arg) => arg.startsWith(`${name}=`));
  if (equals) return equals.slice(name.length + 1);
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};
const sessionId = value("--session-id");
const prompt = value("--interactive");
const sessionName = value("--name");
if (!sessionId || !prompt || !sessionName) process.exit(2);
const state = join(process.env.HOME, ".copilot", "session-state", sessionId);
mkdirSync(state, { recursive: true });
writeFileSync(
  join(state, "events.jsonl"),
  `${JSON.stringify({
    type: "user.message",
    data: { content: prompt, delivery: "idle" },
  })}\n${
    process.env.MOCK_NEW_SESSION_EXTRA_MESSAGE
      ? `${JSON.stringify({
          type: "user.message",
          data: { content: "boundary work", delivery: "queued" },
        })}\n`
      : ""
  }`,
);
EOF
cat >"$ROOT/bin/copilot" <<EOF
#!/bin/sh
exec node "$ROOT/fake-copilot.mjs" "\$@"
EOF
chmod +x "$ROOT/bin/copilot"
export MOCK_COPILOT_BIN="$ROOT/bin/copilot"

wait_for_result() {
  local log="$1"
  local _
  for _ in $(/usr/bin/seq 1 200); do
    grep -q 'RESULT:' "$log" 2>/dev/null && return 0
    /bin/sleep 0.02
  done
  return 1
}

start_rotation() {
  local old="$1"
  local label="$2"
  local prompt="${3:-continue retired session $old}"
  local race_events="${4:-}"
  local extra_new_message="${5:-}"
  local setup_user_message="${6:-}"
  local inbox_inflight="${7:-}"
  local state="$ROOT/home/.copilot/session-state/$old"
  local input="$ROOT/$label-input.txt"
  local log="$ROOT/$label.log"

  mkdir -p "$state"
  printf '%s\n' '{"type":"assistant.turn_start","data":{}}' >"$state/events.jsonl"
  if [ -n "$setup_user_message" ]; then
    printf '%s\n' \
      '{"type":"user.message","data":{"content":"setup work","delivery":"steering"}}' \
      >>"$state/events.jsonl"
  fi
  touch "$state/inuse.$$.lock"
  if [ -n "$inbox_inflight" ]; then
    mkdir -p "$ROOT/home/.copilot/session-inbox/processing"
    printf '{"id":"inflight","target":{"sessionId":"%s"}}\n' "$old" \
      >"$ROOT/home/.copilot/session-inbox/processing/inflight-$old.json"
  fi
  printf '%s' "$prompt" >"$input"

  HOME="$ROOT/home" TMPDIR="$ROOT/tmp" PATH="$ROOT/bin:$PATH" \
    ROTATE_STATE_ROOT="$ROOT/home/.copilot/session-state" \
    ROTATE_LOG="$log" ROTATE_TMUX_BIN="$ROOT/bin/tmux" \
    MOCK_TMUX_CWD="$ROOT" MOCK_TMUX_RACE_EVENTS="$race_events" \
    MOCK_NEW_SESSION_EXTRA_MESSAGE="$extra_new_message" \
    MOCK_TMUX_PID_FILE="$ROOT/$label-helper.pid" \
    MOCK_TMUX_CALLS="$ROOT/$label-tmux.calls" TMUX_PANE="%test" \
    "$SCRIPT" "$old" "$input" --consume-prompt >"$ROOT/$label.out"

  [ ! -e "$input" ]
  printf '%s\t%s\n' "$state" "$log"
}

bash -n "$SCRIPT" "$HELPER"

IFS=$'\t' read -r success_state success_log < <(
  start_rotation old-success success
)
grep -Fq 'rotation requested' "$ROOT/success.out"
printf '%s\n' '{"type":"assistant.turn_end","data":{}}' >>"$success_state/events.jsonl"
wait_for_result "$success_log"
grep -Fq 'transport: tmux process replacement from pane %test' "$success_log"
grep -Fq 'seeded through tmux process replacement' "$success_log"
grep -Fq -- '-d -t %test' "$ROOT/success-tmux.calls"
grep -Fq -- '-e -t %test' "$ROOT/success-tmux.calls"
success_new="$(sed -n 's/^replacement session: //p' "$success_log" | tail -1)"
grep -Fq 'continue retired session old-success' \
  "$ROOT/home/.copilot/session-state/$success_new/events.jsonl"
! find "$ROOT/tmp" -maxdepth 1 -name 'copilot-rotate-recovery-old-success.*' |
  grep -q .

IFS=$'\t' read -r cancel_state cancel_log < <(
  start_rotation old-cancel cancel
)
printf '%s\n' \
  '{"type":"assistant.turn_end","data":{}}' \
  '{"type":"user.message","data":{"content":"new work","delivery":"idle"}}' \
  >>"$cancel_state/events.jsonl"
wait_for_result "$cancel_log"
grep -Fq 'rotation cancelled because new user activity arrived' "$cancel_log"
cancel_recovery="$(
  sed -n 's/^recovery snapshot: \([^ ]*\).*/\1/p' "$cancel_log" | tail -1
)"
[ -f "$cancel_recovery" ]

IFS=$'\t' read -r setup_state setup_log < <(
  start_rotation old-setup-activity setup-activity \
    'continue retired session old-setup-activity' "" "" "yes"
)
wait_for_result "$setup_log"
grep -Fq 'rotation cancelled because new user activity arrived' "$setup_log"
setup_recovery="$(
  sed -n 's/^recovery snapshot: \([^ ]*\).*/\1/p' "$setup_log" | tail -1
)"
[ -f "$setup_recovery" ]

IFS=$'\t' read -r inbox_state inbox_log < <(
  start_rotation old-inbox-activity inbox-activity \
    'continue retired session old-inbox-activity' "" "" "" "yes"
)
printf '%s\n' '{"type":"assistant.turn_end","data":{}}' \
  >>"$inbox_state/events.jsonl"
wait_for_result "$inbox_log"
grep -Fq 'session-inbox work is in flight' "$inbox_log"
inbox_recovery="$(
  sed -n 's/^recovery snapshot: \([^ ]*\).*/\1/p' "$inbox_log" | tail -1
)"
[ -f "$inbox_recovery" ]
[ ! -e "$inbox_state/rotation.barrier" ]

concurrent_state="$ROOT/home/.copilot/session-state/old-concurrent"
IFS=$'\t' read -r concurrent_state concurrent_log < <(
  start_rotation old-concurrent concurrent-first
)
concurrent_input="$ROOT/concurrent-second-input.txt"
printf 'continue old-concurrent again' >"$concurrent_input"
if HOME="$ROOT/home" TMPDIR="$ROOT/tmp" PATH="$ROOT/bin:$PATH" \
  ROTATE_STATE_ROOT="$ROOT/home/.copilot/session-state" \
  ROTATE_LOG="$ROOT/concurrent-second.log" ROTATE_TMUX_BIN="$ROOT/bin/tmux" \
  MOCK_TMUX_CWD="$ROOT" MOCK_TMUX_PID_FILE="$ROOT/concurrent-second-helper.pid" \
  TMUX_PANE="%test" \
  "$SCRIPT" old-concurrent "$concurrent_input" --consume-prompt \
  >"$ROOT/concurrent-second.out" 2>&1; then
  exit 1
fi
grep -Fq 'another rotation is pending or the detached verifier could not acquire its lock' \
  "$ROOT/concurrent-second.out"
[ -f "$concurrent_input" ]
printf '%s\n' '{"type":"assistant.turn_end","data":{}}' \
  >>"$concurrent_state/events.jsonl"
wait_for_result "$concurrent_log"
[ -f "$concurrent_state/rotation.lock" ]

stale_state="$ROOT/home/.copilot/session-state/old-stale"
mkdir -p "$stale_state"
printf '%s\n' 'stale lock file without a live kernel lock' \
  >"$stale_state/rotation.lock"
IFS=$'\t' read -r stale_state stale_log < <(
  start_rotation old-stale stale
)
printf '%s\n' '{"type":"assistant.turn_end","data":{}}' \
  >>"$stale_state/events.jsonl"
wait_for_result "$stale_log"
grep -Fq 'seeded through tmux process replacement' "$stale_log"
[ -f "$stale_state/rotation.barrier" ]

IFS=$'\t' read -r malformed_state malformed_log < <(
  start_rotation old-malformed malformed
)
printf '%s\n' '{"type":not-json}' >>"$malformed_state/events.jsonl"
wait_for_result "$malformed_log"
grep -Fq 'rotation verifier failed unexpectedly' "$malformed_log"
malformed_recovery="$(
  sed -n 's/^recovery snapshot: \([^ ]*\).*/\1/p' "$malformed_log" | tail -1
)"
[ -f "$malformed_recovery" ]
[ -f "$malformed_state/rotation.lock" ]

race_state="$ROOT/home/.copilot/session-state/old-race"
IFS=$'\t' read -r race_state race_log < <(
  start_rotation old-race race 'continue retired session old-race' "$race_state/events.jsonl"
)
printf '%s\n' '{"type":"assistant.turn_end","data":{}}' >>"$race_state/events.jsonl"
wait_for_result "$race_log"
grep -Fq 'new user activity was recorded in the retired session' "$race_log"
race_recovery="$(
  sed -n 's/^recovery snapshot: \([^ ]*\).*/\1/p' "$race_log" | tail -1
)"
[ -f "$race_recovery" ]

IFS=$'\t' read -r new_race_state new_race_log < <(
  start_rotation old-new-race new-race \
    'continue retired session old-new-race' "" "yes"
)
printf '%s\n' '{"type":"assistant.turn_end","data":{}}' \
  >>"$new_race_state/events.jsonl"
wait_for_result "$new_race_log"
grep -Fq 'seed or boundary activity was not exact' "$new_race_log"
new_race_recovery="$(
  sed -n 's/^recovery snapshot: \([^ ]*\).*/\1/p' "$new_race_log" | tail -1
)"
[ -f "$new_race_recovery" ]

invalid_state="$ROOT/home/.copilot/session-state/old-invalid"
invalid_input="$ROOT/invalid-input.txt"
mkdir -p "$invalid_state"
printf '%s\n' '{"type":"assistant.turn_start","data":{}}' >"$invalid_state/events.jsonl"
touch "$invalid_state/inuse.$$.lock"
printf 'wrong session' >"$invalid_input"
if HOME="$ROOT/home" PATH="$ROOT/bin:$PATH" ROTATE_TMUX_BIN="$ROOT/bin/tmux" \
  ROTATE_STATE_ROOT="$ROOT/home/.copilot/session-state" \
  MOCK_TMUX_CWD="$ROOT" TMUX_PANE="%test" \
  "$SCRIPT" old-invalid "$invalid_input" --consume-prompt \
  >"$ROOT/invalid.out" 2>&1; then
  exit 1
fi
grep -Fq 'prompt does not name expected session old-invalid' "$ROOT/invalid.out"
[ -f "$invalid_input" ]

unsupported_input="$ROOT/unsupported-input.txt"
mkdir -p "$ROOT/home/.copilot/session-state/old-unsupported"
printf 'continue old-unsupported' >"$unsupported_input"
if HOME="$ROOT/home" ROTATE_STATE_ROOT="$ROOT/home/.copilot/session-state" \
  TMUX_PANE= "$SCRIPT" old-unsupported "$unsupported_input" \
  >"$ROOT/unsupported.out" 2>&1; then
  exit 1
fi
grep -Fq 'automated rotation requires the current Copilot session to run in tmux' \
  "$ROOT/unsupported.out"
[ -f "$unsupported_input" ]

log_input="$ROOT/log-input.txt"
log_state="$ROOT/home/.copilot/session-state/old-log"
mkdir -p "$log_state"
printf '%s\n' '{"type":"assistant.turn_start","data":{}}' >"$log_state/events.jsonl"
touch "$log_state/inuse.$$.lock"
printf 'continue old-log' >"$log_input"
if HOME="$ROOT/home" PATH="$ROOT/bin:$PATH" ROTATE_TMUX_BIN="$ROOT/bin/tmux" \
  ROTATE_STATE_ROOT="$ROOT/home/.copilot/session-state" \
  ROTATE_LOG="$ROOT/missing/rotate.log" MOCK_TMUX_CWD="$ROOT" TMUX_PANE="%test" \
  "$SCRIPT" old-log "$log_input" --consume-prompt >"$ROOT/log.out" 2>&1; then
  exit 1
fi
grep -Fq 'could not open rotation log; original prompt retained' "$ROOT/log.out"
[ -f "$log_input" ]

options_input="$ROOT/options-input.txt"
options_state="$ROOT/home/.copilot/session-state/old-options"
mkdir -p "$options_state"
printf '%s\n' '{"type":"assistant.turn_start","data":{}}' \
  >"$options_state/events.jsonl"
touch "$options_state/inuse.$$.lock"
printf 'continue old-options' >"$options_input"
if HOME="$ROOT/home" PATH="$ROOT/bin:$PATH" ROTATE_TMUX_BIN="$ROOT/bin/tmux" \
  ROTATE_STATE_ROOT="$ROOT/home/.copilot/session-state" \
  MOCK_PS_COMMAND="$ROOT/bin/copilot --remote --deny-tool shell --session-id old-options" \
  MOCK_TMUX_CWD="$ROOT" TMUX_PANE="%test" \
  "$SCRIPT" old-options "$options_input" --consume-prompt \
  >"$ROOT/options.out" 2>&1; then
  exit 1
fi
grep -Fq 'current Copilot launch option cannot be preserved safely: --deny-tool' \
  "$ROOT/options.out"
[ -f "$options_input" ]

! grep -Eq 'send-keys|capture-pane|paste-buffer|load-buffer' "$SCRIPT" "$HELPER"
echo "rotate-session tests: pass"
