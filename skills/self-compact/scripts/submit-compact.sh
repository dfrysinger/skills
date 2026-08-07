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
PS_BIN="$(command -v ps)" || {
  echo "submit-compact.sh: ps is unavailable; compact not submitted" >&2
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
START_GRACE_SECONDS="${SELF_COMPACT_START_GRACE_SECONDS:-15}"
for value_name in AUTH_WAIT_SECONDS QUIESCENCE_GRACE_SECONDS; do
  value="${!value_name}"
  if ! awk -v seconds="$value" 'BEGIN {
    exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ && seconds > 0 && seconds <= 30)
  }'; then
    echo "submit-compact.sh: $value_name must be greater than zero and at most 30 seconds; compact not submitted" >&2
    exit 1
  fi
done
if ! awk -v quiet="$QUIESCENCE_GRACE_SECONDS" -v auth="$AUTH_WAIT_SECONDS" \
  'BEGIN { exit !(quiet < auth) }'; then
  echo "submit-compact.sh: QUIESCENCE_GRACE_SECONDS must be less than AUTH_WAIT_SECONDS; compact not submitted" >&2
  exit 1
fi
if ! awk -v seconds="$START_GRACE_SECONDS" 'BEGIN {
  exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ && seconds > 0 && seconds <= 30)
}'; then
  echo "submit-compact.sh: START_GRACE_SECONDS must be greater than zero and at most 30 seconds; compact not submitted" >&2
  exit 1
fi
AUTH_SCAN_BYTES="${SELF_COMPACT_AUTH_SCAN_BYTES:-65536}"
case "$AUTH_SCAN_BYTES" in
  ''|*[!0-9]*)
    echo "submit-compact.sh: authorization scan bound must be a positive integer; compact not submitted" >&2
    exit 1
    ;;
esac
if [ "$AUTH_SCAN_BYTES" -lt 65536 ] || [ "$AUTH_SCAN_BYTES" -gt 67108864 ]; then
  echo "submit-compact.sh: authorization scan bound must be between 65536 and 67108864 bytes; compact not submitted" >&2
  exit 1
fi

owner_pid_for_workspace() {
  local ws="$1"
  local pane_pid lock lock_pid parent
  local selected=""
  pane_pid="$("$TMUX_BIN" display-message -p -t "$PANE" '#{pane_pid}' 2>/dev/null)" ||
    return 1
  case "$pane_pid" in ''|*[!0-9]*) return 1 ;; esac

  for lock in "${ws%/workspace.yaml}"/inuse.*.lock; do
    [ -e "$lock" ] || continue
    lock_pid="${lock##*/inuse.}"
    lock_pid="${lock_pid%.lock}"
    case "$lock_pid" in ''|*[!0-9]*) continue ;; esac
    parent="$lock_pid"
    while [ "$parent" -gt 1 ]; do
      if [ "$parent" = "$pane_pid" ]; then
        if [ -z "$selected" ]; then
          selected="$lock_pid"
        elif [ "$selected" != "$lock_pid" ]; then
          return 2
        fi
        break
      fi
      parent="$(ps -o ppid= -p "$parent" 2>/dev/null | tr -d '[:space:]')"
      case "$parent" in ''|*[!0-9]*) break ;; esac
    done
  done
  [ -n "$selected" ] || return 1
  printf '%s\n' "$selected"
}

resolve_workspace() {
  local pane_cwd ws this_cwd owner_pid owner_status
  local selected="" selected_pid=""
  pane_cwd="$("$TMUX_BIN" display-message -p -t "$PANE" '#{pane_current_path}' 2>/dev/null)" ||
    return 1

  for ws in "$SESSION_STATE_DIR"/*/workspace.yaml; do
    [ -r "$ws" ] || continue
    this_cwd="$(awk -F': ' '/^cwd: /{sub(/[[:space:]]+$/, "", $2); print $2; exit}' "$ws")"
    [ "$this_cwd" = "$pane_cwd" ] || continue
    owner_status=0
    owner_pid="$(owner_pid_for_workspace "$ws")" || owner_status=$?
    case "$owner_status" in
      0) ;;
      1) continue ;;
      *) return 1 ;;
    esac
    if [ -z "$selected" ]; then
      selected="$ws"
      selected_pid="$owner_pid"
    elif [ "$selected" != "$ws" ] || [ "$selected_pid" != "$owner_pid" ]; then
      return 1
    fi
  done
  [ -n "$selected" ] || return 1
  printf '%s\t%s\n' "$selected" "$selected_pid"
}

if [ -n "${SELF_COMPACT_WORKSPACE:-}" ]; then
  WORKSPACE="$SELF_COMPACT_WORKSPACE"
  OWNER_PID="$(owner_pid_for_workspace "$WORKSPACE")" || {
    echo "submit-compact.sh: could not bind the active Copilot process for this pane; compact not submitted" >&2
    exit 1
  }
else
  active_session="$(resolve_workspace)" || {
    echo "submit-compact.sh: could not resolve one active Copilot session for this pane; compact not submitted" >&2
    exit 1
  }
  IFS=$'\t' read -r WORKSPACE OWNER_PID <<< "$active_session"
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

CANDIDATE_BOUNDARY="$(
  /usr/bin/perl -e 'my $size = -s $ARGV[0]; defined $size or exit 1; print $size' \
    "$EVENTS"
)" || {
  echo "submit-compact.sh: could not snapshot the event log after acquiring the lock; compact not submitted" >&2
  exit 1
}
CANDIDATE_CALL_ID="$(
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $end, $maximum) = @ARGV;
    $end =~ /^\d+$/ && $maximum =~ /^\d+$/ or exit 1;
    open my $fh, "<", $path or exit 1;
    binmode $fh;
    my $size = (stat($fh))[7];
    defined $size && $size >= $end or exit 1;
    my $floor = $end > $maximum ? $end - $maximum : 0;
    seek($fh, $floor, 0) or exit 1;
    read($fh, my $buffer, $end - $floor) == $end - $floor or exit 1;
    if ($floor > 0) {
      my $newline = index($buffer, "\n");
      exit 2 if $newline < 0;
      $buffer = substr($buffer, $newline + 1);
    }
    exit 1 if length($buffer) && substr($buffer, -1) ne "\n";
    my @lines = split /\n/, $buffer;
    my @starts;
    my %completed;
    for my $line (@lines) {
      my $event = eval { decode_json($line) };
      exit 3 unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      my $type = $event->{type} // "";
      my $data = $event->{data};
      next unless $data && ref($data) eq "HASH";
      my $id = $data->{toolCallId} // "";
      if ($type eq "tool.execution_complete" && length $id) {
        $completed{$id} = 1;
      } elsif ($type eq "tool.execution_start") {
        push @starts, [$id, $data->{toolName} // ""];
      }
    }
    exit 2 unless @starts;
    my ($id, $name) = @{$starts[-1]};
    exit 2 unless $name eq "bash" && length $id && !$completed{$id};
    print $id;
  ' "$EVENTS" "$CANDIDATE_BOUNDARY" "$AUTH_SCAN_BYTES"
)" || {
  echo "submit-compact.sh: could not identify the current root-agent Bash tool call within the bounded event tail; compact not submitted" >&2
  exit 1
}
printf '%s\n' "$CANDIDATE_CALL_ID" > "$LOCK_DIR/tool-call-id"

shell_quote() {
  printf '%q' "$1"
}

watcher_command=""
for argument in \
  "$WATCHER" "$PANE" "$OWNER_PID" "$WORKSPACE" "$SUMMARY_COUNT" "$READY" "$ARMED" \
  "$CANCELLED" "$HANDOFF" "$TOKEN" "$CONTINUATION" "$TMUX_BIN" "$COMMAND" \
  "$CUSTOM_INSTRUCTIONS" "$LOCK_DIR" "$LOCK_TOKEN" "$CANDIDATE_CALL_ID" \
  "$SCRIPT_PATH" "$LOG" "$AMBIGUOUS_WAIT_SECONDS" "$AUTH_WAIT_SECONDS" \
  "$QUIESCENCE_GRACE_SECONDS" "$START_GRACE_SECONDS" "$PS_BIN"; do
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
if ! "$TMUX_BIN" run-shell -b "$watcher_command"; then
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

watcher_owns_lock() {
  local watcher_pid
  lock_token_matches &&
    [ "$(lock_state)" = watcher-owned ] &&
    [ -r "$LOCK_DIR/watcher.pid" ] &&
    [ -e "$LOCK_DIR/ready" ] || return 1
  watcher_pid="$(cat "$LOCK_DIR/watcher.pid")"
  pid_is_live "$watcher_pid"
}

watcher_owns_lock || {
  echo "submit-compact.sh: detached verifier lost lock ownership after READY; compact not submitted" >&2
  exit 1
}
HANDOFF_EVENT_OFFSET="$(
  /usr/bin/perl -e 'my $size = -s $ARGV[0]; defined $size or exit 1; print $size' \
    "$EVENTS"
)" || {
  echo "submit-compact.sh: could not snapshot the positive handoff boundary; compact not submitted" >&2
  exit 1
}
printf '%s\n%s\n%s\n' \
  "$LOCK_TOKEN" "$CANDIDATE_CALL_ID" "$HANDOFF_EVENT_OFFSET" > "$HANDOFF.next"
watcher_owns_lock || {
  rm -f "$HANDOFF.next"
  echo "submit-compact.sh: detached verifier lost lock ownership before HANDOFF; compact not submitted" >&2
  exit 1
}
mv "$HANDOFF.next" "$HANDOFF"
: > "$LOCK_DIR/handoff"
HANDOFF_COMPLETE=true
trap - EXIT

echo "self-compact handoff receipt: $LOCK_TOKEN"
echo "self-compact verifier armed; foreground helper complete"
echo "watcher log: $LOG"
