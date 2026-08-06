#!/usr/bin/env bash
# Authorize, submit, verify, and resume one token-bearing compact.

set -euo pipefail

PANE="${1:?pane is required}"
WORKSPACE="${2:?workspace.yaml path is required}"
BEFORE="${3:?baseline summary_count is required}"
READY="${4:?ready path is required}"
ARMED="${5:?armed path is required}"
CANCELLED="${6:?cancelled path is required}"
HANDOFF="${7:?handoff path is required}"
TOKEN="${8:?run token is required}"
CONTINUATION="${9:?continuation is required}"
TMUX_BIN="${10:?tmux path is required}"
COMMAND="${11:?compact command is required}"
CUSTOM_INSTRUCTIONS="${12:?custom instructions are required}"
LOCK_DIR="${13:?lock directory is required}"
LOCK_TOKEN="${14:?lock token is required}"
TOOL_CALL_ID="${15:?tool call id is required}"
HELPER_PATH="${16:?helper path is required}"
LOG="${17:?log path is required}"
AMBIGUOUS_WAIT_SECONDS="${18:?ambiguous wait is required}"
AUTH_WAIT_SECONDS="${19:?authorization wait is required}"
QUIESCENCE_GRACE_SECONDS="${20:?quiescence grace is required}"

[ -x "$TMUX_BIN" ] || {
  echo "self-compact watcher has no executable tmux path" >&2
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

RELEASE_LOCK=true
cleanup() {
  if [ "$RELEASE_LOCK" = true ]; then
    rm -f "$READY" "$ARMED" "$CANCELLED" "$HANDOFF"
    if lock_token_matches; then
      rm -rf "$LOCK_DIR"
    fi
  fi
}
trap cleanup EXIT

lock_token_matches || {
  echo "self-compact watcher lock token mismatch" >&2
  exit 1
}
printf '%s\n' "$$" > "$LOCK_DIR/watcher.pid"
write_lock_state watcher-owned

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=skills/self-compact/scripts/input-recovery.sh
source "$SCRIPT_DIR/input-recovery.sh"
if ! sc_input_init "$TMUX_BIN" "$PANE"; then
  echo "self-compact watcher could not verify a UTF-8 locale; input state remains unknown" >&2
  exit 1
fi

POLL_SECONDS="${SELF_COMPACT_POLL_SECONDS:-1}"
MAX_POLLS="${SELF_COMPACT_MAX_POLLS:-1800}"
RESUME_GRACE_SECONDS="${SELF_COMPACT_RESUME_GRACE_SECONDS:-3}"
START_GRACE_SECONDS="${SELF_COMPACT_START_GRACE_SECONDS:-15}"
CHECKPOINTS_DIR="${WORKSPACE%/workspace.yaml}/checkpoints"
EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"

deferred_failure() {
  local message="$1"
  echo "$message" >&2
  sc_notice "self-compact cancelled: $message; log: $LOG"
}

: > "$LOCK_DIR/ready"
: > "$READY"

handoff_matches() {
  [ -r "$HANDOFF" ] || return 1
  [ "$(sed -n '1p' "$HANDOFF")" = "$LOCK_TOKEN" ] || return 1
  [ "$(sed -n '2p' "$HANDOFF")" = "$TOOL_CALL_ID" ] || return 1
  [ "$(wc -l < "$HANDOFF" | tr -d '[:space:]')" -eq 2 ]
}

authorization_probe() {
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $call_id, $helper) = @ARGV;
    open my $fh, "<", $path or do { print "wait\n"; exit };
    my @events;
    my $line_number = 0;
    while (my $line = <$fh>) {
      $line_number++;
      next unless index($line, "\"agentId\"") < 0 ||
        index($line, "\"agentId\":null") >= 0;
      my $event = eval { decode_json($line) };
      next unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      push @events, [$line_number, $event];
    }

    my @request_indexes;
    for my $index (0 .. $#events) {
      my $event = $events[$index][1];
      next unless ($event->{type} // "") eq "assistant.message";
      my $data = $event->{data};
      next unless $data && ref($data) eq "HASH";
      my $requests = $data->{toolRequests};
      next unless $requests && ref($requests) eq "ARRAY";
      for my $request (@$requests) {
        next unless $request && ref($request) eq "HASH";
        push @request_indexes, $index
          if ($request->{toolCallId} // "") eq $call_id;
      }
    }
    if (@request_indexes > 1) {
      print "cancel:duplicate helper request identity\n";
      exit;
    }
    if (!@request_indexes) {
      print "wait\n";
      exit;
    }

    my $request_index = $request_indexes[0];
    my $request_event = $events[$request_index][1];
    my $request_data = $request_event->{data};
    my $requests = $request_data->{toolRequests};
    if (@$requests != 1) {
      print "cancel:helper request was batched with another tool\n";
      exit;
    }
    my $request = $requests->[0];
    my $arguments = $request->{arguments};
    my $command = $arguments && ref($arguments) eq "HASH"
      ? ($arguments->{command} // "")
      : "";
    my %allowed = map { $_ => 1 } (
      $helper,
      "'"'"'" . $helper . "'"'"'",
      "\"" . $helper . "\""
    );
    if (($request->{name} // "") ne "bash" || !$allowed{$command}) {
      print "cancel:helper request was not the canonical zero-argument command\n";
      exit;
    }

    my $turn_start = -1;
    for (my $index = $request_index; $index >= 0; $index--) {
      if (($events[$index][1]{type} // "") eq "assistant.turn_start") {
        $turn_start = $index;
        last;
      }
    }
    if ($turn_start < 0) {
      print "wait\n";
      exit;
    }

    my $brief = "";
    for my $index ($turn_start + 1 .. $request_index) {
      my $event = $events[$index][1];
      next unless ($event->{type} // "") eq "assistant.message";
      my $data = $event->{data};
      next unless $data && ref($data) eq "HASH";
      my $content = $data->{content};
      $brief = $content if defined $content && length $content;
    }
    if (
      $brief !~ /\ASELF_COMPACT_BRIEF\n/ ||
      $brief !~ /\nKeep:[ \t]*\S[^\n]*/ ||
      $brief !~ /\nDrop:[^\n]*/ ||
      $brief !~ /\nAfter compaction:[ \t]*\S[^\n]*do not compact again[^\n]*/
    ) {
      print "cancel:bound assistant turn has no complete SELF_COMPACT_BRIEF\n";
      exit;
    }

    my @starts;
    my @completions;
    for my $index (0 .. $#events) {
      my $event = $events[$index][1];
      my $data = $event->{data};
      next unless $data && ref($data) eq "HASH";
      next unless ($data->{toolCallId} // "") eq $call_id;
      push @starts, $index
        if ($event->{type} // "") eq "tool.execution_start";
      push @completions, $index
        if ($event->{type} // "") eq "tool.execution_complete";
    }
    if (@starts > 1 || @completions > 1) {
      print "cancel:duplicate helper execution identity\n";
      exit;
    }
    if (!@starts || $starts[0] <= $request_index) {
      print "wait\n";
      exit;
    }
    if (!@completions || $completions[0] <= $starts[0]) {
      print "wait\n";
      exit;
    }
    my $completion_index = $completions[0];

    my $authorizing_end = -1;
    for my $index ($completion_index + 1 .. $#events) {
      my $event = $events[$index][1];
      my $type = $event->{type} // "";
      if ($type eq "user.message") {
        print "cancel:user activity followed the helper request\n";
        exit;
      }
      if ($type eq "tool.execution_start") {
        print "cancel:new root tool activity followed helper completion\n";
        exit;
      }
      if ($type eq "assistant.message") {
        my $data = $event->{data};
        my $tool_requests = $data && ref($data) eq "HASH"
          ? $data->{toolRequests}
          : undef;
        if ($tool_requests && ref($tool_requests) eq "ARRAY" && @$tool_requests) {
          print "cancel:new root tool request followed helper completion\n";
          exit;
        }
      }
      if ($type eq "assistant.turn_start") {
        print "cancel:new root assistant turn began before the authorizing turn ended\n";
        exit;
      }
      if ($type eq "assistant.turn_end") {
        $authorizing_end = $index;
        last;
      }
    }
    if ($authorizing_end < 0) {
      print "wait\n";
      exit;
    }

    my $closure_start = -1;
    for my $index ($authorizing_end + 1 .. $#events) {
      my $event = $events[$index][1];
      my $type = $event->{type} // "";
      next unless $type eq "user.message" ||
        $type eq "assistant.turn_start" ||
        $type eq "tool.execution_start" ||
        $type eq "assistant.message";
      if ($type eq "user.message" || $type eq "tool.execution_start") {
        print "cancel:new root activity followed the authorizing turn\n";
        exit;
      }
      if ($type eq "assistant.message") {
        my $data = $event->{data};
        my $tool_requests = $data && ref($data) eq "HASH"
          ? $data->{toolRequests}
          : undef;
        if ($tool_requests && ref($tool_requests) eq "ARRAY" && @$tool_requests) {
          print "cancel:new root tool request followed the authorizing turn\n";
          exit;
        }
        next;
      }
      $closure_start = $index;
      last;
    }
    if ($closure_start < 0) {
      print "quiet:" . $events[$authorizing_end][0] . "\n";
      exit;
    }

    for my $index ($closure_start + 1 .. $#events) {
      my $event = $events[$index][1];
      my $type = $event->{type} // "";
      if ($type eq "user.message" || $type eq "tool.execution_start") {
        print "cancel:new root activity entered the closure turn\n";
        exit;
      }
      if ($type eq "assistant.turn_start") {
        print "cancel:a second root assistant turn began before submission\n";
        exit;
      }
      if ($type eq "assistant.message") {
        my $data = $event->{data};
        my $tool_requests = $data && ref($data) eq "HASH"
          ? $data->{toolRequests}
          : undef;
        if ($tool_requests && ref($tool_requests) eq "ARRAY" && @$tool_requests) {
          print "cancel:closure turn contained a tool request\n";
          exit;
        }
      }
      if ($type eq "assistant.turn_end") {
        print "ready:" . $events[$index][0] . "\n";
        exit;
      }
    }
    print "wait\n";
  ' "$EVENTS" "$TOOL_CALL_ID" "$HELPER_PATH"
}

auth_wait_milliseconds="$(sc_seconds_to_milliseconds "$AUTH_WAIT_SECONDS")" || {
  deferred_failure "invalid authorization wait"
  exit 1
}
quiescence_milliseconds="$(sc_seconds_to_milliseconds "$QUIESCENCE_GRACE_SECONDS")" || {
  deferred_failure "invalid quiescence grace"
  exit 1
}
auth_started="$(sc_epoch_milliseconds)"
case "$auth_started" in ''|*[!0-9]*) exit 1 ;; esac
auth_deadline=$((auth_started + auth_wait_milliseconds))
quiet_line=""
quiet_started=""
AUTH_EVENT_LINE=""
last_probe="handoff-pending"

while :; do
  if [ -e "$CANCELLED" ]; then
    deferred_failure "foreground cancelled before positive handoff"
    exit 1
  fi
  if handoff_matches; then
    probe="$(authorization_probe)"
    last_probe="$probe"
    case "$probe" in
      ready:*)
        AUTH_EVENT_LINE="${probe#ready:}"
        break
        ;;
      quiet:*)
        current_quiet_line="${probe#quiet:}"
        now="$(sc_epoch_milliseconds)"
        case "$now" in ''|*[!0-9]*) exit 1 ;; esac
        if [ "$quiet_line" != "$current_quiet_line" ]; then
          quiet_line="$current_quiet_line"
          quiet_started="$now"
        elif [ $((now - quiet_started)) -ge "$quiescence_milliseconds" ]; then
          AUTH_EVENT_LINE="$quiet_line"
          break
        fi
        ;;
      cancel:*)
        deferred_failure "${probe#cancel:}"
        exit 1
        ;;
      wait) ;;
      *)
        deferred_failure "authorization parser returned an invalid state"
        exit 1
        ;;
    esac
  fi
  now="$(sc_epoch_milliseconds)"
  case "$now" in ''|*[!0-9]*) exit 1 ;; esac
  if [ "$now" -ge "$auth_deadline" ]; then
    deferred_failure "timed out waiting for persisted brief authorization (last state: $last_probe)"
    exit 1
  fi
  sleep "$POLL_SECONDS"
done

if [ -e "$CANCELLED" ] || ! handoff_matches; then
  deferred_failure "positive handoff was lost before editor preparation"
  exit 1
fi

root_activity_exists() {
  awk -v after="$AUTH_EVENT_LINE" '
    NR > after &&
      $0 !~ /"agentId":"[^"]+"/ &&
      (/"type":"user.message"/ ||
       /"type":"assistant.turn_start"/ ||
       /"type":"tool.execution_start"/) {
        found = 1
        exit
      }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"
}

row_limit="$(sc_pane_one_row_limit)" || {
  deferred_failure "current pane width is unavailable before compact submission"
  exit 1
}
if ! sc_one_row_command_fits "$COMMAND" "$row_limit"; then
  deferred_failure "compact command no longer fits one safe editor row"
  exit 1
fi

prepare_status=0
sc_prepare_empty_editor root_activity_exists || prepare_status=$?
case "$prepare_status" in
  0) ;;
  10)
    deferred_failure "root-agent activity started before compact preparation"
    exit 1
    ;;
  *)
    deferred_failure "editor could not be proven empty"
    exit 1
    ;;
esac

HAD_DRAFT="$SC_PREPARE_HAD_DRAFT"
type_status=0
sc_type_literal "$COMMAND" root_activity_exists || type_status=$?
case "$type_status" in
  0) ;;
  10)
    deferred_failure "root-agent activity started before compact typing"
    exit 1
    ;;
  *)
    deferred_failure "could not type the compact command"
    exit 1
    ;;
esac

expected_hex="$(sc_literal_hex "$COMMAND")"
render_status=0
sc_wait_for_exact_render "$expected_hex" root_activity_exists || render_status=$?
case "$render_status" in
  0) ;;
  10)
    sc_cleanup_exact_command "$expected_hex"
    deferred_failure "root-agent activity started before compact Enter"
    exit 1
    ;;
  *)
    if [ "$HAD_DRAFT" = true ]; then
      sc_cleanup_exact_command "$expected_hex"
      deferred_failure "compact command was not exact and this run handled a draft"
      exit 1
    fi
    ambiguous_status=0
    SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS="$AMBIGUOUS_WAIT_SECONDS" \
      sc_wait_for_ambiguous_submit "$expected_hex" root_activity_exists ||
      ambiguous_status=$?
    case "$ambiguous_status" in
      0|2) ;;
      10)
        sc_cleanup_exact_command "$expected_hex"
        deferred_failure "root-agent activity started during the timed render wait"
        exit 1
        ;;
      *)
        sc_cleanup_exact_command "$expected_hex"
        deferred_failure "compact command rendered with a known mismatch"
        exit 1
        ;;
    esac
    ;;
esac

if root_activity_exists; then
  sc_cleanup_exact_command "$expected_hex"
  deferred_failure "root-agent activity started before compact Enter"
  exit 1
fi

BEFORE_EVENTS="$(wc -l < "$EVENTS" | tr -d '[:space:]')"
: > "$ARMED"
: > "$LOCK_DIR/armed"
RELEASE_LOCK=false
if ! "$TMUX_BIN" send-keys -t "$PANE" Enter; then
  sc_cleanup_exact_command "$expected_hex"
  deferred_failure "could not submit the compact command"
  exit 1
fi

event_line_after() {
  local after="$1"
  local event_type="$2"
  awk -v after="$after" -v event_type="$event_type" '
    NR > after &&
      $0 !~ /"agentId":"[^"]+"/ &&
      index($0, "\"type\":\"" event_type "\"") {
      print NR
      exit
    }
  ' "$EVENTS"
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
  deferred_failure "timed out waiting for the submitting turn end or compaction start"
  exit 1
fi

if [ -z "$compaction_start_line" ]; then
  start_grace_milliseconds="$(sc_seconds_to_milliseconds "$START_GRACE_SECONDS")" || exit 1
  start_now_milliseconds="$(sc_epoch_milliseconds)"
  case "$start_now_milliseconds" in ''|*[!0-9]*) exit 1 ;; esac
  start_deadline_milliseconds=$((start_now_milliseconds + start_grace_milliseconds))
  while :; do
    compaction_start_line="$(event_line_after "$BEFORE_EVENTS" session.compaction_start)"
    [ -n "$compaction_start_line" ] && break
    now_milliseconds="$(sc_epoch_milliseconds)"
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
  RELEASE_LOCK=true
  exit 1
fi

completion_line=""
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  completion_line="$(event_line_after "$compaction_start_line" session.compaction_complete)"
  [ -n "$completion_line" ] && break
  sleep "$POLL_SECONDS"
done
[ -n "$completion_line" ] || {
  deferred_failure "timed out waiting for session.compaction_complete"
  exit 1
}

completion_json="$(sed -n "${completion_line}p" "$EVENTS")"
checkpoint_number="$(
  printf '%s\n' "$completion_json" |
    /usr/bin/perl -MJSON::PP -e '
      my $line = <STDIN>;
      my $event = eval { decode_json($line) } or exit 1;
      exit 1 if defined $event->{agentId};
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
  RELEASE_LOCK=true
  exit 1
}

[ "$checkpoint_number" -gt "$BEFORE" ] || {
  echo "matching compact did not advance the checkpoint number" >&2
  RELEASE_LOCK=true
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
  RELEASE_LOCK=true
  exit 1
}

post_compact_activity_exists() {
  awk -v after="$completion_line" '
    NR > after &&
      $0 !~ /"agentId":"[^"]+"/ &&
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
  RELEASE_LOCK=true
  exit 0
fi

row_limit="$(sc_pane_one_row_limit)" || {
  echo "compact landed, but current pane width is unavailable; continuation not submitted" >&2
  RELEASE_LOCK=true
  exit 1
}
if ! sc_one_row_command_fits "$CONTINUATION" "$row_limit"; then
  echo "compact landed, but continuation no longer fits one safe editor row; continuation not submitted" >&2
  RELEASE_LOCK=true
  exit 1
fi

prepare_status=0
sc_prepare_verified_command "$CONTINUATION" post_compact_activity_exists ||
  prepare_status=$?
case "$prepare_status" in
  0) ;;
  10)
    echo "post-compact activity started during recovery; continuation not needed"
    RELEASE_LOCK=true
    exit 0
    ;;
  *)
    echo "compact landed, but continuation never rendered exactly" >&2
    RELEASE_LOCK=true
    exit 1
    ;;
esac

expected_hex="$(sc_literal_hex "$CONTINUATION")"
if post_compact_activity_exists; then
  sc_cleanup_exact_command "$expected_hex"
  echo "post-compact activity started before submission; continuation not needed"
  RELEASE_LOCK=true
  exit 0
fi

"$TMUX_BIN" send-keys -t "$PANE" Enter
for ((attempt = 1; attempt <= ${SELF_COMPACT_CONTINUATION_CONFIRM_POLLS:-100}; attempt++)); do
  if awk -v after="$completion_line" -v continuation="$CONTINUATION" '
    NR > after &&
      $0 !~ /"agentId":"[^"]+"/ &&
      /"type":"user.message"/ &&
      index($0, "\"content\":\"" continuation "\"") {
        found = 1
        exit
      }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"; then
    echo "submitted post-compact continuation after event line $completion_line"
    RELEASE_LOCK=true
    exit 0
  fi
  sleep "${SELF_COMPACT_CONTINUATION_CONFIRM_DELAY_SECONDS:-0.1}"
done

sc_cleanup_exact_command "$expected_hex"
echo "compact landed, but continuation submission was not confirmed" >&2
RELEASE_LOCK=true
exit 1
