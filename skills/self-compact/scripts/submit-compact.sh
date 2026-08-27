#!/usr/bin/env bash
# Bind one structured self_compact tool call to a detached SDK compaction request.

set -euo pipefail
umask 077

[ "$#" -eq 2 ] && [ "$1" = "--tool-call-id" ] || {
  echo "usage: submit-compact.sh --tool-call-id ID" >&2
  echo "submit-compact.sh: invoke through the self_compact extension tool" >&2
  exit 2
}
TOOL_CALL_ID="$2"
case "$TOOL_CALL_ID" in
  ''|*$'\n'*)
    echo "submit-compact.sh: tool-call identity is invalid; compact not submitted" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WATCHER="$SCRIPT_DIR/resume-after-compact.sh"
REQUEST_CLI="${SELF_COMPACT_REQUEST_CLI:-$SCRIPT_DIR/../../../extensions/session-inbox/request.mjs}"
SESSION_STATE_DIR="${SELF_COMPACT_SESSION_STATE_DIR:-$HOME/.copilot/session-state}"
TARGET_SESSION="${SELF_COMPACT_TARGET_SESSION:-${COPILOT_AGENT_SESSION_ID:-}}"
CONTINUATION="Compaction done; resume, do not compact."
AUTH_SCAN_BYTES="${SELF_COMPACT_AUTH_SCAN_BYTES:-67108864}"
SUBMIT_SCAN_BYTES="${SELF_COMPACT_SUBMIT_SCAN_BYTES:-1048576}"
REQUEST_TIMEOUT="${SELF_COMPACT_REQUEST_TIMEOUT_SECONDS:-1800}"
SUBMIT_POLLS="${SELF_COMPACT_SUBMIT_POLLS:-40}"
SUBMIT_POLL_SECONDS="${SELF_COMPACT_SUBMIT_POLL_SECONDS:-0.05}"

[ -x "$WATCHER" ] || {
  echo "submit-compact.sh: detached verifier is unavailable; compact not submitted" >&2
  exit 1
}
[ -r "$REQUEST_CLI" ] || {
  echo "submit-compact.sh: session-inbox request CLI is unavailable; compact not submitted" >&2
  exit 1
}
[ -n "$TARGET_SESSION" ] || {
  echo "submit-compact.sh: COPILOT_AGENT_SESSION_ID is unavailable; compact not submitted" >&2
  exit 1
}
case "$TARGET_SESSION" in
  *$'\n'*)
    echo "submit-compact.sh: target session ID is invalid; compact not submitted" >&2
    exit 1
    ;;
esac
case "$AUTH_SCAN_BYTES" in
  ''|*[!0-9]*)
    echo "submit-compact.sh: authorization scan bound must be an integer; compact not submitted" >&2
    exit 1
    ;;
esac
if [ "$AUTH_SCAN_BYTES" -lt 65536 ] || [ "$AUTH_SCAN_BYTES" -gt 67108864 ]; then
  echo "submit-compact.sh: authorization scan bound must be between 65536 and 67108864 bytes; compact not submitted" >&2
  exit 1
fi
case "$SUBMIT_SCAN_BYTES" in
  ''|*[!0-9]*)
    echo "submit-compact.sh: submit scan bound must be an integer; compact not submitted" >&2
    exit 1
    ;;
esac
if [ "$SUBMIT_SCAN_BYTES" -lt 65536 ] || [ "$SUBMIT_SCAN_BYTES" -gt 8388608 ]; then
  echo "submit-compact.sh: submit scan bound must be between 65536 and 8388608 bytes; compact not submitted" >&2
  exit 1
fi
case "$REQUEST_TIMEOUT" in
  ''|*[!0-9]*|0)
    echo "submit-compact.sh: request timeout must be a positive integer; compact not submitted" >&2
    exit 1
    ;;
esac
case "$SUBMIT_POLLS" in
  ''|*[!0-9]*|0)
    echo "submit-compact.sh: submit poll count must be a positive integer; compact not submitted" >&2
    exit 1
    ;;
esac
if [ "$SUBMIT_POLLS" -gt 200 ]; then
  echo "submit-compact.sh: submit poll count must not exceed 200; compact not submitted" >&2
  exit 1
fi
if ! awk -v seconds="$SUBMIT_POLL_SECONDS" 'BEGIN {
  exit !(seconds ~ /^[0-9]+([.][0-9]+)?$/ && seconds > 0 && seconds <= 1)
}'; then
  echo "submit-compact.sh: submit poll interval must be between 0 and 1 second; compact not submitted" >&2
  exit 1
fi

NODE_BIN="${SELF_COMPACT_NODE_BIN:-$(command -v node || true)}"
NOHUP_BIN="${SELF_COMPACT_NOHUP_BIN:-$(command -v nohup || true)}"
[ -x "$NODE_BIN" ] || {
  echo "submit-compact.sh: node is unavailable; compact not submitted" >&2
  exit 1
}
[ -x "$NOHUP_BIN" ] || {
  echo "submit-compact.sh: nohup is unavailable; compact not submitted" >&2
  exit 1
}

RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TOKEN="${SELF_COMPACT_RUN_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  checksum="$(
    printf '%s' "$(date -u +%s):$$:$RUN_STAMP" |
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

workspaces=()
if [ -n "${SELF_COMPACT_WORKSPACE:-}" ]; then
  workspaces+=("$SELF_COMPACT_WORKSPACE")
elif [ -r "$SESSION_STATE_DIR/$TARGET_SESSION/workspace.yaml" ]; then
  workspaces+=("$SESSION_STATE_DIR/$TARGET_SESSION/workspace.yaml")
else
  for workspace in "$SESSION_STATE_DIR"/*/workspace.yaml; do
    [ -r "$workspace" ] || continue
    workspace_cwd="$(
      awk -F': ' '/^cwd: / {sub(/[[:space:]]+$/, "", $2); print $2; exit}' \
        "$workspace"
    )"
    [ "$workspace_cwd" = "$PWD" ] || continue
    workspaces+=("$workspace")
  done
fi
[ "${#workspaces[@]}" -gt 0 ] || {
  echo "submit-compact.sh: could not find a candidate Copilot workspace; compact not submitted" >&2
  exit 1
}

scan_candidate() {
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($expected_call_id, $maximum, @workspaces) = @ARGV;
    $maximum =~ /^\d+$/ or die "invalid authorization scan bound\n";
    my @matches;

    for my $workspace (@workspaces) {
      (my $events_path = $workspace) =~ s{/workspace\.yaml$}{/events.jsonl}
        or next;
      next unless -r $events_path;
      open my $fh, "<", $events_path or die "cannot read $events_path\n";
      binmode $fh;
      my $size = (stat($fh))[7];
      defined $size or die "cannot stat $events_path\n";
      my $floor = $size > $maximum ? $size - $maximum : 0;
      seek($fh, $floor, 0) or die "cannot seek $events_path\n";
      read($fh, my $buffer, $size - $floor) == $size - $floor
        or die "cannot read authorization tail from $events_path\n";
      if ($floor > 0) {
        my $newline = index($buffer, "\n");
        next if $newline < 0;
        $buffer = substr($buffer, $newline + 1);
      }
      next if length($buffer) && substr($buffer, -1) ne "\n";

      my @events;
      for my $line (split /\n/, $buffer) {
        my $event = eval { decode_json($line) };
        die "malformed JSON in $events_path\n"
          unless $event && ref($event) eq "HASH";
        next if defined $event->{agentId};
        push @events, $event;
      }

      for my $request_index (0 .. $#events) {
        my $event = $events[$request_index];
        next unless ($event->{type} // "") eq "assistant.message";
        my $data = $event->{data};
        next unless $data && ref($data) eq "HASH";
        my $content = $data->{content};
        my $requests = $data->{toolRequests};
        next unless $requests && ref($requests) eq "ARRAY";

        for my $request (@$requests) {
          next unless $request && ref($request) eq "HASH";
          next unless ($request->{name} // "") eq "self_compact";
          next unless ($request->{toolCallId} // "") eq $expected_call_id;
          die "self_compact request exposed assistant prose\n"
            if defined($content) && (ref($content) || length($content));
          die "self_compact request was batched with another tool\n"
            unless @$requests == 1;
          my $arguments = $request->{arguments};
          my $call_id = $request->{toolCallId} // "";
          die "helper request has no tool-call identity\n" unless length $call_id;
          my $brief = $arguments && ref($arguments) eq "HASH"
            ? ($arguments->{brief} // "")
            : "";
          die "self_compact tool has no complete brief\n"
            unless !ref($brief) &&
              $brief =~ /\AKeep:[ \t]*\S[^\n]*/ &&
              $brief =~ /\nDrop:[^\n]*/ &&
              $brief =~ /\nAfter compaction:[ \t]*\S[^\n]*do not compact again[^\n]*/;

          my $turn_start = -1;
          for (my $index = $request_index; $index >= 0; $index--) {
            if (($events[$index]{type} // "") eq "assistant.turn_start") {
              $turn_start = $index;
              last;
            }
          }
          die "helper request has no containing assistant turn\n"
            if $turn_start < 0;

          for my $index ($turn_start + 1 .. $request_index - 1) {
            my $prior = $events[$index];
            my $type = $prior->{type} // "";
            die "conflicting root activity preceded the helper request\n"
              if $type eq "user.message" ||
                $type eq "assistant.turn_start" ||
                $type eq "assistant.turn_end" ||
                $type eq "tool.execution_start" ||
                $type eq "tool.execution_complete";
            if ($type eq "assistant.message") {
              my $prior_data = $prior->{data};
              my $prior_requests = $prior_data && ref($prior_data) eq "HASH"
                ? $prior_data->{toolRequests}
                : undef;
              die "another root tool request preceded the helper request\n"
                if $prior_requests && ref($prior_requests) eq "ARRAY" &&
                  @$prior_requests;
            }
          }

          my @starts;
          my @completions;
          for my $index (0 .. $#events) {
            my $candidate = $events[$index];
            my $candidate_data = $candidate->{data};
            next unless $candidate_data && ref($candidate_data) eq "HASH";
            next unless ($candidate_data->{toolCallId} // "") eq $call_id;
            push @starts, $index
              if ($candidate->{type} // "") eq "tool.execution_start";
            push @completions, $index
              if ($candidate->{type} // "") eq "tool.execution_complete";
          }
          next unless @starts == 1 && !@completions;
          my $start_index = $starts[0];
          next unless $start_index > $request_index;
          my $start_data = $events[$start_index]{data};
          next unless ($start_data->{toolName} // "") eq "self_compact";
          for my $index ($start_index + 1 .. $#events) {
            my $later = $events[$index];
            my $type = $later->{type} // "";
            die "root activity followed the running helper\n"
              if $type eq "user.message" ||
                $type eq "assistant.turn_start" ||
                $type eq "assistant.turn_end" ||
                $type eq "tool.execution_start" ||
                $type eq "tool.execution_complete";
            if ($type eq "assistant.message") {
              my $later_data = $later->{data};
              my $later_requests = $later_data && ref($later_data) eq "HASH"
                ? $later_data->{toolRequests}
                : undef;
              die "root tool request followed the running helper\n"
                if $later_requests && ref($later_requests) eq "ARRAY" &&
                  @$later_requests;
            }
          }

          push @matches, {
            workspace => $workspace,
            callId => $call_id,
            brief => $brief,
          };
        }
      }
    }

    die "could not bind one running canonical self-compact helper\n"
      unless @matches == 1;
    print encode_json($matches[0]);
  ' "$TOOL_CALL_ID" "$SUBMIT_SCAN_BYTES" \
    "${workspaces[@]}"
}

CANDIDATE_JSON=""
CANDIDATE_FOUND=false
for _ in $(seq 1 "$SUBMIT_POLLS"); do
  if CANDIDATE_JSON="$(scan_candidate 2>/dev/null)"; then
    CANDIDATE_FOUND=true
    break
  fi
  sleep "$SUBMIT_POLL_SECONDS"
done
if [ "$CANDIDATE_FOUND" = false ]; then
  scan_candidate >/dev/null || true
  echo "submit-compact.sh: current-turn authorization failed; compact not submitted" >&2
  exit 1
fi

WORKSPACE="$(
  printf '%s' "$CANDIDATE_JSON" |
    /usr/bin/perl -MJSON::PP -0777 -e '
      my $value = decode_json(<STDIN>);
      print $value->{workspace};
    '
)"
TOOL_CALL_ID="$(
  printf '%s' "$CANDIDATE_JSON" |
    /usr/bin/perl -MJSON::PP -0777 -e '
      my $value = decode_json(<STDIN>);
      print $value->{callId};
    '
)"
[ -r "$WORKSPACE" ] || {
  echo "submit-compact.sh: authorized workspace is unavailable; compact not submitted" >&2
  exit 1
}

SUMMARY_COUNT="$(
  awk -F': ' '/^summary_count: / {print $2; exit}' "$WORKSPACE"
)"
case "$SUMMARY_COUNT" in
  ''|*[!0-9]*)
    echo "submit-compact.sh: active session has no numeric summary_count; compact not submitted" >&2
    exit 1
    ;;
esac

FILES_DIR="${WORKSPACE%/workspace.yaml}/files"
EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"
[ -r "$EVENTS" ] || {
  echo "submit-compact.sh: active session event log is unavailable; compact not submitted" >&2
  exit 1
}
mkdir -p "$FILES_DIR"

RUN_ID="$RUN_STAMP-$$"
LOCK_DIR="$FILES_DIR/self-compact.lock"
LOCK_TOKEN="$TOKEN-$RUN_ID"
READY="$FILES_DIR/self-compact-$RUN_ID.ready"
HANDOFF="$FILES_DIR/self-compact-$RUN_ID.handoff"
INSTRUCTIONS="$FILES_DIR/self-compact-$RUN_ID.instructions"
CONTINUATION_FILE="$FILES_DIR/self-compact-$RUN_ID.continuation"
LOG="$FILES_DIR/self-compact-$RUN_ID.log"
CANDIDATE_FILE="$FILES_DIR/self-compact-$RUN_ID.candidate.json"

lock_state() {
  [ -r "$LOCK_DIR/state" ] && cat "$LOCK_DIR/state"
}

lock_token_matches() {
  [ -r "$LOCK_DIR/token" ] &&
    [ "$(cat "$LOCK_DIR/token")" = "$LOCK_TOKEN" ]
}

pid_is_live() {
  local pid="$1"
  case "$pid" in ''|*[!0-9]*|0|1) return 1 ;; esac
  kill -0 "$pid" >/dev/null 2>&1
}

reclaim_stale_foreground_lock() {
  local submitter
  [ -d "$LOCK_DIR" ] || return 1
  [ "$(lock_state)" = foreground ] || return 1
  [ -r "$LOCK_DIR/submitter.pid" ] || return 1
  [ ! -e "$LOCK_DIR/watcher.pid" ] || return 1
  submitter="$(cat "$LOCK_DIR/submitter.pid")"
  pid_is_live "$submitter" && return 1
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
printf '%s\n' foreground > "$LOCK_DIR/state"
printf '%s\n' "$CANDIDATE_JSON" > "$CANDIDATE_FILE"
/usr/bin/perl -MJSON::PP -0777 -e '
  use strict;
  use warnings;
  my ($candidate_path, $instructions_path, $token) = @ARGV;
  open my $candidate_fh, "<", $candidate_path or die "read candidate: $!";
  my $candidate = decode_json(do { local $/; <$candidate_fh> });
  open my $instructions_fh, ">", $instructions_path
    or die "write instructions: $!";
  print {$instructions_fh} $candidate->{brief},
    "\n\nSELF_COMPACT_RUN_TOKEN: ", $token;
' "$CANDIDATE_FILE" "$INSTRUCTIONS" "$TOKEN"
printf '%s' "$CONTINUATION" > "$CONTINUATION_FILE"
chmod 600 "$INSTRUCTIONS" "$CONTINUATION_FILE" "$CANDIDATE_FILE"

WATCHER_LAUNCHED=false
HANDOFF_COMPLETE=false
cleanup_foreground() {
  if [ "$WATCHER_LAUNCHED" = false ]; then
    rm -f "$READY" "$HANDOFF" "$INSTRUCTIONS" "$CONTINUATION_FILE" \
      "$CANDIDATE_FILE"
    if lock_token_matches && [ "$(lock_state)" = foreground ]; then
      rm -rf "$LOCK_DIR"
    fi
  elif [ "$HANDOFF_COMPLETE" = false ]; then
    : > "$LOCK_DIR/cancelled"
  fi
}
trap cleanup_foreground EXIT

"$NOHUP_BIN" "$WATCHER" \
  "$WORKSPACE" "$SUMMARY_COUNT" "$READY" "$HANDOFF" "$INSTRUCTIONS" \
  "$CONTINUATION_FILE" "$LOCK_DIR" "$LOCK_TOKEN" "$TOOL_CALL_ID" \
  "$TARGET_SESSION" "$NODE_BIN" "$REQUEST_CLI" "$REQUEST_TIMEOUT" "$LOG" \
  >> "$LOG" 2>&1 </dev/null &
WATCHER_PID=$!
WATCHER_LAUNCHED=true

for _ in $(seq 1 50); do
  [ -e "$READY" ] && break
  pid_is_live "$WATCHER_PID" || break
  sleep 0.1
done
[ -e "$READY" ] && pid_is_live "$WATCHER_PID" || {
  echo "submit-compact.sh: detached SDK verifier did not become ready; lock retained at $LOCK_DIR" >&2
  exit 1
}

printf '%s\n%s\n' "$LOCK_TOKEN" "$TOOL_CALL_ID" > "$HANDOFF.next"
mv "$HANDOFF.next" "$HANDOFF"
HANDOFF_COMPLETE=true
trap - EXIT

echo "self-compact handoff receipt: $LOCK_TOKEN"
echo "self-compact SDK verifier armed; foreground helper complete"
echo "watcher log: $LOG"
