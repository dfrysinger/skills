#!/usr/bin/env bash
# Authorize, submit, verify, and resume one token-bearing compact.

set -euo pipefail

[ "$#" -eq 21 ] || {
  echo "usage: resume-after-compact.sh PANE WORKSPACE BEFORE READY ARMED CANCELLED HANDOFF TOKEN CONTINUATION TMUX COMMAND CUSTOM_INSTRUCTIONS LOCK_DIR LOCK_TOKEN TOOL_CALL_ID HELPER_PATH LOG AMBIGUOUS_WAIT AUTH_WAIT QUIESCENCE_GRACE START_GRACE" >&2
  exit 2
}

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
START_GRACE_SECONDS="${21:?compaction start grace is required}"

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
AUTH_SCAN_BYTES="${SELF_COMPACT_AUTH_SCAN_BYTES:-65536}"
CHECKPOINTS_DIR="${WORKSPACE%/workspace.yaml}/checkpoints"
EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"
PORTABLE_HELPER_COMMAND=""
if [ -n "${HOME:-}" ]; then
  home_root="${HOME%/}"
  [ -n "$home_root" ] || home_root=/
  portable_helper_path="$home_root/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh"
  if [ "$HELPER_PATH" = "$portable_helper_path" ]; then
    PORTABLE_HELPER_COMMAND='"$HOME/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh"'
  fi
fi

deferred_failure() {
  local message="$1"
  echo "$message" >&2
  sc_notice "self-compact cancelled: $message; log: $LOG"
}

validate_positive_duration() {
  awk -v seconds="$1" -v maximum="$2" 'BEGIN {
    exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ &&
      seconds > 0 && seconds <= maximum)
  }'
}

validate_nonnegative_duration() {
  awk -v seconds="$1" -v maximum="$2" 'BEGIN {
    exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ &&
      seconds >= 0 && seconds <= maximum)
  }'
}

if ! validate_positive_duration "$POLL_SECONDS" 30; then
  deferred_failure "invalid verifier poll interval"
  exit 1
fi
if ! validate_nonnegative_duration "$RESUME_GRACE_SECONDS" 30; then
  deferred_failure "invalid resume grace"
  exit 1
fi
if ! validate_positive_duration "$START_GRACE_SECONDS" 30; then
  deferred_failure "invalid compaction start grace"
  exit 1
fi
if ! validate_positive_duration "$AUTH_WAIT_SECONDS" 30; then
  deferred_failure "invalid authorization wait"
  exit 1
fi
if ! validate_positive_duration "$QUIESCENCE_GRACE_SECONDS" 30; then
  deferred_failure "invalid quiescence grace"
  exit 1
fi
if ! sc_ambiguous_wait_is_bounded "$AMBIGUOUS_WAIT_SECONDS"; then
  deferred_failure "invalid ambiguous render wait"
  exit 1
fi
if ! awk -v quiet="$QUIESCENCE_GRACE_SECONDS" -v auth="$AUTH_WAIT_SECONDS" \
  'BEGIN { exit !(quiet < auth) }'; then
  deferred_failure "invalid quiescence grace: must be less than authorization wait"
  exit 1
fi
case "$MAX_POLLS" in
  ''|*[!0-9]*|0)
    deferred_failure "invalid verifier poll limit"
    exit 1
    ;;
esac
case "$AUTH_SCAN_BYTES" in
  ''|*[!0-9]*)
    deferred_failure "invalid authorization scan bound"
    exit 1
    ;;
esac
if [ "$AUTH_SCAN_BYTES" -lt 65536 ] || [ "$AUTH_SCAN_BYTES" -gt 67108864 ]; then
  deferred_failure "invalid authorization scan bound"
  exit 1
fi

: > "$LOCK_DIR/ready"
: > "$READY"

HANDOFF_EVENT_OFFSET=""
handoff_matches() {
  local actual prefix
  [ -r "$HANDOFF" ] || return 1
  actual="$(cat "$HANDOFF"; printf '\034')" || return 1
  prefix="$(printf '%s\n%s\n\034' "$LOCK_TOKEN" "$TOOL_CALL_ID")"
  prefix="${prefix%$'\034'}"
  case "$actual" in
    "$prefix"[0-9]*$'\n'$'\034') ;;
    *) return 1 ;;
  esac
  HANDOFF_EVENT_OFFSET="${actual#"$prefix"}"
  HANDOFF_EVENT_OFFSET="${HANDOFF_EVENT_OFFSET%$'\n'$'\034'}"
  case "$HANDOFF_EVENT_OFFSET" in ''|*[!0-9]*) return 1 ;; esac
}

authorization_probe() {
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my (
      $path, $call_id, $helper, $portable_helper,
      $maximum, $handoff, $lock_token
    ) = @ARGV;
    $maximum =~ /^\d+$/ && $handoff =~ /^\d+$/ or exit 2;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    my $size = (stat($fh))[7];
    defined $size or exit 2;
    my $floor = $size > $maximum ? $size - $maximum : 0;
    seek($fh, $floor, 0) or exit 2;
    read($fh, my $buffer, $size - $floor) == $size - $floor or exit 2;
    my $base = $floor;
    if ($floor > 0) {
      my $newline = index($buffer, "\n");
      if ($newline < 0) {
        print "cancel:authorization binding boundary exceeds bounded event tail\n";
        exit;
      }
      $buffer = substr($buffer, $newline + 1);
      $base += $newline + 1;
    }
    if (length($buffer) && substr($buffer, -1) ne "\n") {
      print "cancel:malformed JSON in authorization event region\n";
      exit;
    }
    my @events;
    my $offset = $base;
    for my $line (split /\n/, $buffer) {
      my $start = $offset;
      $offset += length($line) + 1;
      my $event = eval { decode_json($line) };
      if (!$event || ref($event) ne "HASH") {
        print "cancel:malformed JSON in authorization event region\n";
        exit;
      }
      next if defined $event->{agentId};
      push @events, [$start, $offset, $event];
    }

    my @request_indexes;
    for my $index (0 .. $#events) {
      my $event = $events[$index][2];
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
      print $floor > 0
        ? "cancel:authorization binding boundary exceeds bounded event tail\n"
        : "wait\n";
      exit;
    }

    my $request_index = $request_indexes[0];
    my $request_event = $events[$request_index][2];
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
    my @allowed = (
      $helper,
      "'"'"'" . $helper . "'"'"'",
      "\"" . $helper . "\""
    );
    push @allowed, $portable_helper if length $portable_helper;
    my %allowed = map { $_ => 1 } @allowed;
    if (($request->{name} // "") ne "bash" || !$allowed{$command}) {
      print "cancel:helper request was not the canonical zero-argument command\n";
      exit;
    }

    my $turn_start = -1;
    for (my $index = $request_index; $index >= 0; $index--) {
      if (($events[$index][2]{type} // "") eq "assistant.turn_start") {
        $turn_start = $index;
        last;
      }
    }
    if ($turn_start < 0) {
      print $floor > 0
        ? "cancel:authorization binding boundary exceeds bounded event tail\n"
        : "wait\n";
      exit;
    }
    for (my $index = $turn_start - 1; $index >= 0; $index--) {
      my $type = $events[$index][2]{type} // "";
      last if $type eq "assistant.turn_end";
      if ($type eq "assistant.turn_start") {
        print "cancel:selected helper began in an overlapping root assistant turn\n";
        exit;
      }
    }

    my $brief = "";
    for my $index ($turn_start + 1 .. $request_index) {
      my $event = $events[$index][2];
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

    for my $index ($turn_start + 1 .. $request_index - 1) {
      my $event = $events[$index][2];
      my $type = $event->{type} // "";
      if ($type eq "user.message" ||
        $type eq "assistant.turn_start" ||
        $type eq "tool.execution_start" ||
        $type eq "tool.execution_complete" ||
        $type eq "assistant.turn_end") {
        print "cancel:conflicting root activity preceded the helper request\n";
        exit;
      }
      if ($type eq "assistant.message") {
        my $data = $event->{data};
        my $tool_requests = $data && ref($data) eq "HASH"
          ? $data->{toolRequests}
          : undef;
        if ($tool_requests && ref($tool_requests) eq "ARRAY" && @$tool_requests) {
          print "cancel:another root tool request preceded the helper request\n";
          exit;
        }
      }
    }

    my @starts;
    my @completions;
    for my $index (0 .. $#events) {
      my $event = $events[$index][2];
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
    my $start_data = $events[$starts[0]][2]{data};
    if (!$start_data || ref($start_data) ne "HASH" ||
      ($start_data->{toolName} // "") ne "bash") {
      print "cancel:helper execution start was not Bash\n";
      exit;
    }
    if (@completions && $completions[0] <= $starts[0]) {
      print "cancel:helper completion preceded its execution start\n";
      exit;
    }
    if (!@completions) {
      print "wait\n";
      exit;
    }
    my $completion_index = $completions[0];
    if ($events[$completion_index][0] < $handoff) {
      print "cancel:selected helper completed before positive handoff\n";
      exit;
    }

    for my $index ($request_index + 1 .. $completion_index - 1) {
      my $event = $events[$index][2];
      my $type = $event->{type} // "";
      if ($type eq "user.message") {
        print "cancel:user activity followed the helper request\n";
        exit;
      }
      if ($type eq "assistant.turn_start" || $type eq "assistant.turn_end") {
        print "cancel:the authorizing turn changed before helper completion\n";
        exit;
      }
      if (
        ($type eq "tool.execution_start" && $index != $starts[0]) ||
        $type eq "tool.execution_complete"
      ) {
        print "cancel:conflicting root tool activity followed the helper request\n";
        exit;
      }
      if ($type eq "assistant.message") {
        my $data = $event->{data};
        my $tool_requests = $data && ref($data) eq "HASH"
          ? $data->{toolRequests}
          : undef;
        if ($tool_requests && ref($tool_requests) eq "ARRAY" && @$tool_requests) {
          print "cancel:new root tool request followed the helper request\n";
          exit;
        }
      }
    }

    my $completion_data = $events[$completion_index][2]{data};
    my $result = $completion_data && ref($completion_data) eq "HASH"
      ? $completion_data->{result}
      : undef;
    my $result_content = $result && ref($result) eq "HASH"
      ? $result->{content}
      : undef;
    if (defined $result_content && !ref($result_content) &&
      index($result_content, "self-compact handoff receipt:") >= 0) {
      my $expected = "self-compact handoff receipt: " . $lock_token;
      my $matched = grep { $_ eq $expected } split /\n/, $result_content;
      if (!$matched) {
        print "cancel:helper completion carried another foreground receipt\n";
        exit;
      }
    }

    my $authorizing_end = -1;
    for my $index ($completion_index + 1 .. $#events) {
      my $event = $events[$index][2];
      my $type = $event->{type} // "";
      if ($type eq "user.message") {
        print "cancel:user activity followed the helper request\n";
        exit;
      }
      if ($type eq "tool.execution_start" ||
        $type eq "tool.execution_complete") {
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
      my $event = $events[$index][2];
      my $type = $event->{type} // "";
      next unless $type eq "user.message" ||
        $type eq "assistant.turn_start" ||
        $type eq "tool.execution_start" ||
        $type eq "tool.execution_complete" ||
        $type eq "assistant.message";
      if ($type eq "user.message" ||
        $type eq "tool.execution_start" ||
        $type eq "tool.execution_complete") {
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
      print "quiet:" . $events[$authorizing_end][1] . "\n";
      exit;
    }

    for my $index ($closure_start + 1 .. $#events) {
      my $event = $events[$index][2];
      my $type = $event->{type} // "";
      if ($type eq "user.message" ||
        $type eq "tool.execution_start" ||
        $type eq "tool.execution_complete") {
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
        print "ready:" . $events[$index][1] . "\n";
        exit;
      }
    }
    print "wait\n";
  ' "$EVENTS" "$TOOL_CALL_ID" "$HELPER_PATH" "$PORTABLE_HELPER_COMMAND" \
    "$AUTH_SCAN_BYTES" "$HANDOFF_EVENT_OFFSET" "$LOCK_TOKEN"
}

auth_wait_milliseconds="$(sc_seconds_to_milliseconds "$AUTH_WAIT_SECONDS")" || {
  deferred_failure "invalid authorization wait"
  exit 1
}
quiescence_milliseconds="$(sc_seconds_to_milliseconds "$QUIESCENCE_GRACE_SECONDS")" || {
  deferred_failure "invalid quiescence grace"
  exit 1
}

read_epoch_milliseconds() {
  local value
  value="$(sc_epoch_milliseconds)" || return 1
  case "$value" in ''|*[!0-9]*) return 1 ;; esac
  [ "${#value}" -le 15 ] || return 1
  printf '%s\n' "$value"
}

event_log_size() {
  /usr/bin/perl -e '
    my $size = -s $ARGV[0];
    defined $size or exit 1;
    print $size;
  ' "$EVENTS"
}

auth_started="$(read_epoch_milliseconds)" || {
  deferred_failure "invalid authorization clock value"
  exit 1
}
auth_deadline=$((auth_started + auth_wait_milliseconds))
quiet_offset=""
quiet_started=""
AUTH_EVENT_OFFSET=""
last_probe="handoff-pending"

while :; do
  if [ -e "$CANCELLED" ]; then
    deferred_failure "foreground cancelled before positive handoff"
    exit 1
  fi
  if handoff_matches; then
    probe_status=0
    probe="$(authorization_probe)" || probe_status=$?
    if [ "$probe_status" -ne 0 ]; then
      deferred_failure "authorization parser failed with status $probe_status"
      exit 1
    fi
    last_probe="$probe"
    case "$probe" in
      ready:*)
        AUTH_EVENT_OFFSET="${probe#ready:}"
        break
        ;;
      quiet:*)
        current_quiet_offset="${probe#quiet:}"
        now="$(read_epoch_milliseconds)" || {
          deferred_failure "invalid quiescence clock value"
          exit 1
        }
        if [ "$quiet_offset" != "$current_quiet_offset" ]; then
          quiet_offset="$current_quiet_offset"
          quiet_started="$now"
        elif [ $((now - quiet_started)) -ge "$quiescence_milliseconds" ]; then
          AUTH_EVENT_OFFSET="$quiet_offset"
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
  now="$(read_epoch_milliseconds)" || {
    deferred_failure "invalid authorization clock value"
    exit 1
  }
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

semantic_activity_after() {
  local after="$1"
  local mode="$2"
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $after, $maximum, $mode) = @ARGV;
    $after =~ /^\d+$/ && $maximum =~ /^\d+$/ or exit 2;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    my $size = (stat($fh))[7];
    defined $size && $size >= $after or exit 2;
    exit 3 if $size - $after > $maximum;
    seek($fh, $after, 0) or exit 2;
    while (my $line = <$fh>) {
      exit 2 if substr($line, -1) ne "\n";
      my $event = eval { decode_json($line) };
      exit 2 unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      my $type = $event->{type} // "";
      if ($type eq "user.message" || $type eq "assistant.turn_start") {
        print "activity\n";
        exit;
      }
      if ($mode eq "authorization") {
        if ($type eq "tool.execution_start" ||
          $type eq "tool.execution_complete") {
          print "activity\n";
          exit;
        }
        if ($type eq "assistant.message") {
          my $data = $event->{data};
          my $requests = $data && ref($data) eq "HASH"
            ? $data->{toolRequests}
            : undef;
          if ($requests && ref($requests) eq "ARRAY" && @$requests) {
            print "activity\n";
            exit;
          }
        }
      }
    }
    print "clear\n";
  ' "$EVENTS" "$after" "$AUTH_SCAN_BYTES" "$mode"
}

root_activity_exists() {
  local result status=0
  result="$(semantic_activity_after "$AUTH_EVENT_OFFSET" authorization)" ||
    status=$?
  [ "$status" -eq 0 ] && [ "$result" = clear ] && return 1
  return 0
}

row_limit="$(sc_pane_one_row_limit)" || {
  deferred_failure "current pane width is unavailable before compact submission"
  exit 1
}
if ! sc_one_row_command_fits "$COMMAND" "$row_limit"; then
  deferred_failure "compact command no longer fits one safe editor row"
  exit 1
fi
if [ -e "$CANCELLED" ] || ! handoff_matches; then
  deferred_failure "positive handoff was lost before editor preparation"
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

BEFORE_EVENT_OFFSET="$(event_log_size)" || {
  deferred_failure "could not snapshot the pre-submit event boundary"
  exit 1
}
: > "$ARMED"
: > "$LOCK_DIR/armed"
RELEASE_LOCK=false
enter_failed=false
if ! "$TMUX_BIN" send-keys -t "$PANE" Enter; then
  sc_cleanup_exact_command "$expected_hex"
  echo "compact Enter returned nonzero; observing the compaction-start deadline" >&2
  enter_failed=true
fi

STREAM_STATE=""
STREAM_CURSOR=""
STREAM_START=""
STREAM_END=""
STREAM_ERROR=""

stream_event_probe() {
  local cursor="$1"
  local mode="$2"
  local expected="${3:-}"
  local output status=0
  STREAM_ERROR=""
  output="$(
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $cursor, $mode, $expected) = @ARGV;
    $cursor =~ /^\d+$/ or exit 2;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    my $size = (stat($fh))[7];
    defined $size && $size >= $cursor or exit 2;
    seek($fh, $cursor, 0) or exit 2;

    my $buffer = "";
    my $buffer_start = $cursor;
    my $maximum_line = 16 * 1024 * 1024;
    my $remaining = $size - $cursor;
    while ($remaining > 0) {
      my $take = $remaining > 65536 ? 65536 : $remaining;
      my $read = sysread($fh, my $chunk, $take);
      defined $read or exit 3;
      $read > 0 or exit 3;
      $remaining -= $read;
      $buffer .= $chunk;
      while ((my $newline = index($buffer, "\n")) >= 0) {
        exit 5 if $newline > $maximum_line;
        my $line = substr($buffer, 0, $newline, "");
        substr($buffer, 0, 1, "");
        my $start = $buffer_start;
        my $end = $start + $newline + 1;
        $buffer_start = $end;
        my $event = eval { decode_json($line) };
        exit 4 unless $event && ref($event) eq "HASH";
        next if defined $event->{agentId};
        my $type = $event->{type} // "";
        my $state = "";
        if ($mode eq "submit") {
          $state = "start" if $type eq "session.compaction_start";
          $state = "turn-end" if $type eq "assistant.turn_end";
        } elsif ($mode eq "start") {
          $state = "start" if $type eq "session.compaction_start";
        } elsif ($mode eq "completion") {
          $state = "completion" if $type eq "session.compaction_complete";
        } elsif ($mode eq "post") {
          $state = "activity"
            if $type eq "user.message" || $type eq "assistant.turn_start";
        } elsif ($mode eq "continuation") {
          if ($type eq "assistant.turn_start") {
            $state = "activity";
          } elsif ($type eq "user.message") {
            my $data = $event->{data};
            my $content = $data && ref($data) eq "HASH"
              ? $data->{content}
              : $event->{content};
            $state = defined $content && !ref($content) &&
              $content eq $expected
              ? "continuation"
              : "mismatch";
          }
        } else {
          exit 2;
        }
        if (length $state) {
          print join("\t", $state, $end, $start, $end), "\n";
          exit;
        }
      }
      exit 5 if length($buffer) > $maximum_line;
    }
    print join("\t", "none", $buffer_start, "", ""), "\n";
  ' "$EVENTS" "$cursor" "$mode" "$expected"
  )" || status=$?
  if [ "$status" -ne 0 ]; then
    STREAM_STATE=error
    STREAM_CURSOR="$cursor"
    STREAM_START=""
    STREAM_END=""
    case "$status" in
      2) STREAM_ERROR="invalid reader boundary or mode" ;;
      3) STREAM_ERROR="event log read failure" ;;
      4) STREAM_ERROR="malformed event JSON" ;;
      5) STREAM_ERROR="event line exceeded the reader bound" ;;
      *) STREAM_ERROR="status $status" ;;
    esac
    return 0
  fi
  IFS=$'\t' read -r \
    STREAM_STATE STREAM_CURSOR STREAM_START STREAM_END <<< "$output"
  case "$STREAM_STATE" in
    none|start|turn-end|completion|activity|continuation|mismatch) ;;
    *)
      STREAM_STATE=error
      STREAM_ERROR="invalid reader state"
      return 0
      ;;
  esac
  case "$STREAM_CURSOR" in
    ''|*[!0-9]*)
      STREAM_STATE=error
      STREAM_ERROR="invalid reader cursor"
      ;;
  esac
  if [ "$STREAM_STATE" != none ]; then
    for event_bound in "$STREAM_START" "$STREAM_END"; do
      case "$event_bound" in
        ''|*[!0-9]*)
          STREAM_STATE=error
          STREAM_ERROR="invalid reader event bounds"
          break
          ;;
      esac
    done
  fi
}

read_event_at_offset() {
  local offset="$1"
  /usr/bin/perl -e '
    my ($path, $offset) = @ARGV;
    $offset =~ /^\d+$/ or exit 1;
    open my $fh, "<", $path or exit 1;
    binmode $fh;
    seek($fh, $offset, 0) or exit 1;
    my $line = <$fh>;
    defined $line && substr($line, -1) eq "\n" or exit 1;
    print $line;
  ' "$EVENTS" "$offset"
}

post_armed_parser_failure() {
  local message="$1"
  RELEASE_LOCK=true
  echo "$message" >&2
  "$TMUX_BIN" display-message \
    -d "${SELF_COMPACT_NOTICE_MILLISECONDS:-10000}" -t "$PANE" \
    "self-compact cancelled: $message; log: $LOG" >/dev/null 2>&1 || true
  exit 1
}

compaction_start_record=""
turn_end_record=""
LIFECYCLE_CURSOR="$BEFORE_EVENT_OFFSET"
if [ "$enter_failed" = false ]; then
  for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
    stream_event_probe "$LIFECYCLE_CURSOR" submit
    [ "$STREAM_STATE" = error ] &&
      post_armed_parser_failure \
        "could not inspect submitting lifecycle events ($STREAM_ERROR)"
    LIFECYCLE_CURSOR="$STREAM_CURSOR"
    case "$STREAM_STATE" in
      start)
        compaction_start_record="$STREAM_START:$STREAM_END"
        break
        ;;
      turn-end)
        turn_end_record="$STREAM_START:$STREAM_END"
        break
        ;;
    esac
    sleep "$POLL_SECONDS"
  done

  if [ -z "$compaction_start_record" ] && [ -z "$turn_end_record" ]; then
    deferred_failure "timed out waiting for the submitting turn end or compaction start"
    exit 1
  fi
else
  turn_end_record=enter-failed
fi

if [ -z "$compaction_start_record" ]; then
  start_grace_milliseconds="$(sc_seconds_to_milliseconds "$START_GRACE_SECONDS")" || {
    deferred_failure "invalid compaction start grace"
    exit 1
  }
  start_now_milliseconds="$(read_epoch_milliseconds)" || {
    deferred_failure "invalid compaction start clock value"
    exit 1
  }
  start_deadline_milliseconds=$((start_now_milliseconds + start_grace_milliseconds))
  while :; do
    stream_event_probe "$LIFECYCLE_CURSOR" start
    [ "$STREAM_STATE" = error ] &&
      post_armed_parser_failure \
        "could not inspect compaction start events ($STREAM_ERROR)"
    LIFECYCLE_CURSOR="$STREAM_CURSOR"
    if [ "$STREAM_STATE" = start ]; then
      compaction_start_record="$STREAM_START:$STREAM_END"
      break
    fi
    now_milliseconds="$(read_epoch_milliseconds)" || {
      deferred_failure "invalid compaction start clock value"
      exit 1
    }
    if [ "$now_milliseconds" -ge "$start_deadline_milliseconds" ]; then
      stream_event_probe "$LIFECYCLE_CURSOR" start
      [ "$STREAM_STATE" = error ] &&
        post_armed_parser_failure \
          "could not inspect compaction start events ($STREAM_ERROR)"
      LIFECYCLE_CURSOR="$STREAM_CURSOR"
      if [ "$STREAM_STATE" = start ]; then
        compaction_start_record="$STREAM_START:$STREAM_END"
      fi
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

if [ -z "$compaction_start_record" ]; then
  sc_cleanup_exact_command "$(sc_literal_hex "$COMMAND")"
  sc_notice "self-compact: compaction did not start; cancelled"
  echo "compaction did not start within ${START_GRACE_SECONDS}s after assistant.turn_end" >&2
  RELEASE_LOCK=true
  exit 1
fi

compaction_start_end_offset="${compaction_start_record#*:}"
completion_record=""
COMPLETION_CURSOR="$compaction_start_end_offset"
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  stream_event_probe "$COMPLETION_CURSOR" completion
  [ "$STREAM_STATE" = error ] &&
    post_armed_parser_failure \
      "could not inspect compaction completion events ($STREAM_ERROR)"
  COMPLETION_CURSOR="$STREAM_CURSOR"
  if [ "$STREAM_STATE" = completion ]; then
    completion_record="$STREAM_START:$STREAM_END"
    break
  fi
  sleep "$POLL_SECONDS"
done
[ -n "$completion_record" ] || {
  deferred_failure "timed out waiting for session.compaction_complete"
  exit 1
}

completion_offset="${completion_record%%:*}"
completion_end_offset="${completion_record#*:}"
completion_json="$(read_event_at_offset "$completion_offset")" || {
  post_armed_parser_failure \
    "could not read the matched compaction completion event"
}
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

POST_ACTIVITY_CURSOR="$completion_end_offset"
POST_ACTIVITY_FOUND=false
POST_ACTIVITY_PARSE_ERROR=""

post_compact_activity_exists() {
  [ "$POST_ACTIVITY_FOUND" = false ] || return 0
  [ -z "$POST_ACTIVITY_PARSE_ERROR" ] || return 0
  stream_event_probe "$POST_ACTIVITY_CURSOR" post
  if [ "$STREAM_STATE" = error ]; then
    POST_ACTIVITY_PARSE_ERROR="$STREAM_ERROR"
    return 0
  fi
  POST_ACTIVITY_CURSOR="$STREAM_CURSOR"
  if [ "$STREAM_STATE" = activity ]; then
    POST_ACTIVITY_FOUND=true
    return 0
  fi
  return 1
}

handle_post_compact_activity() {
  local activity_message="$1"
  if [ -n "$POST_ACTIVITY_PARSE_ERROR" ]; then
    post_armed_parser_failure \
      "could not inspect post-compact activity ($POST_ACTIVITY_PARSE_ERROR)"
  fi
  echo "$activity_message"
  RELEASE_LOCK=true
  exit 0
}

sleep "$RESUME_GRACE_SECONDS"
if post_compact_activity_exists; then
  handle_post_compact_activity \
    "post-compact activity already present after event offset $completion_end_offset; continuation not needed"
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
    handle_post_compact_activity \
      "post-compact activity started during recovery; continuation not needed"
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
  handle_post_compact_activity \
    "post-compact activity started before submission; continuation not needed"
fi

CONTINUATION_CURSOR="$POST_ACTIVITY_CURSOR"
continuation_enter_status=0
"$TMUX_BIN" send-keys -t "$PANE" Enter || continuation_enter_status=$?
if [ "$continuation_enter_status" -ne 0 ]; then
  sc_cleanup_exact_command "$expected_hex"
  sc_capture_state || true
  if [ "$SC_PREPARE_HAD_DRAFT" = true ] && sc_state_is_empty; then
    "$TMUX_BIN" send-keys -t "$PANE" C-s || true
  fi
  echo "compact landed, but continuation Enter returned status $continuation_enter_status" >&2
  sc_notice "self-compact: compact landed but continuation Enter failed; log: $LOG"
  RELEASE_LOCK=true
  exit 1
fi

CONTINUATION_CONFIRM_POLLS="${SELF_COMPACT_CONTINUATION_CONFIRM_POLLS:-100}"
CONTINUATION_CONFIRM_DELAY_SECONDS="${SELF_COMPACT_CONTINUATION_CONFIRM_DELAY_SECONDS:-0.1}"
case "$CONTINUATION_CONFIRM_POLLS" in
  ''|*[!0-9]*|0)
    echo "compact landed, but continuation confirmation poll limit is invalid" >&2
    RELEASE_LOCK=true
    exit 1
    ;;
esac
if ! validate_positive_duration "$CONTINUATION_CONFIRM_DELAY_SECONDS" 5; then
  echo "compact landed, but continuation confirmation delay is invalid" >&2
  RELEASE_LOCK=true
  exit 1
fi

for ((attempt = 1; attempt <= CONTINUATION_CONFIRM_POLLS; attempt++)); do
  stream_event_probe "$CONTINUATION_CURSOR" continuation "$CONTINUATION"
  if [ "$STREAM_STATE" = error ]; then
    echo "compact landed, but continuation confirmation parsing failed ($STREAM_ERROR)" >&2
    RELEASE_LOCK=true
    exit 1
  fi
  CONTINUATION_CURSOR="$STREAM_CURSOR"
  if [ "$STREAM_STATE" = continuation ]; then
    echo "submitted post-compact continuation after event offset $completion_end_offset"
    RELEASE_LOCK=true
    exit 0
  fi
  if [ "$STREAM_STATE" = mismatch ] || [ "$STREAM_STATE" = activity ]; then
    echo "compact landed, but another root activity won continuation confirmation" >&2
    RELEASE_LOCK=true
    exit 1
  fi
  sleep "$CONTINUATION_CONFIRM_DELAY_SECONDS"
done

sc_cleanup_exact_command "$expected_hex"
echo "compact landed, but continuation submission was not confirmed" >&2
RELEASE_LOCK=true
exit 1
