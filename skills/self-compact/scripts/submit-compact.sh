#!/usr/bin/env bash
# Queue a steered /compact and arm a watcher that resumes after it lands.

set -euo pipefail

PANE="${TMUX_PANE:?TMUX_PANE is not set; run inside tmux}"
TMUX_BIN="$(command -v tmux)" || {
  echo "submit-compact.sh: tmux is unavailable; compact not submitted" >&2
  exit 1
}
CONTINUATION="proceed"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION_STATE_DIR="${SELF_COMPACT_SESSION_STATE_DIR:-$HOME/.copilot/session-state}"
# shellcheck source=skills/self-compact/scripts/input-recovery.sh
source "$SCRIPT_DIR/input-recovery.sh"

if [ "${1:-}" = "--continuation" ]; then
  [ $# -ge 3 ] || {
    echo "usage: submit-compact.sh [--continuation '<prompt>'] '<steer>'" >&2
    exit 2
  }
  CONTINUATION="$2"
  shift 2
fi

STEER="${*:-}"

if [ -z "$STEER" ]; then
  echo "usage: submit-compact.sh [--continuation '<prompt>'] '<steer>'" >&2
  exit 2
fi

validate_input() {
  local value_name="$1"
  local value="$2"
  case "$value" in
    *$'\n'*)
      echo "submit-compact.sh: ${value_name} must be a single line" >&2
      exit 2
      ;;
  esac
  if ! sc_ascii_printable "$value"; then
    echo "submit-compact.sh: ${value_name} must contain only printable ASCII" >&2
    exit 2
  fi
}

validate_input "steer" "$STEER"
validate_input "continuation" "$CONTINUATION"

RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EPOCH_SECONDS="$(date -u +%s)"
case "$EPOCH_SECONDS:$$" in
  *[!0-9:]*|:*|*::*|*:)
    echo "submit-compact.sh: could not create a compact run marker" >&2
    exit 1
    ;;
esac
[ "$EPOCH_SECONDS" -le 4294967295 ] && [ "$$" -le 1048575 ] || {
  echo "submit-compact.sh: compact run marker exceeds its supported range" >&2
  exit 1
}
printf -v EPOCH_HEX '%08x' "$EPOCH_SECONDS"
printf -v PID_HEX '%05x' "$$"
RUN_ID="$RUN_STAMP-$$"
MARKER="SCM:$EPOCH_HEX-$PID_HEX"
COMMAND="/compact $STEER Keep $MARKER"

SC_TMUX_BIN="$TMUX_BIN"
SC_PANE="$PANE"
ROW_LIMIT="$(sc_pane_one_row_limit)" || {
  echo "submit-compact.sh: could not read pane width; compact not submitted" >&2
  exit 1
}
if ! sc_one_row_command_fits "$COMMAND" "$ROW_LIMIT"; then
  echo "submit-compact.sh: marked compact command is ${#COMMAND} columns, but this pane safely allows $ROW_LIMIT; shorten the steer or reference a shorter durable artifact" >&2
  exit 2
fi
if ! sc_one_row_command_fits "$CONTINUATION" "$ROW_LIMIT"; then
  echo "submit-compact.sh: continuation is ${#CONTINUATION} columns, but this pane safely allows $ROW_LIMIT; shorten the continuation or reference a shorter durable artifact" >&2
  exit 2
fi

if ! sc_input_init "$TMUX_BIN" "$PANE"; then
  echo "submit-compact.sh: could not verify a UTF-8 locale; compact not submitted" >&2
  exit 1
fi

resolve_workspace() {
  local pane_cwd pane_pid ws this_cwd lock lock_pid parent
  local selected=""

  pane_cwd="$(tmux display-message -p -t "$PANE" '#{pane_current_path}' 2>/dev/null)" ||
    return 1
  pane_pid="$(tmux display-message -p -t "$PANE" '#{pane_pid}' 2>/dev/null)" ||
    return 1

  for ws in "$SESSION_STATE_DIR"/*/workspace.yaml; do
    [ -r "$ws" ] || continue
    this_cwd="$(awk -F': ' '/^cwd: /{sub(/[[:space:]]+$/, "", $2); print $2; exit}' "$ws")"
    [ "$this_cwd" = "$pane_cwd" ] || continue
    for lock in "${ws%/workspace.yaml}"/inuse.*.lock; do
      [ -e "$lock" ] || continue
      lock_pid="${lock##*/inuse.}"
      lock_pid="${lock_pid%.lock}"
      case "$lock_pid" in
        ''|*[!0-9]*) continue ;;
      esac

      parent="$lock_pid"
      while [ "$parent" -gt 1 ]; do
        if [ "$parent" = "$pane_pid" ]; then
          if [ -z "$selected" ]; then
            selected="$ws"
          elif [ "$selected" != "$ws" ]; then
            return 1
          fi
          break
        fi
        parent="$(ps -o ppid= -p "$parent" 2>/dev/null | tr -d '[:space:]')"
        case "$parent" in
          ''|*[!0-9]*) break ;;
        esac
      done
    done
  done

  [ -n "$selected" ] || return 1
  printf '%s\n' "$selected"
}

if [ -n "${SELF_COMPACT_WORKSPACE:-}" ]; then
  WORKSPACE="$SELF_COMPACT_WORKSPACE"
else
  WORKSPACE="$(resolve_workspace)" || {
    echo "submit-compact.sh: could not resolve one active Copilot session for this pane; compact not submitted" >&2
    exit 1
  }
fi

[ -r "$WORKSPACE" ] || {
  echo "submit-compact.sh: could not resolve the active Copilot session; compact not submitted" >&2
  exit 1
}

SUMMARY_COUNT="$(awk -F': ' '/^summary_count: /{print $2; exit}' "$WORKSPACE")"
case "$SUMMARY_COUNT" in
  ''|*[!0-9]*)
    echo "submit-compact.sh: active session has no numeric summary_count; compact not submitted" >&2
    exit 1
    ;;
esac

EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"
[ -r "$EVENTS" ] || {
  echo "submit-compact.sh: active session event log is unavailable; compact not submitted" >&2
  exit 1
}
EVENT_LINE_COUNT="$(wc -l < "$EVENTS" | tr -d '[:space:]')"

submission_activity_exists() {
  awk -v after="$EVENT_LINE_COUNT" '
    NR > after &&
      (/"type":"user.message"/ || /"type":"assistant.turn_start"/) {
        found = 1
        exit
      }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"
}

FILES_DIR="${WORKSPACE%/workspace.yaml}/files"
mkdir -p "$FILES_DIR"
READY="$FILES_DIR/self-compact-$RUN_ID.ready"
ARMED="$FILES_DIR/self-compact-$RUN_ID.armed"
CANCELLED="$FILES_DIR/self-compact-$RUN_ID.cancelled"
LOG="$FILES_DIR/self-compact-$RUN_ID.log"
WATCHER="$SCRIPT_DIR/resume-after-compact.sh"

shell_quote() {
  printf '%q' "$1"
}

watcher_command=""
for argument in \
  "$WATCHER" "$PANE" "$WORKSPACE" "$SUMMARY_COUNT" "$EVENT_LINE_COUNT" \
  "$READY" "$ARMED" "$CANCELLED" "$MARKER" "$CONTINUATION" "$TMUX_BIN" \
  "$COMMAND"; do
  quoted="$(shell_quote "$argument")"
  watcher_command="${watcher_command}${watcher_command:+ }$quoted"
done
quoted_log="$(shell_quote "$LOG")"
watcher_command="$watcher_command >> $quoted_log 2>&1"
quoted_locale="$(shell_quote "$SC_INPUT_LOCALE")"
watcher_command="LC_ALL=$quoted_locale LANG=$quoted_locale SELF_COMPACT_LOCALE=$quoted_locale $watcher_command"

cleanup_unarmed_watcher() {
  [ -e "$ARMED" ] || : > "$CANCELLED"
}
trap cleanup_unarmed_watcher EXIT

# The watcher records failures in its own log. Keep its detached exit status
# from becoming a tmux status message over the Copilot interface.
watcher_command="$watcher_command || true"

if ! tmux run-shell -b "$watcher_command"; then
  rm -f "$READY" "$ARMED" "$CANCELLED"
  echo "submit-compact.sh: continuation watcher did not start; compact not submitted" >&2
  exit 1
fi

for ((attempt = 1; attempt <= 30; attempt++)); do
  [ -e "$READY" ] && break
  sleep 0.1
done

if [ ! -e "$READY" ]; then
  echo "submit-compact.sh: continuation watcher did not become ready; compact not submitted" >&2
  exit 1
fi

prepare_status=0
sc_prepare_verified_command "$COMMAND" submission_activity_exists ||
  prepare_status=$?
case "$prepare_status" in
  0) ;;
  10)
    echo "submit-compact.sh: session activity started; compact not submitted" >&2
    exit 1
    ;;
  *)
    echo "submit-compact.sh: compact command could not be rendered exactly; compact not submitted" >&2
    exit 1
    ;;
esac

expected_hex="$(sc_literal_hex "$COMMAND")"
final_status=0
sc_wait_for_exact_render "$expected_hex" submission_activity_exists ||
  final_status=$?
case "$final_status" in
  0) ;;
  10)
    sc_cleanup_exact_command "$expected_hex"
    echo "submit-compact.sh: session activity started before Enter; compact not submitted" >&2
    exit 1
    ;;
  *)
    sc_cleanup_exact_command "$expected_hex"
    echo "submit-compact.sh: compact command changed before Enter; compact not submitted" >&2
    exit 1
    ;;
esac
if submission_activity_exists; then
  sc_cleanup_exact_command "$expected_hex"
  echo "submit-compact.sh: session activity started before Enter; compact not submitted" >&2
  exit 1
fi
if ! tmux send-keys -t "$PANE" Enter; then
  sc_cleanup_exact_command "$expected_hex"
  echo "submit-compact.sh: could not submit the compact command" >&2
  exit 1
fi

: > "$ARMED"
trap - EXIT
echo "submitted compact; post-compact continuation watcher armed"
echo "watcher log: $LOG"
