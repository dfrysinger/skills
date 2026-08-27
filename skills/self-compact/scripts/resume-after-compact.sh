#!/usr/bin/env bash
# Submit and verify one session-inbox compaction after the authorizing turn ends.

set -euo pipefail
umask 077

[ "$#" -eq 14 ] || {
  echo "usage: resume-after-compact.sh WORKSPACE BEFORE READY HANDOFF INSTRUCTIONS CONTINUATION LOCK_DIR LOCK_TOKEN TOOL_CALL_ID TARGET_SESSION NODE REQUEST_CLI TIMEOUT LOG" >&2
  exit 2
}

WORKSPACE="${1:?workspace is required}"
BEFORE="${2:?baseline summary_count is required}"
READY="${3:?ready path is required}"
HANDOFF="${4:?handoff path is required}"
INSTRUCTIONS="${5:?instructions path is required}"
CONTINUATION_FILE="${6:?continuation path is required}"
LOCK_DIR="${7:?lock directory is required}"
LOCK_TOKEN="${8:?lock token is required}"
TOOL_CALL_ID="${9:?tool-call identity is required}"
TARGET_SESSION="${10:?target session is required}"
NODE_BIN="${11:?node path is required}"
REQUEST_CLI="${12:?request CLI path is required}"
REQUEST_TIMEOUT="${13:?request timeout is required}"
LOG="${14:?log path is required}"

EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"
CHECKPOINTS_DIR="${WORKSPACE%/workspace.yaml}/checkpoints"
POLL_SECONDS="${SELF_COMPACT_POLL_SECONDS:-0.25}"
MAX_POLLS="${SELF_COMPACT_MAX_POLLS:-7200}"
AUTH_WAIT_SECONDS="${SELF_COMPACT_AUTH_WAIT_SECONDS:-180}"
AUTH_SCAN_BYTES="${SELF_COMPACT_AUTH_SCAN_BYTES:-67108864}"

lock_token_matches() {
  [ -r "$LOCK_DIR/token" ] &&
    [ "$(cat "$LOCK_DIR/token")" = "$LOCK_TOKEN" ]
}

write_lock_state() {
  printf '%s\n' "$1" > "$LOCK_DIR/state.next"
  mv "$LOCK_DIR/state.next" "$LOCK_DIR/state"
}

RELEASE_LOCK=true
cleanup() {
  rm -f "$READY" "$HANDOFF"
  if [ "$RELEASE_LOCK" = true ]; then
    rm -f "$INSTRUCTIONS" "$CONTINUATION_FILE" \
      "${INSTRUCTIONS%.instructions}.candidate.json"
    if lock_token_matches; then
      rm -rf "$LOCK_DIR"
    fi
  fi
}
trap cleanup EXIT

fail() {
  echo "self-compact cancelled: $*" >&2
  exit 1
}

case "$BEFORE" in ''|*[!0-9]*) fail "invalid baseline summary_count" ;; esac
case "$MAX_POLLS" in ''|*[!0-9]*|0) fail "invalid verifier poll limit" ;; esac
case "$REQUEST_TIMEOUT" in ''|*[!0-9]*|0) fail "invalid request timeout" ;; esac
case "$AUTH_SCAN_BYTES" in ''|*[!0-9]*) fail "invalid authorization scan bound" ;; esac
if ! awk -v seconds="$POLL_SECONDS" 'BEGIN {
  exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ && seconds > 0 && seconds <= 30)
}'; then
  fail "invalid verifier poll interval"
fi
if ! awk -v seconds="$AUTH_WAIT_SECONDS" 'BEGIN {
  exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ && seconds > 0 && seconds <= 180)
}'; then
  fail "invalid authorization wait"
fi

lock_token_matches || fail "watcher lock token mismatch"
[ -r "$EVENTS" ] || fail "session event log is unavailable"
[ -r "$INSTRUCTIONS" ] || fail "bound compaction instructions are unavailable"
[ -r "$CONTINUATION_FILE" ] || fail "continuation prompt is unavailable"
[ -x "$NODE_BIN" ] || fail "node is unavailable"
[ -r "$REQUEST_CLI" ] || fail "session-inbox request CLI is unavailable"

printf '%s\n' "$$" > "$LOCK_DIR/watcher.pid"
write_lock_state watcher-owned
: > "$READY"

handoff_matches() {
  [ -r "$HANDOFF" ] &&
    [ "$(sed -n '1p' "$HANDOFF")" = "$LOCK_TOKEN" ] &&
    [ "$(sed -n '2p' "$HANDOFF")" = "$TOOL_CALL_ID" ] &&
    [ "$(wc -l < "$HANDOFF" | tr -d '[:space:]')" = 2 ]
}

authorization_probe() {
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $call_id, $receipt, $maximum) = @ARGV;
    $maximum =~ /^\d+$/ or exit 2;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    my $size = (stat($fh))[7];
    defined $size or exit 2;
    my $floor = $size > $maximum ? $size - $maximum : 0;
    seek($fh, $floor, 0) or exit 2;
    read($fh, my $buffer, $size - $floor) == $size - $floor or exit 2;
    if ($floor > 0) {
      my $newline = index($buffer, "\n");
      if ($newline < 0) {
        print "cancel:authorization boundary exceeds event tail\n";
        exit;
      }
      $buffer = substr($buffer, $newline + 1);
    }
    if (length($buffer) && substr($buffer, -1) ne "\n") {
      print "wait\n";
      exit;
    }
    my @events;
    for my $line (split /\n/, $buffer) {
      my $event = eval { decode_json($line) };
      unless ($event && ref($event) eq "HASH") {
        print "cancel:malformed authorization event JSON\n";
        exit;
      }
      next if defined $event->{agentId};
      push @events, $event;
    }

    my (@starts, @completions);
    for my $index (0 .. $#events) {
      my $event = $events[$index];
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
    unless (@starts == 1 && @completions == 1) {
      print "wait\n";
      exit;
    }
    my ($start, $completion) = ($starts[0], $completions[0]);
    unless ($completion > $start) {
      print "cancel:helper completion preceded execution start\n";
      exit;
    }

    for my $index ($start + 1 .. $completion - 1) {
      my $event = $events[$index];
      my $type = $event->{type} // "";
      if ($type eq "user.message" ||
          $type eq "assistant.turn_start" ||
          $type eq "assistant.turn_end" ||
          $type eq "tool.execution_start" ||
          $type eq "tool.execution_complete") {
        print "cancel:conflicting root activity occurred during helper execution\n";
        exit;
      }
    }

    my $completion_data = $events[$completion]{data};
    my $result = $completion_data->{result};
    my $content = $result && ref($result) eq "HASH"
      ? $result->{content}
      : undef;
    unless (defined $content && !ref($content)) {
      print "wait\n";
      exit;
    }
    my $matched = grep { $_ eq $receipt } split /\n/, $content;
    unless ($matched) {
      print "cancel:helper completion carried no matching handoff receipt\n";
      exit;
    }

    my $saw_turn_end = 0;
    my $assistant_turn_open = 0;
    for my $index ($completion + 1 .. $#events) {
      my $event = $events[$index];
      my $type = $event->{type} // "";
      if ($type eq "assistant.turn_start") {
        $assistant_turn_open = 1;
        next;
      }
      if ($type eq "assistant.turn_end") {
        $assistant_turn_open = 0;
        $saw_turn_end = 1;
        next;
      }
      if ($type eq "user.message" ||
          $type eq "tool.execution_start" ||
          $type eq "tool.execution_complete") {
        print "cancel:new root activity followed helper completion\n";
        exit;
      }
      if ($type eq "assistant.message") {
        my $data = $event->{data};
        my $requests = $data && ref($data) eq "HASH"
          ? $data->{toolRequests}
          : undef;
        if ($requests && ref($requests) eq "ARRAY" && @$requests) {
          print "cancel:new root tool request followed helper completion\n";
          exit;
        }
      }
    }
    unless ($saw_turn_end && !$assistant_turn_open) {
      print "wait\n";
      exit;
    }
    print "ready\n";
  ' "$EVENTS" "$TOOL_CALL_ID" \
    "self-compact handoff receipt: $LOCK_TOKEN" "$AUTH_SCAN_BYTES"
}

for _ in $(seq 1 100); do
  [ ! -e "$LOCK_DIR/cancelled" ] || fail "foreground cancelled before handoff"
  handoff_matches && break
  sleep 0.05
done
handoff_matches || fail "positive handoff was not established"

auth_polls="$(
  awk -v wait="$AUTH_WAIT_SECONDS" -v poll="$POLL_SECONDS" \
    'BEGIN { print int(wait / poll) + 1 }'
)"
for _ in $(seq 1 "$auth_polls"); do
  probe="$(authorization_probe)" || fail "authorization parser failed"
  case "$probe" in
    ready) break ;;
    wait) ;;
    cancel:*) fail "${probe#cancel:}" ;;
    *) fail "authorization parser returned an invalid state" ;;
  esac
  sleep "$POLL_SECONDS"
done
[ "${probe:-}" = ready ] || fail "timed out waiting for the authorizing turn to end"

BEFORE_EVENT_OFFSET="$(
  /usr/bin/perl -e '
    my $size = -s $ARGV[0];
    defined $size or exit 1;
    print $size;
  ' "$EVENTS"
)" || fail "could not snapshot the pre-request event boundary"

echo "submitting one session-inbox compact request for session $TARGET_SESSION"
RELEASE_LOCK=false
request_status=0
request_output="$(
  "$NODE_BIN" "$REQUEST_CLI" compact \
    --target-session "$TARGET_SESSION" \
    --instructions-file "$INSTRUCTIONS" \
    --continuation-file "$CONTINUATION_FILE" \
    --dedupe-key "self-compact:$TARGET_SESSION:$LOCK_TOKEN" \
    --timeout "$REQUEST_TIMEOUT" 2>&1
)" || request_status=$?
printf '%s\n' "$request_output"

if [ "$request_status" -ne 0 ] &&
  ! grep -q '^request: ' <<<"$request_output"; then
  RELEASE_LOCK=true
  fail "session-inbox rejected the compact request before publication"
fi

if [ "$request_status" -eq 1 ]; then
  ambiguous_side_effect="$(
    printf '%s\n' "$request_output" |
      /usr/bin/perl -MJSON::PP -ne '
        my $value = eval { decode_json($_) };
        next unless $value && ref($value) eq "HASH";
        if (($value->{status} // "") eq "failed" &&
            ($value->{ambiguousSideEffect} // 0)) {
          print "yes";
          exit;
        }
      '
  )"
  [ "$ambiguous_side_effect" != yes ] ||
    fail "extension exited during compact execution; outcome is ambiguous and lock retained at $LOCK_DIR"

  post_compact_failure="$(
    printf '%s\n' "$request_output" |
      /usr/bin/perl -MJSON::PP -ne '
        my $value = eval { decode_json($_) };
        next unless $value && ref($value) eq "HASH";
        my $result = $value->{result};
        if (($value->{status} // "") eq "failed" &&
            ($value->{sideEffectCompleted} // 0) &&
            $result && ref($result) eq "HASH" &&
            ($result->{compacted} // 0)) {
          print "yes";
          exit;
        }
      '
  )"
  if [ "$post_compact_failure" = yes ]; then
    request_status=0
  else
    RELEASE_LOCK=true
    fail "session-inbox reported a failed compact request"
  fi
fi
if [ "$request_status" -ne 0 ]; then
  fail "session-inbox compact request outcome is ambiguous (status $request_status); lock retained at $LOCK_DIR"
fi

receipt_state="$(
  printf '%s\n' "$request_output" |
    TARGET_SESSION="$TARGET_SESSION" /usr/bin/perl -MJSON::PP -e '
      use strict;
      use warnings;
      my $valid = 0;
      my $continuation = "unknown";
      while (my $line = <STDIN>) {
        my $value = eval { decode_json($line) };
        next unless $value && ref($value) eq "HASH";
        next unless ($value->{sessionId} // "") eq $ENV{TARGET_SESSION};
        my $result = $value->{result};
        my $completed = ($value->{status} // "") eq "completed";
        my $completed_side_effect =
          ($value->{status} // "") eq "failed" &&
          ($value->{sideEffectCompleted} // 0) &&
          $result && ref($result) eq "HASH" &&
          ($result->{compacted} // 0);
        next unless $completed || $completed_side_effect;
        $valid = 1;
        if ($result && ref($result) eq "HASH" &&
            exists $result->{continuationDelivered}) {
          $continuation = $result->{continuationDelivered} ? "delivered" : "failed";
        } elsif ($result && ref($result) eq "HASH" &&
                 ($result->{continuationQueued} // 0)) {
          $continuation = "queued";
        }
      }
      print $valid ? "completed\t$continuation" : "invalid";
    '
)"
case "$receipt_state" in
  completed$'\t'delivered) CONTINUATION_RECEIPT=delivered ;;
  completed$'\t'queued) CONTINUATION_RECEIPT=queued ;;
  completed$'\t'failed) CONTINUATION_RECEIPT=failed ;;
  completed$'\t'unknown) CONTINUATION_RECEIPT=unknown ;;
  *) CONTINUATION_RECEIPT=invalid ;;
esac
[ "$CONTINUATION_RECEIPT" != invalid ] ||
  fail "session-inbox returned no matching completed receipt; lock retained at $LOCK_DIR"

CUSTOM_INSTRUCTIONS="$(cat "$INSTRUCTIONS")"
completion_probe() {
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $offset, $instructions) = @ARGV;
    $offset =~ /^\d+$/ or exit 2;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    my $size = (stat($fh))[7];
    defined $size && $size >= $offset or exit 2;
    seek($fh, $offset, 0) or exit 2;
    my $cursor = $offset;
    while (my $line = <$fh>) {
      my $start = $cursor;
      $cursor += length($line);
      next unless substr($line, -1) eq "\n";
      my $event = eval { decode_json($line) };
      exit 3 unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      next unless ($event->{type} // "") eq "session.compaction_complete";
      my $data = $event->{data} && ref($event->{data}) eq "HASH"
        ? $event->{data}
        : $event;
      next unless defined $data->{customInstructions} &&
        !ref($data->{customInstructions}) &&
        $data->{customInstructions} eq $instructions;
      if (!($data->{success} // 0)) {
        print "failed\n";
        exit;
      }
      if (!defined $data->{checkpointNumber} ||
        $data->{checkpointNumber} !~ /^\d+$/) {
        print "invalid\n";
        exit;
      }
      print "success\t", $data->{checkpointNumber}, "\t", $cursor, "\n";
      exit;
    }
    print "wait\n";
  ' "$EVENTS" "$BEFORE_EVENT_OFFSET" "$CUSTOM_INSTRUCTIONS"
}

completion=""
for _ in $(seq 1 "$MAX_POLLS"); do
  completion="$(completion_probe)" || fail "could not inspect compaction completion events"
  case "$completion" in
    success$'\t'*) break ;;
    failed)
      RELEASE_LOCK=true
      fail "matching compaction completion reported failure"
      ;;
    invalid)
      fail "matching compaction completion had no checkpoint number"
      ;;
    wait) ;;
    *) fail "compaction completion parser returned an invalid state" ;;
  esac
  sleep "$POLL_SECONDS"
done
case "$completion" in
  success$'\t'*) ;;
  *) fail "matching token-bound compaction completion was not observed; lock retained at $LOCK_DIR" ;;
esac

IFS=$'\t' read -r _ CHECKPOINT_NUMBER COMPLETION_END <<< "$completion"
[ "$CHECKPOINT_NUMBER" -gt "$BEFORE" ] ||
  fail "matching compaction did not advance the checkpoint number"

checkpoint_landed=false
for _ in $(seq 1 "$MAX_POLLS"); do
  current="$(
    awk -F': ' '/^summary_count: / {print $2; exit}' "$WORKSPACE" 2>/dev/null ||
      true
  )"
  case "$current" in
    ''|*[!0-9]*) ;;
    *)
      if [ "$current" -ge "$CHECKPOINT_NUMBER" ]; then
        checkpoint_prefix="$(printf '%03d-' "$CHECKPOINT_NUMBER")"
        if [ -d "$CHECKPOINTS_DIR" ]; then
          checkpoint_count="$(
            find "$CHECKPOINTS_DIR" -maxdepth 1 -type f \
              -name "${checkpoint_prefix}*.md" -print |
              wc -l |
              tr -d '[:space:]'
          )"
        else
          checkpoint_count=0
        fi
        if [ "$checkpoint_count" -eq 1 ]; then
          checkpoint_landed=true
          break
        fi
      fi
      ;;
  esac
  sleep "$POLL_SECONDS"
done
[ "$checkpoint_landed" = true ] ||
  fail "matching compact did not produce exactly one checkpoint file for checkpoint $CHECKPOINT_NUMBER"

[ "$CONTINUATION_RECEIPT" != failed ] ||
  fail "compact succeeded but the SDK continuation was not delivered; lock retained at $LOCK_DIR"

CONTINUATION="$(cat "$CONTINUATION_FILE")"
continuation_probe() {
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $offset, $expected) = @ARGV;
    $offset =~ /^\d+$/ or exit 2;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    seek($fh, $offset, 0) or exit 2;
    my $matches = 0;
    while (my $line = <$fh>) {
      next unless substr($line, -1) eq "\n";
      my $event = eval { decode_json($line) };
      exit 3 unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      my $type = $event->{type} // "";
      if ($type eq "user.message") {
        my $data = $event->{data};
        my $content = $data && ref($data) eq "HASH"
          ? $data->{content}
          : $event->{content};
        if (defined $content && !ref($content) && $content eq $expected) {
          my $delivery = $data && ref($data) eq "HASH"
            ? ($data->{delivery} // "")
            : "";
          if ($delivery ne "idle" && $delivery ne "queued") {
            print "mismatch\n";
            exit;
          }
          $matches++;
          next;
        }
        print "mismatch\n";
        exit;
      }
      if ($type eq "assistant.turn_start" && !$matches) {
        print "activity\n";
        exit;
      }
    }
    print $matches == 1 ? "success\n" :
      $matches > 1 ? "duplicate\n" : "wait\n";
  ' "$EVENTS" "$COMPLETION_END" "$CONTINUATION"
}

continuation_state=""
for _ in $(seq 1 "$MAX_POLLS"); do
  continuation_state="$(continuation_probe)" ||
    fail "could not inspect continuation events"
  case "$continuation_state" in
    success) break ;;
    wait) ;;
    duplicate) fail "session-inbox delivered the continuation more than once" ;;
    mismatch|activity) fail "other root activity won the continuation race" ;;
    *) fail "continuation parser returned an invalid state" ;;
  esac
  sleep "$POLL_SECONDS"
done
[ "$continuation_state" = success ] ||
  fail "matching compact landed without the fixed continuation"

RELEASE_LOCK=true
echo "verified token-bound compaction checkpoint $CHECKPOINT_NUMBER and one SDK continuation"
