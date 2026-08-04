#!/usr/bin/env bash
# Submit the fixed SELF_COMPACT_BRIEF control and arm one continuation watcher.

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

current_turn_has_brief() {
  local perl_bin
  if [ -x /usr/bin/perl ]; then
    perl_bin=/usr/bin/perl
  else
    perl_bin="$(command -v perl 2>/dev/null || true)"
  fi
  [ -n "$perl_bin" ] || return 1
  "$perl_bin" -MJSON::PP -e '
    use strict;
    use warnings;
    my $path = shift;
    open my $fh, "<", $path or exit 1;
    my @messages;
    while (my $line = <$fh>) {
      my $event = eval { decode_json($line) };
      next unless $event && ref($event) eq "HASH";
      my $type = $event->{type} // "";
      if ($type eq "assistant.turn_start") {
        @messages = ();
        next;
      }
      if ($type eq "assistant.message") {
        my $content = $event->{data}{content};
        push @messages, $content if defined $content && length $content;
      }
    }
    for my $content (@messages) {
      next unless $content =~ /\ASELF_COMPACT_BRIEF\n/;
      next unless $content =~ /\nKeep:[ \t]*(\S[^\n]*)/;
      next unless $content =~ /\nDrop:[^\n]*/;
      next unless $content =~ /\nAfter compaction:[ \t]*(\S[^\n]*)/;
      my ($after) = $content =~ /\nAfter compaction:[ \t]*([^\n]+)/;
      next unless defined $after && index($after, "do not compact again") >= 0;
      exit 0;
    }
    exit 1;
  ' "$EVENTS"
}

wait_for_current_turn_brief() {
  local attempts="${SELF_COMPACT_BRIEF_WAIT_ATTEMPTS:-40}"
  local delay="${SELF_COMPACT_BRIEF_WAIT_DELAY_SECONDS:-0.05}"

  case "$attempts" in
    ''|*[!0-9]*|0) return 1 ;;
  esac
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    current_turn_has_brief && return 0
    [ "$attempt" -lt "$attempts" ] && sleep "$delay"
  done
  return 1
}

if ! wait_for_current_turn_brief; then
  echo "submit-compact.sh: current assistant turn has no complete SELF_COMPACT_BRIEF; compact not submitted" >&2
  exit 1
fi

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
LOCK_DIR="$FILES_DIR/self-compact.lock"
LOCK_TOKEN="$TOKEN-$RUN_ID"
READY="$FILES_DIR/self-compact-$RUN_ID.ready"
ARMED="$FILES_DIR/self-compact-$RUN_ID.armed"
CANCELLED="$FILES_DIR/self-compact-$RUN_ID.cancelled"
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
  local state owner_pid
  [ -d "$LOCK_DIR" ] || return 1
  state="$(lock_state)"
  [ "$state" = foreground ] || return 1
  [ -r "$LOCK_DIR/token" ] && [ -r "$LOCK_DIR/submitter.pid" ] || return 1
  [ ! -e "$LOCK_DIR/watcher.pid" ] &&
    [ ! -e "$LOCK_DIR/watcher-launching" ] &&
    [ ! -e "$LOCK_DIR/ready" ] &&
    [ ! -e "$LOCK_DIR/armed" ] || return 1
  owner_pid="$(cat "$LOCK_DIR/submitter.pid")"
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
printf '%s\n%s\n%s\n%s\n' "$READY" "$ARMED" "$CANCELLED" "$LOG" > "$LOCK_DIR/run-files"
write_lock_state foreground

WATCHER_LAUNCH_ATTEMPTED=false
cleanup_foreground() {
  if [ "$WATCHER_LAUNCH_ATTEMPTED" = false ]; then
    if lock_token_matches && [ "$(lock_state)" = foreground ]; then
      rm -rf "$LOCK_DIR"
    fi
  else
    : > "$CANCELLED"
  fi
}
trap cleanup_foreground EXIT

shell_quote() {
  printf '%q' "$1"
}

watcher_command=""
for argument in \
  "$WATCHER" "$PANE" "$WORKSPACE" "$SUMMARY_COUNT" "$EVENT_LINE_COUNT" \
  "$READY" "$ARMED" "$CANCELLED" "$TOKEN" "$CONTINUATION" "$TMUX_BIN" \
  "$COMMAND" "$CUSTOM_INSTRUCTIONS" "$LOCK_DIR" "$LOCK_TOKEN"; do
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
  echo "submit-compact.sh: continuation watcher did not start; lock retained at $LOCK_DIR" >&2
  exit 1
fi

for ((attempt = 1; attempt <= 30; attempt++)); do
  [ -e "$READY" ] && break
  sleep 0.1
done
[ -e "$READY" ] || {
  echo "submit-compact.sh: continuation watcher did not become ready; lock retained at $LOCK_DIR" >&2
  exit 1
}

prepare_status=0
sc_prepare_empty_editor submission_activity_exists || prepare_status=$?
case "$prepare_status" in
  0) ;;
  10)
    echo "submit-compact.sh: session activity started; compact not submitted" >&2
    exit 1
    ;;
  *)
    echo "submit-compact.sh: editor could not be proven empty; compact not submitted" >&2
    exit 1
    ;;
esac

HAD_DRAFT="$SC_PREPARE_HAD_DRAFT"
type_status=0
sc_type_literal "$COMMAND" submission_activity_exists || type_status=$?
case "$type_status" in
  0) ;;
  10)
    echo "submit-compact.sh: session activity started before typing; compact not submitted" >&2
    exit 1
    ;;
  *)
    echo "submit-compact.sh: could not type the compact command" >&2
    exit 1
    ;;
esac

expected_hex="$(sc_literal_hex "$COMMAND")"
render_status=0
sc_wait_for_exact_render "$expected_hex" submission_activity_exists ||
  render_status=$?
case "$render_status" in
  0) ;;
  10)
    sc_cleanup_exact_command "$expected_hex"
    echo "submit-compact.sh: session activity started before Enter; compact not submitted" >&2
    exit 1
    ;;
  *)
    if [ "$HAD_DRAFT" = true ]; then
      sc_cleanup_exact_command "$expected_hex"
      echo "submit-compact.sh: compact command was not exact and this run handled a draft; compact not submitted" >&2
      exit 1
    fi
    ambiguous_status=0
    sc_wait_for_ambiguous_submit "$expected_hex" submission_activity_exists ||
      ambiguous_status=$?
    case "$ambiguous_status" in
      0|2) ;;
      10)
        sc_cleanup_exact_command "$expected_hex"
        echo "submit-compact.sh: session activity started during the timed render wait; compact not submitted" >&2
        exit 1
        ;;
      *)
        sc_cleanup_exact_command "$expected_hex"
        echo "submit-compact.sh: compact command rendered with a known mismatch; compact not submitted" >&2
        exit 1
        ;;
    esac
    ;;
esac

if submission_activity_exists; then
  sc_cleanup_exact_command "$expected_hex"
  echo "submit-compact.sh: session activity started before Enter; compact not submitted" >&2
  exit 1
fi
: > "$ARMED"
: > "$LOCK_DIR/armed"
if ! tmux send-keys -t "$PANE" Enter; then
  sc_cleanup_exact_command "$expected_hex"
  echo "submit-compact.sh: could not submit the compact command" >&2
  exit 1
fi

trap - EXIT
echo "submitted compact; post-compact continuation watcher armed"
echo "watcher log: $LOG"
