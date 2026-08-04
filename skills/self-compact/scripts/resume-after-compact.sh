#!/usr/bin/env bash
# Verify one token-bearing compact, then submit one strict continuation.

set -euo pipefail

PANE="${1:?pane is required}"
WORKSPACE="${2:?workspace.yaml path is required}"
BEFORE="${3:?baseline summary_count is required}"
BEFORE_EVENTS="${4:?baseline event line count is required}"
READY="${5:?ready path is required}"
ARMED="${6:?armed path is required}"
CANCELLED="${7:?cancelled path is required}"
TOKEN="${8:?run token is required}"
CONTINUATION="${9:?continuation is required}"
TMUX_BIN="${10:?tmux path is required}"
COMMAND="${11:?compact command is required}"
CUSTOM_INSTRUCTIONS="${12:?custom instructions are required}"
LOCK_DIR="${13:?lock directory is required}"
LOCK_TOKEN="${14:?lock token is required}"

[ -x "$TMUX_BIN" ] || {
  echo "continuation watcher has no executable tmux path" >&2
  exit 1
}

lock_token_matches() {
  [ -r "$LOCK_DIR/token" ] &&
    [ "$(cat "$LOCK_DIR/token")" = "$LOCK_TOKEN" ]
}

write_lock_state() {
  local state="$1"
  printf '%s\n' "$state" > "$LOCK_DIR/state.next"
  mv "$LOCK_DIR/state.next" "$LOCK_DIR/state"
}

cleanup() {
  rm -f "$READY" "$ARMED" "$CANCELLED"
  if lock_token_matches; then
    rm -rf "$LOCK_DIR"
  fi
}
trap cleanup EXIT

lock_token_matches || {
  echo "continuation watcher lock token mismatch" >&2
  exit 1
}
printf '%s\n' "$$" > "$LOCK_DIR/watcher.pid"
write_lock_state watcher-owned

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=skills/self-compact/scripts/input-recovery.sh
source "$SCRIPT_DIR/input-recovery.sh"
if ! sc_input_init "$TMUX_BIN" "$PANE"; then
  echo "continuation watcher could not verify a UTF-8 locale; input state remains unknown" >&2
  exit 1
fi
: > "$LOCK_DIR/ready"
: > "$READY"

POLL_SECONDS="${SELF_COMPACT_POLL_SECONDS:-1}"
MAX_POLLS="${SELF_COMPACT_MAX_POLLS:-1800}"
RESUME_GRACE_SECONDS="${SELF_COMPACT_RESUME_GRACE_SECONDS:-3}"
START_GRACE_SECONDS="${SELF_COMPACT_START_GRACE_SECONDS:-15}"
CHECKPOINTS_DIR="${WORKSPACE%/workspace.yaml}/checkpoints"
EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"

for ((attempt = 1; attempt <= 1200; attempt++)); do
  if [ -e "$ARMED" ]; then
    break
  fi
  if [ -e "$CANCELLED" ]; then
    echo "continuation watcher cancelled before compact was armed" >&2
    exit 1
  fi
  sleep 0.1
done

[ -e "$ARMED" ] || {
  echo "continuation watcher was never armed" >&2
  exit 1
}

event_line_after() {
  local after="$1"
  local event_type="$2"
  awk -v after="$after" -v event_type="$event_type" '
    NR > after && index($0, "\"type\":\"" event_type "\"") {
      print NR
      exit
    }
  ' "$EVENTS"
}

epoch_milliseconds() {
  sc_epoch_milliseconds
}

compaction_start_line=""
turn_end_line=""
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  compaction_start_line="$(event_line_after "$BEFORE_EVENTS" session.compaction_start)"
  [ -n "$compaction_start_line" ] && break
  turn_end_line="$(event_line_after "$BEFORE_EVENTS" assistant.turn_end)"
  [ -n "$turn_end_line" ] && break
  sleep "$POLL_SECONDS"
done

if [ -z "$compaction_start_line" ] && [ -z "$turn_end_line" ]; then
  echo "timed out waiting for the submitting assistant.turn_end or compaction start" >&2
  exit 1
fi

if [ -z "$compaction_start_line" ]; then
  start_grace_milliseconds="$(sc_seconds_to_milliseconds "$START_GRACE_SECONDS")" || {
    echo "invalid compaction start grace: $START_GRACE_SECONDS" >&2
    exit 1
  }
  start_now_milliseconds="$(epoch_milliseconds)"
  case "$start_now_milliseconds" in ''|*[!0-9]*) exit 1 ;; esac
  start_deadline_milliseconds=$((start_now_milliseconds + start_grace_milliseconds))
  while :; do
    compaction_start_line="$(event_line_after "$BEFORE_EVENTS" session.compaction_start)"
    [ -n "$compaction_start_line" ] && break
    now_milliseconds="$(epoch_milliseconds)"
    case "$now_milliseconds" in ''|*[!0-9]*) exit 1 ;; esac
    if [ "$now_milliseconds" -ge "$start_deadline_milliseconds" ]; then
      compaction_start_line="$(event_line_after "$BEFORE_EVENTS" session.compaction_start)"
      break
    fi
    sleep_seconds="$(
      awk -v poll="$POLL_SECONDS" \
        -v remaining="$((start_deadline_milliseconds - now_milliseconds))" '
        BEGIN {
          remaining_seconds = remaining / 1000
          if (poll < remaining_seconds) print poll
          else print remaining_seconds
        }'
    )"
    sleep "$sleep_seconds"
  done
fi

if [ -z "$compaction_start_line" ]; then
  sc_cleanup_exact_command "$(sc_literal_hex "$COMMAND")"
  sc_notice "self-compact: compaction did not start; cancelled"
  echo "compaction did not start within ${START_GRACE_SECONDS}s after assistant.turn_end" >&2
  exit 1
fi

completion_line=""
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  completion_line="$(event_line_after "$compaction_start_line" session.compaction_complete)"
  [ -n "$completion_line" ] && break
  sleep "$POLL_SECONDS"
done
[ -n "$completion_line" ] || {
  echo "timed out waiting for session.compaction_complete" >&2
  exit 1
}

completion_json="$(sed -n "${completion_line}p" "$EVENTS")"
checkpoint_number="$(
  printf '%s\n' "$completion_json" |
    /usr/bin/perl -MJSON::PP -e '
      my $line = <STDIN>;
      my $event = eval { decode_json($line) } or exit 1;
      my $data = $event->{data} && ref($event->{data}) eq "HASH"
        ? $event->{data}
        : $event;
      exit 1 unless ($data->{success} // 0);
      exit 1 unless defined $data->{customInstructions};
      exit 1 unless $data->{customInstructions} eq $ARGV[0];
      exit 1 unless defined $data->{checkpointNumber};
      exit 1 unless $data->{checkpointNumber} =~ /^\d+$/;
      print $data->{checkpointNumber};
    ' "$CUSTOM_INSTRUCTIONS"
)" || {
  echo "first compact completion did not match this run token or failed" >&2
  exit 1
}

[ "$checkpoint_number" -gt "$BEFORE" ] || {
  echo "matching compact did not advance the checkpoint number" >&2
  exit 1
}

landed=false
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  current="$(awk -F': ' '/^summary_count: /{print $2; exit}' "$WORKSPACE" 2>/dev/null || true)"
  case "$current" in
    ''|*[!0-9]*) ;;
    *)
      if [ "$current" -ge "$checkpoint_number" ]; then
        checkpoint_prefix="$(printf '%03d-' "$checkpoint_number")"
        checkpoint_count="$(
          find "$CHECKPOINTS_DIR" -maxdepth 1 -type f \
            -name "${checkpoint_prefix}*.md" -print 2>/dev/null |
            wc -l |
            tr -d '[:space:]'
        )"
        if [ "$checkpoint_count" -eq 1 ]; then
          landed=true
          echo "matching compact advanced summary_count to $current at checkpoint $checkpoint_number"
          break
        fi
      fi
      ;;
  esac
  sleep "$POLL_SECONDS"
done

[ "$landed" = true ] || {
  echo "matching compact event did not produce exactly one checkpoint file for checkpoint $checkpoint_number under $CHECKPOINTS_DIR" >&2
  exit 1
}

post_compact_activity_exists() {
  awk -v after="$completion_line" '
    NR > after &&
      (/"type":"user.message"/ || /"type":"assistant.turn_start"/) {
        found = 1
        exit
      }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"
}

sleep "$RESUME_GRACE_SECONDS"
if post_compact_activity_exists; then
  echo "post-compact activity already present after event line $completion_line; continuation not needed"
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
if post_compact_activity_exists; then
  sc_cleanup_exact_command "$expected_hex"
  echo "post-compact activity started before submission; continuation not needed"
  exit 0
fi

"$TMUX_BIN" send-keys -t "$PANE" Enter
for ((attempt = 1; attempt <= ${SELF_COMPACT_CONTINUATION_CONFIRM_POLLS:-100}; attempt++)); do
  if awk -v after="$completion_line" -v continuation="$CONTINUATION" '
    NR > after &&
      /"type":"user.message"/ &&
      index($0, "\"content\":\"" continuation "\"") {
        found = 1
        exit
      }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"; then
    echo "submitted post-compact continuation after event line $completion_line"
    exit 0
  fi
  sleep "${SELF_COMPACT_CONTINUATION_CONFIRM_DELAY_SECONDS:-0.1}"
done

sc_cleanup_exact_command "$expected_hex"
echo "compact landed, but continuation submission was not confirmed" >&2
exit 1
