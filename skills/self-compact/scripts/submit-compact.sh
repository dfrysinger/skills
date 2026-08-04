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

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
MARKER="SELF_COMPACT_RUN_ID:$RUN_ID"
COMMAND="/compact $STEER Keep this exact continuation marker in the summary: $MARKER."

case "$STEER" in
  *$'\n'*)
    echo "submit-compact.sh: steer must be a single line" >&2
    exit 2
    ;;
esac

validate_single_line() {
  local value_name="$1"
  local value="$2"
  case "$value" in
    *$'\n'*)
      echo "submit-compact.sh: ${value_name} must be a single line" >&2
      exit 2
      ;;
  esac
  if printf '%s' "$value" | LC_ALL=C grep -q '[[:cntrl:]]'; then
    echo "submit-compact.sh: ${value_name} must not contain control characters" >&2
    exit 2
  fi
}

validate_single_line "steer" "$STEER"
validate_single_line "continuation" "$CONTINUATION"

input_region() {
  tmux capture-pane -p -t "$PANE" 2>/dev/null | awk '
    { line[NR] = $0 }
    END {
      for (i = NR; i >= 1; i--) {
        if (line[i] ~ /^❯([[:space:]]|$)/) {
          prompt = i
          break
        }
      }
      if (!prompt) exit 1
      for (i = NR; i > prompt; i--) {
        if (line[i] ~ /^─+$/) {
          bottom = i
          break
        }
      }
      if (!bottom) exit 1
      sub(/^❯[[:space:]]?/, "", line[prompt])
      print line[prompt]
      for (i = prompt + 1; i < bottom; i++) {
        if (line[i] !~ /^─+$/) print line[i]
      }
    }'
}

squash() {
  tr -d '[:space:]'
}

input_is_empty() {
  local text
  text=$(input_region | tr -d '❯' | squash) || return 1
  [ -z "$text" ]
}

normalized_input() {
  input_region | tr -d '❯' | squash
}

stash_input() {
  tmux send-keys -t "$PANE" C-s || return 1
  sleep 0.25
  local stable=0
  for ((attempt = 1; attempt <= 30; attempt++)); do
    if input_is_empty; then
      stable=$((stable + 1))
      [ "$stable" -ge 3 ] && return 0
    else
      stable=0
    fi
    sleep 0.1
  done
  return 1
}

clear_input() {
  local attempt
  for ((attempt = 1; attempt <= 3; attempt++)); do
    if ! tmux send-keys -t "$PANE" C-u; then
      return 1
    fi
    sleep 0.5
    input_is_empty && return 0
  done
  return 1
}

abort_after_send() {
  local reason="$1"
  if clear_input; then
    echo "submit-compact.sh: $reason; input cleared" >&2
  else
    echo "submit-compact.sh: $reason; input cleanup failed" >&2
  fi
  exit 1
}

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
  "$READY" "$ARMED" "$CANCELLED" "$MARKER" "$CONTINUATION" "$TMUX_BIN"; do
  quoted="$(shell_quote "$argument")"
  watcher_command="${watcher_command}${watcher_command:+ }$quoted"
done
quoted_log="$(shell_quote "$LOG")"
watcher_command="$watcher_command >> $quoted_log 2>&1"

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

# Press Ctrl-S exactly once after watcher startup. A second press would restore
# the same draft because Copilot's stash key is a toggle.
if ! stash_input; then
  echo "submit-compact.sh: could not stash Copilot input; compact not submitted" >&2
  exit 1
fi

expected=$(printf '%s' "$COMMAND" | squash)
if ! tmux send-keys -t "$PANE" -l -- "$COMMAND"; then
  abort_after_send "could not type the compact command"
fi

rendered=false
scrolled=false
for ((attempt = 1; attempt <= 40; attempt++)); do
  actual=$(normalized_input || true)
  if [ "$actual" = "$expected" ]; then
    rendered=true
    break
  fi
  if [ -n "$actual" ] &&
    [ "${#actual}" -lt "${#expected}" ] &&
    [[ "$expected" == *"$actual" ]]; then
    scrolled=true
    break
  fi
  sleep 0.5
done

if [ "$scrolled" = true ]; then
  abort_after_send "steer is too long to verify; shorten it or reference the durable artifact"
fi

if [ "$rendered" != true ]; then
  abort_after_send "compact command never rendered exactly"
fi

submitted=false
for ((attempt = 1; attempt <= 10; attempt++)); do
  if ! tmux send-keys -t "$PANE" Enter; then
    abort_after_send "could not submit the compact command"
  fi
  sleep 1.5
  if input_is_empty; then
    submitted=true
    break
  fi
  if [ "$(normalized_input)" != "$expected" ]; then
    break
  fi
done

if [ "$submitted" != true ]; then
  abort_after_send "compact command submission was not confirmed"
fi

: > "$ARMED"
trap - EXIT
echo "submitted compact; post-compact continuation watcher armed"
echo "watcher log: $LOG"
