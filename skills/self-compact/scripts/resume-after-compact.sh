#!/usr/bin/env bash
# Wait for a queued compact to increment summary_count, then submit continuation.

set -euo pipefail

PANE="${1:?pane is required}"
WORKSPACE="${2:?workspace.yaml path is required}"
BEFORE="${3:?baseline summary_count is required}"
BEFORE_EVENTS="${4:?baseline event line count is required}"
READY="${5:?ready path is required}"
ARMED="${6:?armed path is required}"
CANCELLED="${7:?cancelled path is required}"
MARKER="${8:?checkpoint marker is required}"
CONTINUATION="${9:-proceed}"
TMUX_BIN="${10:-}"
COMMAND="${11:?marked compact command is required}"
[ -x "$TMUX_BIN" ] || {
  echo "continuation watcher has no executable tmux path" >&2
  exit 1
}
cleanup() {
  rm -f "$READY" "$ARMED" "$CANCELLED"
}
trap cleanup EXIT

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=skills/self-compact/scripts/input-recovery.sh
source "$SCRIPT_DIR/input-recovery.sh"
if ! sc_input_init "$TMUX_BIN" "$PANE"; then
  echo "continuation watcher could not verify a UTF-8 locale; input state remains unknown" >&2
  exit 1
fi
POLL_SECONDS="${SELF_COMPACT_POLL_SECONDS:-1}"
MAX_POLLS="${SELF_COMPACT_MAX_POLLS:-1800}"
RESUME_GRACE_SECONDS="${SELF_COMPACT_RESUME_GRACE_SECONDS:-3}"
START_GRACE_SECONDS="${SELF_COMPACT_START_GRACE_SECONDS:-15}"
CHECKPOINTS_DIR="${WORKSPACE%/workspace.yaml}/checkpoints"
EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"

: > "$READY"

for ((attempt = 1; attempt <= 1200; attempt++)); do
  [ -e "$CANCELLED" ] && {
    echo "continuation watcher cancelled before compact submission" >&2
    exit 1
  }
  [ -e "$ARMED" ] && break
  sleep 0.1
done

if [ ! -e "$ARMED" ]; then
  echo "continuation watcher was never armed" >&2
  exit 1
fi

failed_compaction_exists() {
  awk -v before="$BEFORE_EVENTS" '
    NR > before &&
      /"type":"session.compaction_complete"/ &&
      /"success":false/ { found = 1; exit }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"
}

event_line_after_submission() {
  local event_type="$1"
  awk -v before="$BEFORE_EVENTS" -v event_type="$event_type" '
    NR > before && index($0, "\"type\":\"" event_type "\"") {
      print NR
      exit
    }
  ' "$EVENTS"
}

epoch_milliseconds() {
  local perl_bin seconds
  perl_bin="$(command -v perl 2>/dev/null || true)"
  if [ -n "$perl_bin" ]; then
    "$perl_bin" -MTime::HiRes=time -e \
      'printf "%.0f\n", time() * 1000'
    return
  fi
  seconds="$(date +%s)"
  printf '%s000\n' "$seconds"
}

compaction_start_line=""
turn_end_line=""
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  if failed_compaction_exists; then
    echo "compact failed before producing the marked checkpoint" >&2
    exit 1
  fi
  compaction_start_line="$(event_line_after_submission session.compaction_start)"
  [ -n "$compaction_start_line" ] && break
  turn_end_line="$(event_line_after_submission assistant.turn_end)"
  [ -n "$turn_end_line" ] && break
  sleep "$POLL_SECONDS"
done

if [ -z "$compaction_start_line" ] && [ -z "$turn_end_line" ]; then
  echo "timed out waiting for the submitting assistant.turn_end or compaction start" >&2
  exit 1
fi

if [ -z "$compaction_start_line" ]; then
  start_grace_milliseconds="$(
    awk -v seconds="$START_GRACE_SECONDS" '
      BEGIN {
        if (seconds !~ /^[0-9]+([.][0-9]+)?$/) exit 1
        milliseconds = int((seconds * 1000) + 0.5)
        if (milliseconds < 1) milliseconds = 1
        print milliseconds
      }'
  )" || {
    echo "invalid compaction start grace: $START_GRACE_SECONDS" >&2
    exit 1
  }
  start_now_milliseconds="$(epoch_milliseconds)"
  case "$start_now_milliseconds" in
    ''|*[!0-9]*)
      echo "could not read the compaction start clock" >&2
      exit 1
      ;;
  esac
  start_deadline_milliseconds=$((start_now_milliseconds + start_grace_milliseconds))
  while :; do
    if failed_compaction_exists; then
      echo "compact failed before producing the marked checkpoint" >&2
      exit 1
    fi
    compaction_start_line="$(event_line_after_submission session.compaction_start)"
    [ -n "$compaction_start_line" ] && break
    now_milliseconds="$(epoch_milliseconds)"
    case "$now_milliseconds" in
      ''|*[!0-9]*)
        echo "could not read the compaction start clock" >&2
        exit 1
        ;;
    esac
    if [ "$now_milliseconds" -ge "$start_deadline_milliseconds" ]; then
      # Read once more at expiry so an event from the final sleep interval wins.
      if failed_compaction_exists; then
        echo "compact failed before producing the marked checkpoint" >&2
        exit 1
      fi
      compaction_start_line="$(
        event_line_after_submission session.compaction_start
      )"
      break
    fi
    sleep_seconds="$(
      awk -v poll="$POLL_SECONDS" \
        -v remaining="$((start_deadline_milliseconds - now_milliseconds))" '
        BEGIN {
          if (poll <= 0) exit 1
          remaining_seconds = remaining / 1000
          if (poll < remaining_seconds) print poll
          else print remaining_seconds
        }'
    )" || {
      echo "invalid compaction poll interval: $POLL_SECONDS" >&2
      exit 1
    }
    sleep "$sleep_seconds"
  done
fi

if [ -z "$compaction_start_line" ]; then
  sc_cleanup_exact_command "$(sc_literal_hex "$COMMAND")"
  sc_notice "self-compact: compaction did not start; cancelled"
  echo "compaction did not start within ${START_GRACE_SECONDS}s after assistant.turn_end" >&2
  exit 1
fi

landed=false
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  if failed_compaction_exists; then
    echo "compact failed before producing the marked checkpoint" >&2
    exit 1
  fi

  current="$(awk -F': ' '/^summary_count: /{print $2; exit}' "$WORKSPACE" 2>/dev/null || true)"
  case "$current" in
    ''|*[!0-9]*) ;;
    *)
      if [ "$current" -gt "$BEFORE" ] &&
        grep -R -F -q -- "$MARKER" "$CHECKPOINTS_DIR" 2>/dev/null; then
        landed=true
        echo "marked compact advanced summary_count to $current"
        break
      fi
      ;;
  esac
  sleep "$POLL_SECONDS"
done

if [ "$landed" != true ]; then
  echo "timed out waiting for compact checkpoint marker $MARKER beyond summary_count $BEFORE" >&2
  exit 1
fi

compaction_line=""
for ((attempt = 1; attempt <= 300; attempt++)); do
  compaction_line="$(
    awk -v before="$BEFORE_EVENTS" '
      NR > before && /"type":"session.compaction_complete"/ { line = NR }
      END { if (line) print line }
    ' "$EVENTS"
  )"
  [ -n "$compaction_line" ] && break
  sleep 0.1
done

if [ -z "$compaction_line" ]; then
  echo "marked checkpoint landed, but session.compaction_complete was not recorded" >&2
  exit 1
fi

post_compact_activity_exists() {
  awk -v after="$compaction_line" '
    NR > after &&
      (/"type":"user.message"/ || /"type":"assistant.turn_start"/) { found = 1; exit }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"
}

# Autopilot sometimes resumes on its own. Give it one short chance, then inject
# only when no post-compact user message or assistant turn exists.
sleep "$RESUME_GRACE_SECONDS"
if post_compact_activity_exists; then
  echo "post-compact activity already present after event line $compaction_line; continuation not needed"
  exit 0
fi

row_limit="$(sc_pane_one_row_limit)" || {
  echo "compact landed, but current pane width is unavailable; continuation not submitted" >&2
  exit 1
}
if ! sc_one_row_command_fits "$CONTINUATION" "$row_limit"; then
  echo "compact landed, but continuation no longer fits one safe editor row; continuation not submitted" >&2
  exit 1
fi

prepare_status=0
sc_prepare_verified_command "$CONTINUATION" post_compact_activity_exists ||
  prepare_status=$?
case "$prepare_status" in
  0) ;;
  10)
    echo "post-compact activity started during recovery; continuation not needed"
    exit 0
    ;;
  *)
    echo "compact landed, but continuation never rendered exactly" >&2
    exit 1
    ;;
esac

expected_hex="$(sc_literal_hex "$CONTINUATION")"
final_status=0
sc_wait_for_exact_render "$expected_hex" post_compact_activity_exists ||
  final_status=$?
case "$final_status" in
  0) ;;
  10)
    sc_cleanup_exact_command "$expected_hex"
    echo "post-compact activity started before submission; continuation not needed"
    exit 0
    ;;
  *)
    sc_cleanup_exact_command "$expected_hex"
    echo "compact landed, but continuation changed before Enter" >&2
    exit 1
    ;;
esac
if post_compact_activity_exists; then
  sc_cleanup_exact_command "$expected_hex"
  echo "post-compact activity started before submission; continuation not needed"
  exit 0
fi

"$TMUX_BIN" send-keys -t "$PANE" Enter
for ((attempt = 1; attempt <= ${SELF_COMPACT_CONTINUATION_CONFIRM_POLLS:-100}; attempt++)); do
  if awk -v after="$compaction_line" -v continuation="$CONTINUATION" '
    NR > after &&
      /"type":"user.message"/ &&
      index($0, "\"content\":\"" continuation "\"") { found = 1; exit }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"; then
    echo "submitted post-compact continuation after event line $compaction_line"
    exit 0
  fi
  sleep "${SELF_COMPACT_CONTINUATION_CONFIRM_DELAY_SECONDS:-0.1}"
done

sc_cleanup_exact_command "$expected_hex"
echo "compact landed, but continuation submission was not confirmed" >&2
exit 1
