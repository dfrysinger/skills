#!/usr/bin/env bash
# Arm a detached verifier that submits one fixed SELF_COMPACT_BRIEF control.

set -euo pipefail

[ $# -eq 0 ] || {
  echo "usage: submit-compact.sh" >&2
  echo "submit-compact.sh: inline steers and --continuation are retired; emit SELF_COMPACT_BRIEF in the current assistant message" >&2
  exit 2
}

PANE="${TMUX_PANE:?TMUX_PANE is not set; run inside tmux}"
TMUX_BIN="$(command -v tmux)" || {
  echo "submit-compact.sh: tmux is unavailable; compact not submitted" >&2
  exit 1
}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/submit-compact.sh"
SESSION_STATE_DIR="${SELF_COMPACT_SESSION_STATE_DIR:-$HOME/.copilot/session-state}"
CONTINUATION="Compaction done; resume, do not compact."
# shellcheck source=skills/self-compact/scripts/input-recovery.sh
source "$SCRIPT_DIR/input-recovery.sh"

SC_TMUX_BIN="$TMUX_BIN"
SC_PANE="$PANE"

RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EPOCH_SECONDS="$(date -u +%s)"
TOKEN_SOURCE="${SELF_COMPACT_RUN_TOKEN:-}"
if [ -n "$TOKEN_SOURCE" ]; then
  TOKEN="$TOKEN_SOURCE"
else
  checksum="$(
    printf '%s' "$EPOCH_SECONDS:$$:$RUN_STAMP" |
      cksum |
      awk '{print $1}'
  )"
  case "$checksum" in
    ''|*[!0-9]*)
      echo "submit-compact.sh: could not create a compact run token" >&2
      exit 1
      ;;
  esac
  printf -v TOKEN '%08x' "$checksum"
fi
case "$TOKEN" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *)
    echo "submit-compact.sh: compact run token must be eight lowercase hex characters" >&2
    exit 1
    ;;
esac

CUSTOM_INSTRUCTIONS="Use SELF_COMPACT_BRIEF. B:$TOKEN"
COMMAND="/compact $CUSTOM_INSTRUCTIONS"
RUN_ID="$RUN_STAMP-$$"

ROW_LIMIT="$(sc_pane_one_row_limit)" || {
  echo "submit-compact.sh: could not read pane width; compact not submitted" >&2
  exit 1
}
if ! sc_one_row_command_fits "$COMMAND" "$ROW_LIMIT"; then
  echo "submit-compact.sh: compact command is ${#COMMAND} columns, but this pane safely allows $ROW_LIMIT" >&2
  exit 2
fi
if ! sc_one_row_command_fits "$CONTINUATION" "$ROW_LIMIT"; then
  echo "submit-compact.sh: continuation is ${#CONTINUATION} columns, but this pane safely allows $ROW_LIMIT" >&2
  exit 2
fi
if ! sc_input_init "$TMUX_BIN" "$PANE"; then
  echo "submit-compact.sh: could not verify a UTF-8 locale; compact not submitted" >&2
  exit 1
fi

AMBIGUOUS_WAIT_SECONDS="${SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS:-25}"
if ! sc_ambiguous_wait_is_bounded "$AMBIGUOUS_WAIT_SECONDS"; then
  echo "submit-compact.sh: ambiguous render wait must be between 20 and 30 seconds; compact not submitted" >&2
  exit 1
fi
AUTH_WAIT_SECONDS="${SELF_COMPACT_AUTH_WAIT_SECONDS:-30}"
QUIESCENCE_GRACE_SECONDS="${SELF_COMPACT_QUIESCENCE_GRACE_SECONDS:-2}"
for value_name in AUTH_WAIT_SECONDS QUIESCENCE_GRACE_SECONDS; do
  value="${!value_name}"
  if ! awk -v seconds="$value" 'BEGIN {
    exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ && seconds > 0 && seconds <= 30)
  }'; then
    echo "submit-compact.sh: $value_name must be greater than zero and at most 30 seconds; compact not submitted" >&2
    exit 1
  fi
done

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
      case "$lock_pid" in ''|*[!0-9]*) continue ;; esac
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
        case "$parent" in ''|*[!0-9]*) break ;; esac
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

CANDIDATE_CALL_ID="$(
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my $path = shift;
    open my $fh, "<", $path or exit 1;
    binmode $fh;
    my $size = (stat($fh))[7];
    defined $size or exit 1;
    my $maximum = 8 * 1024 * 1024;
    my $floor = $size > $maximum ? $size - $maximum : 0;
    my $position = $size;
    my $carry = "";
    my %completed;
    while ($position > $floor) {
      my $take = $position - $floor;
      $take = 65536 if $take > 65536;
      $position -= $take;
      seek($fh, $position, 0) or exit 1;
      read($fh, my $chunk, $take) == $take or exit 1;
      my $data = $chunk . $carry;
      my @parts = split /\n/, $data, -1;
      $carry = shift @parts;
      for (my $index = $#parts; $index >= 0; $index--) {
        my $line = $parts[$index];
        next unless index($line, "\"tool.execution_") >= 0;
        my $event = eval { decode_json($line) };
        next unless $event && ref($event) eq "HASH";
        next if defined $event->{agentId};
        my $type = $event->{type} // "";
        my $event_data = $event->{data};
        next unless $event_data && ref($event_data) eq "HASH";
        my $id = $event_data->{toolCallId} // "";
        if ($type eq "tool.execution_complete" && length $id) {
          $completed{$id} = 1;
          next;
        }
        next unless $type eq "tool.execution_start";
        exit 1 unless ($event_data->{toolName} // "") eq "bash";
        exit 1 unless length $id;
        exit 1 if $completed{$id};
        print $id;
        exit 0;
      }
    }
    if ($position == 0 && length $carry) {
      my $event = eval { decode_json($carry) };
      if ($event && ref($event) eq "HASH" && !defined $event->{agentId}) {
        my $event_data = $event->{data};
        if (
          ($event->{type} // "") eq "tool.execution_start" &&
          $event_data && ref($event_data) eq "HASH"
        ) {
          my $id = $event_data->{toolCallId} // "";
          exit 1 unless ($event_data->{toolName} // "") eq "bash";
          exit 1 unless length $id;
          exit 1 if $completed{$id};
          print $id;
          exit 0;
        }
      }
    }
    exit 1;
  ' "$EVENTS"
)" || {
  echo "submit-compact.sh: could not identify the current root-agent Bash tool call; compact not submitted" >&2
  exit 1
}

FILES_DIR="${WORKSPACE%/workspace.yaml}/files"
mkdir -p "$FILES_DIR"
LOCK_DIR="$FILES_DIR/self-compact.lock"
LOCK_TOKEN="$TOKEN-$RUN_ID"
READY="$FILES_DIR/self-compact-$RUN_ID.ready"
ARMED="$FILES_DIR/self-compact-$RUN_ID.armed"
CANCELLED="$FILES_DIR/self-compact-$RUN_ID.cancelled"
HANDOFF="$FILES_DIR/self-compact-$RUN_ID.handoff"
LOG="$FILES_DIR/self-compact-$RUN_ID.log"
WATCHER="$SCRIPT_DIR/resume-after-compact.sh"

lock_state() {
  [ -r "$LOCK_DIR/state" ] && cat "$LOCK_DIR/state"
}

write_lock_state() {
  local state="$1"
  printf '%s\n' "$state" > "$LOCK_DIR/state.next"
  mv "$LOCK_DIR/state.next" "$LOCK_DIR/state"
}

lock_token_matches() {
  [ -r "$LOCK_DIR/token" ] &&
    [ "$(cat "$LOCK_DIR/token")" = "$LOCK_TOKEN" ]
}

pid_is_live() {
  local pid="$1"
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  kill -0 "$pid" >/dev/null 2>&1
}

reclaim_stale_foreground_lock() {
  local state owner_pid existing_token existing_run_id existing_stamp
  local run_files expected_old expected_new ready armed cancelled handoff log
  [ -d "$LOCK_DIR" ] || return 1
  state="$(lock_state)"
  [ "$state" = foreground ] || return 1
  [ -r "$LOCK_DIR/token" ] &&
    [ -r "$LOCK_DIR/submitter.pid" ] &&
    [ -r "$LOCK_DIR/created" ] &&
    [ -r "$LOCK_DIR/run-files" ] || return 1
  [ ! -e "$LOCK_DIR/watcher.pid" ] &&
    [ ! -e "$LOCK_DIR/watcher-launching" ] &&
    [ ! -e "$LOCK_DIR/ready" ] &&
    [ ! -e "$LOCK_DIR/armed" ] &&
    [ ! -e "$LOCK_DIR/handoff" ] || return 1
  existing_token="$(cat "$LOCK_DIR/token")"
  printf '%s\n' "$existing_token" |
    grep -Eq '^[0-9a-f]{8}-[0-9]{8}T[0-9]{6}Z-[1-9][0-9]*$' || return 1
  existing_run_id="${existing_token#*-}"
  existing_stamp="${existing_run_id%-*}"
  owner_pid="$(cat "$LOCK_DIR/submitter.pid")"
  case "$owner_pid" in ''|*[!0-9]*|0|1) return 1 ;; esac
  [ "${existing_run_id##*-}" = "$owner_pid" ] || return 1
  [ "$(cat "$LOCK_DIR/created")" = "$existing_stamp" ] || return 1
  ready="$FILES_DIR/self-compact-$existing_run_id.ready"
  armed="$FILES_DIR/self-compact-$existing_run_id.armed"
  cancelled="$FILES_DIR/self-compact-$existing_run_id.cancelled"
  handoff="$FILES_DIR/self-compact-$existing_run_id.handoff"
  log="$FILES_DIR/self-compact-$existing_run_id.log"
  expected_old="$(printf '%s\n%s\n%s\n%s' "$ready" "$armed" "$cancelled" "$log")"
  expected_new="$(printf '%s\n%s\n%s\n%s\n%s' "$ready" "$armed" "$cancelled" "$handoff" "$log")"
  run_files="$(cat "$LOCK_DIR/run-files")"
  { [ "$run_files" = "$expected_old" ] || [ "$run_files" = "$expected_new" ]; } ||
    return 1
  [ ! -e "$ready" ] &&
    [ ! -e "$armed" ] &&
    [ ! -e "$cancelled" ] &&
    [ ! -e "$handoff" ] &&
    [ ! -e "$log" ] || return 1
  pid_is_live "$owner_pid" && return 1
  rm -rf "$LOCK_DIR"
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if reclaim_stale_foreground_lock && mkdir "$LOCK_DIR" 2>/dev/null; then
    :
  else
    echo "submit-compact.sh: another or ambiguous self-compact run owns $LOCK_DIR; compact not submitted" >&2
    exit 1
  fi
fi
printf '%s\n' "$LOCK_TOKEN" > "$LOCK_DIR/token"
printf '%s\n' "$$" > "$LOCK_DIR/submitter.pid"
printf '%s\n' "$RUN_STAMP" > "$LOCK_DIR/created"
printf '%s\n%s\n%s\n%s\n%s\n' \
  "$READY" "$ARMED" "$CANCELLED" "$HANDOFF" "$LOG" > "$LOCK_DIR/run-files"
printf '%s\n' "$CANDIDATE_CALL_ID" > "$LOCK_DIR/tool-call-id"
printf '%s\n' "$SCRIPT_PATH" > "$LOCK_DIR/helper-path"
write_lock_state foreground

WATCHER_LAUNCH_ATTEMPTED=false
HANDOFF_COMPLETE=false
cleanup_foreground() {
  if [ "$WATCHER_LAUNCH_ATTEMPTED" = false ]; then
    if lock_token_matches && [ "$(lock_state)" = foreground ]; then
      rm -rf "$LOCK_DIR"
    fi
  elif [ "$HANDOFF_COMPLETE" = false ]; then
    : > "$CANCELLED"
  fi
}
trap cleanup_foreground EXIT

shell_quote() {
  printf '%q' "$1"
}

watcher_command=""
for argument in \
  "$WATCHER" "$PANE" "$WORKSPACE" "$SUMMARY_COUNT" "$READY" "$ARMED" \
  "$CANCELLED" "$HANDOFF" "$TOKEN" "$CONTINUATION" "$TMUX_BIN" "$COMMAND" \
  "$CUSTOM_INSTRUCTIONS" "$LOCK_DIR" "$LOCK_TOKEN" "$CANDIDATE_CALL_ID" \
  "$SCRIPT_PATH" "$LOG" "$AMBIGUOUS_WAIT_SECONDS" "$AUTH_WAIT_SECONDS" \
  "$QUIESCENCE_GRACE_SECONDS"; do
  quoted="$(shell_quote "$argument")"
  watcher_command="${watcher_command}${watcher_command:+ }$quoted"
done
quoted_log="$(shell_quote "$LOG")"
watcher_command="$watcher_command >> $quoted_log 2>&1"
quoted_locale="$(shell_quote "$SC_INPUT_LOCALE")"
watcher_command="LC_ALL=$quoted_locale LANG=$quoted_locale SELF_COMPACT_LOCALE=$quoted_locale $watcher_command"
watcher_command="$watcher_command || true"

write_lock_state watcher-launching
: > "$LOCK_DIR/watcher-launching"
WATCHER_LAUNCH_ATTEMPTED=true
if ! tmux run-shell -b "$watcher_command"; then
  echo "submit-compact.sh: detached verifier did not start; lock retained at $LOCK_DIR" >&2
  exit 1
fi

for ((attempt = 1; attempt <= 30; attempt++)); do
  [ -e "$READY" ] && break
  sleep 0.1
done
[ -e "$READY" ] || {
  echo "submit-compact.sh: detached verifier did not become ready; lock retained at $LOCK_DIR" >&2
  exit 1
}

printf '%s\n%s\n' "$LOCK_TOKEN" "$CANDIDATE_CALL_ID" > "$HANDOFF.next"
mv "$HANDOFF.next" "$HANDOFF"
: > "$LOCK_DIR/handoff"
HANDOFF_COMPLETE=true
trap - EXIT

echo "self-compact verifier armed; foreground helper complete"
echo "watcher log: $LOG"
