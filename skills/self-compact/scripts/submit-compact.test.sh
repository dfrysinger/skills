#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_ROOT="$SCRIPT_DIR/.submit-compact-test.$$"
FAKE_BIN="$TEST_ROOT/bin"

cleanup() {
  local pid_file pid
  while IFS= read -r pid_file; do
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    case "$pid" in ''|*[!0-9]*) continue ;; esac
    [ "$pid" != "$$" ] || continue
    kill -0 "$pid" >/dev/null 2>&1 || continue
    kill "$pid" >/dev/null 2>&1 || true
  done < <(find "$TEST_ROOT" -path '*/self-compact.lock/watcher.pid' -type f 2>/dev/null)
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT
mkdir -p "$FAKE_BIN"

fail() {
  echo "submit-compact test: $*" >&2
  exit 1
}

assert_count() {
  local expected="$1"
  local pattern="$2"
  local path="$3"
  local actual
  actual="$(grep -cE "$pattern" "$path" 2>/dev/null || true)"
  [ "$actual" -eq "$expected" ] ||
    fail "expected $expected matches for [$pattern] in $path, got $actual"
}

wait_for_log() {
  local pattern="$1"
  local log="$2"
  for _ in $(seq 1 1500); do
    grep -qE "$pattern" "$log" 2>/dev/null && return 0
    sleep 0.01
  done
  echo "--- $log" >&2
  cat "$log" >&2 || true
  echo "--- events" >&2
  cat "$FAKE_EVENTS" >&2 || true
  fail "timed out waiting for [$pattern]"
}

wait_for_absent() {
  local path="$1"
  for _ in $(seq 1 300); do
    [ ! -e "$path" ] && return 0
    sleep 0.01
  done
  fail "timed out waiting for $path to be removed"
}

cat > "$FAKE_BIN/tmux" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "tmux called: $*" >> "$FAKE_TMUX_CALLS"
exit 99
EOF
chmod +x "$FAKE_BIN/tmux"

cat > "$FAKE_BIN/node" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
request_cli="${1:?request CLI is required}"
shift
exec "$request_cli" "$@"
EOF
chmod +x "$FAKE_BIN/node"

cat > "$FAKE_BIN/request.mjs" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

[ "${1:-}" = compact ] || exit 64
shift
target=""
instructions=""
continuation=""
timeout=""
dedupe=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-session) target="$2"; shift 2 ;;
    --instructions-file) instructions="$2"; shift 2 ;;
    --continuation-file) continuation="$2"; shift 2 ;;
    --timeout) timeout="$2"; shift 2 ;;
    --dedupe-key) dedupe="$2"; shift 2 ;;
    *) exit 64 ;;
  esac
done

count=0
[ ! -s "$FAKE_REQUEST_COUNT" ] || count="$(cat "$FAKE_REQUEST_COUNT")"
count=$((count + 1))
printf '%s\n' "$count" > "$FAKE_REQUEST_COUNT"
cp "$instructions" "$FAKE_CAPTURED_INSTRUCTIONS"
cp "$continuation" "$FAKE_CAPTURED_CONTINUATION"
printf 'target=%s\ntimeout=%s\ndedupe=%s\n' \
  "$target" "$timeout" "$dedupe" > "$FAKE_CAPTURED_ARGUMENTS"

case "${FAKE_REQUEST_MODE:-success}" in
  failed)
    printf '%s\n' \
      'request: fake' \
      "{\"id\":\"fake\",\"status\":\"failed\",\"sessionId\":\"$target\",\"error\":\"forced failure\"}"
    exit 1
    ;;
  timeout)
    printf '%s\n' 'request: fake' >&2
    exit 2
    ;;
  preflight)
    printf '%s\n' 'session-inbox-request: no fresh session-inbox instance' >&2
    exit 64
    ;;
  ambiguous-side-effect)
    printf '%s\n' \
      'request: fake' \
      "{\"id\":\"fake\",\"status\":\"failed\",\"sessionId\":\"$target\",\"ambiguousSideEffect\":true,\"error\":\"extension exited while executing\"}"
    exit 1
    ;;
esac

custom_instructions="$(cat "$instructions")"
event_instructions="$custom_instructions"
[ "${FAKE_REQUEST_MODE:-success}" != wrong-token ] ||
  event_instructions="${custom_instructions%????????}deadbeef"
CUSTOM_INSTRUCTIONS="$event_instructions" /usr/bin/perl -MJSON::PP -e '
  print encode_json({
    agentId => undef,
    type => "session.compaction_complete",
    data => {
      success => JSON::PP::true,
      customInstructions => $ENV{CUSTOM_INSTRUCTIONS},
      checkpointNumber => 2,
    },
  }), "\n";
' >> "$FAKE_EVENTS"

awk '
  /^summary_count: / { print "summary_count: 2"; next }
  { print }
' "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.next"
mv "$FAKE_WORKSPACE.next" "$FAKE_WORKSPACE"
if [ "${FAKE_REQUEST_MODE:-success}" != missing-checkpoint ]; then
  mkdir -p "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints"
  printf '%s\n' "checkpoint" > \
    "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/002-test.md"
fi
if [ "${FAKE_REQUEST_MODE:-success}" = wrong-continuation ]; then
  continuation_text="different continuation"
else
  continuation_text="$(cat "$continuation")"
fi
if [ "${FAKE_REQUEST_MODE:-success}" != continuation-failed ]; then
  CONTENT="$continuation_text" /usr/bin/perl -MJSON::PP -e '
    print encode_json({
      agentId => undef,
      type => "user.message",
      data => {content => $ENV{CONTENT}, delivery => "idle"},
    }), "\n";
  ' >> "$FAKE_EVENTS"
fi

continuation_delivered=true
[ "${FAKE_REQUEST_MODE:-success}" != continuation-failed ] ||
  continuation_delivered=false
receipt_status=completed
receipt_extra=""
receipt_exit=0
if [ "${FAKE_REQUEST_MODE:-success}" = post-compact-receipt-failed ]; then
  receipt_status=failed
  receipt_extra=',"sideEffectCompleted":true'
  receipt_exit=1
fi
printf '%s\n' \
  'request: fake' \
  'receipt: fake' \
  "{\"id\":\"fake\",\"status\":\"$receipt_status\",\"sessionId\":\"$target\"$receipt_extra,\"result\":{\"compacted\":true,\"tokensRemoved\":10,\"messagesRemoved\":2,\"continuationDelivered\":$continuation_delivered}}"
exit "$receipt_exit"
EOF
chmod +x "$FAKE_BIN/request.mjs"

setup_case() {
  local name="$1"
  FAKE_CASE="$TEST_ROOT/$name"
  FAKE_WORKSPACE="$FAKE_CASE/session/workspace.yaml"
  FAKE_EVENTS="$FAKE_CASE/session/events.jsonl"
  FAKE_REQUEST_COUNT="$FAKE_CASE/request-count"
  FAKE_CAPTURED_INSTRUCTIONS="$FAKE_CASE/instructions"
  FAKE_CAPTURED_CONTINUATION="$FAKE_CASE/continuation"
  FAKE_CAPTURED_ARGUMENTS="$FAKE_CASE/arguments"
  FAKE_TMUX_CALLS="$FAKE_CASE/tmux-calls"
  FAKE_DRAFT="$FAKE_CASE/draft"
  FAKE_TOOL_CALL_ID="call-self-compact-$name"
  mkdir -p "$FAKE_CASE/session/files"
  cat > "$FAKE_WORKSPACE" <<EOF
id: workspace-$name
cwd: $PWD
summary_count: 1
EOF
  : > "$FAKE_EVENTS"
  : > "$FAKE_REQUEST_COUNT"
  : > "$FAKE_TMUX_CALLS"
  printf '%s\n' "unsubmitted user draft" > "$FAKE_DRAFT"
  unset FAKE_REQUEST_MODE
  export FAKE_CASE FAKE_WORKSPACE FAKE_EVENTS FAKE_REQUEST_COUNT
  export FAKE_CAPTURED_INSTRUCTIONS FAKE_CAPTURED_CONTINUATION
  export FAKE_CAPTURED_ARGUMENTS FAKE_TMUX_CALLS FAKE_DRAFT
  export FAKE_TOOL_CALL_ID
}

append_authorizing_events() {
  local brief="$1"
  local mode="${2:-canonical}"
  BRIEF="$brief" MODE="$mode" \
    TOOL_CALL_ID="$FAKE_TOOL_CALL_ID" /usr/bin/perl -MJSON::PP -e '
      my @requests = ({
        toolCallId => $ENV{TOOL_CALL_ID},
        name => ($ENV{MODE} eq "wrong-tool" ? "bash" : "self_compact"),
        arguments => {brief => $ENV{BRIEF}},
      });
      push @requests, {
        toolCallId => "other-call",
        name => "bash",
        arguments => {command => "true"},
      } if $ENV{MODE} eq "batched";
      print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
      print encode_json({
        agentId => undef,
        type => "assistant.message",
        data => {
          content => ($ENV{MODE} eq "visible-brief" ? $ENV{BRIEF} : ""),
          toolRequests => \@requests,
        },
      }), "\n";
      print encode_json({
        agentId => undef,
        type => "tool.execution_start",
        data => {
          toolCallId => $ENV{TOOL_CALL_ID},
          toolName => ($ENV{MODE} eq "wrong-tool" ? "bash" : "self_compact"),
        },
      }), "\n";
    ' >> "$FAKE_EVENTS"
}

append_completed_prose_turn() {
  /usr/bin/perl -MJSON::PP -e '
    print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
    print encode_json({
      agentId => undef,
      type => "assistant.message",
      data => {content => "ordinary prior response", toolRequests => []},
    }), "\n";
    print encode_json({agentId => undef, type => "assistant.turn_end"}), "\n";
  ' >> "$FAKE_EVENTS"
}

complete_authorizing_turn() {
  local receipt="$1"
  RECEIPT="$receipt" TOOL_CALL_ID="$FAKE_TOOL_CALL_ID" \
    /usr/bin/perl -MJSON::PP -e '
      print encode_json({
        agentId => undef,
        type => "tool.execution_complete",
        data => {
          toolCallId => $ENV{TOOL_CALL_ID},
          result => {content => $ENV{RECEIPT}},
        },
      }), "\n";
      print encode_json({agentId => undef, type => "assistant.turn_end"}), "\n";
      print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
      print encode_json({
        agentId => undef,
        type => "assistant.message",
        data => {content => "", toolRequests => []},
      }), "\n";
      print encode_json({agentId => undef, type => "assistant.turn_end"}), "\n";
    ' >> "$FAKE_EVENTS"
}

complete_authorizing_turn_with_autopilot_nudge() {
  local receipt="$1"
  local batch="$FAKE_CASE/turn-end-with-autopilot-nudge.jsonl"
  RECEIPT="$receipt" TOOL_CALL_ID="$FAKE_TOOL_CALL_ID" \
    /usr/bin/perl -MJSON::PP -e '
      print encode_json({
        agentId => undef,
        type => "tool.execution_complete",
        data => {
          toolCallId => $ENV{TOOL_CALL_ID},
          result => {content => $ENV{RECEIPT}},
        },
      }), "\n";
      print encode_json({agentId => undef, type => "assistant.turn_end"}), "\n";
      # Autopilot injects a continuation nudge as a root user message the moment
      # the arming turn ends, then the agent produces one brief response turn.
      print encode_json({
        agentId => undef,
        type => "user.message",
        data => {
          content => "",
          delivery => "idle",
          isAutopilotContinuation => JSON::PP::true,
          source => "autopilot",
        },
      }), "\n";
      print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
      print encode_json({
        agentId => undef,
        type => "assistant.message",
        data => {content => "", toolRequests => []},
      }), "\n";
      print encode_json({agentId => undef, type => "assistant.turn_end"}), "\n";
    ' > "$batch"
  cat "$batch" >> "$FAKE_EVENTS"
}

run_submit() {
  local call_id="${1:-$FAKE_TOOL_CALL_ID}"
  local output status=0
  output="$(
    PATH="$FAKE_BIN:$PATH" \
      COPILOT_AGENT_SESSION_ID="target-session" \
      SELF_COMPACT_WORKSPACE="$FAKE_WORKSPACE" \
      SELF_COMPACT_NODE_BIN="$FAKE_BIN/node" \
      SELF_COMPACT_REQUEST_CLI="$FAKE_BIN/request.mjs" \
      SELF_COMPACT_RUN_TOKEN=0123abcd \
      SELF_COMPACT_SUBMIT_POLLS=1 \
      SELF_COMPACT_SUBMIT_POLL_SECONDS=0.01 \
      SELF_COMPACT_AUTH_WAIT_SECONDS=2 \
      SELF_COMPACT_POLL_SECONDS=0.01 \
      SELF_COMPACT_MAX_POLLS=100 \
      SELF_COMPACT_REQUEST_TIMEOUT_SECONDS=3 \
      "$SCRIPT_DIR/submit-compact.sh" \
        --tool-call-id "$call_id" 2>&1
  )" || status=$?
  printf '%s\n' "$output"
  return "$status"
}

brief=$'Keep: active baton\n\nDrop: resolved detail\n\nAfter compaction: continue the task; do not compact again.'

# The SDK path preserves the exact brief, adds one token binding, leaves drafts
# untouched, logs the receipt, verifies the checkpoint, and sends one continuation.
setup_case success
append_authorizing_events "$brief"
output="$(run_submit)" || fail "success case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
[ -n "$lock_token" ] && [ -n "$log" ] || fail "missing handoff output"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'verified token-bound compaction checkpoint 2 and one SDK continuation' "$log"
expected_instructions="${brief}"$'\n\nSELF_COMPACT_RUN_TOKEN: 0123abcd'
[ "$(cat "$FAKE_CAPTURED_INSTRUCTIONS")" = "$expected_instructions" ] ||
  fail "exact brief and token binding were not preserved"
[ "$(cat "$FAKE_CAPTURED_CONTINUATION")" = "Compaction done; resume, do not compact." ] ||
  fail "fixed continuation changed"
grep -q '^target=target-session$' "$FAKE_CAPTURED_ARGUMENTS" ||
  fail "request did not target the current SDK session"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"
[ "$(cat "$FAKE_DRAFT")" = "unsubmitted user draft" ] ||
  fail "draft changed"
[ ! -s "$FAKE_TMUX_CALLS" ] || fail "self-compact called tmux"
grep -q '"status":"completed"' "$log" || fail "completed receipt was not logged"
! grep -Fq 'active baton' "$log" || fail "brief leaked into the verifier log"
wait_for_absent "$FAKE_CASE/session/files/self-compact.lock"

# Ordinary assistant prose from an earlier completed turn does not block the
# later empty-content self_compact authorization.
setup_case prior-prose
append_completed_prose_turn
append_authorizing_events "$brief"
output="$(run_submit)" || fail "prior prose blocked the matching tool request"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'verified token-bound compaction checkpoint 2 and one SDK continuation' "$log"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"
wait_for_absent "$FAKE_CASE/session/files/self-compact.lock"

# Malformed or noncanonical current-turn authorization never creates a request.
setup_case malformed-brief
append_authorizing_events $'Keep:\nDrop: x\nAfter compaction: do not compact again.'
if run_submit >/dev/null; then
  fail "malformed brief was accepted"
fi
[ ! -s "$FAKE_REQUEST_COUNT" ] || fail "malformed brief created a request"

setup_case wrong-tool
append_authorizing_events "$brief" wrong-tool
if run_submit >/dev/null; then
  fail "wrong tool was accepted"
fi
[ ! -s "$FAKE_REQUEST_COUNT" ] || fail "wrong tool created a request"

setup_case wrong-tool-call
append_authorizing_events "$brief"
if run_submit other-call-id >/dev/null; then
  fail "wrong tool-call identity was accepted"
fi
[ ! -s "$FAKE_REQUEST_COUNT" ] || fail "wrong tool-call identity created a request"

setup_case visible-brief
append_authorizing_events "$brief" visible-brief
if run_submit >/dev/null; then
  fail "brief duplicated into assistant prose was accepted"
fi
[ ! -s "$FAKE_REQUEST_COUNT" ] || fail "visible brief created a request"

setup_case batched
append_authorizing_events "$brief" batched
if run_submit >/dev/null; then
  fail "batched helper request was accepted"
fi
[ ! -s "$FAKE_REQUEST_COUNT" ] || fail "batched helper created a request"

# Autopilot continuation nudges (and any other root activity) after the arming
# turn no longer cancel the run: the SDK request is idle-gated and simply waits
# for the next idle boundary, so self-compact completes under autopilot.
setup_case autopilot-nudge
append_authorizing_events "$brief"
output="$(run_submit)" || fail "autopilot-nudge case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn_with_autopilot_nudge "self-compact handoff receipt: $lock_token"
wait_for_log 'verified token-bound compaction checkpoint 2 and one SDK continuation' "$log"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"
wait_for_absent "$FAKE_CASE/session/files/self-compact.lock"

# A live or ambiguous per-session owner excludes a second run.
setup_case run-exclusion
mkdir "$FAKE_CASE/session/files/self-compact.lock"
printf '%s\n' watcher-owned > "$FAKE_CASE/session/files/self-compact.lock/state"
printf '%s\n' "$$" > "$FAKE_CASE/session/files/self-compact.lock/watcher.pid"
printf '%s\n' existing > "$FAKE_CASE/session/files/self-compact.lock/token"
append_authorizing_events "$brief"
if run_submit >/dev/null; then
  fail "concurrent self-compact run was accepted"
fi
[ ! -s "$FAKE_REQUEST_COUNT" ] || fail "excluded run created a request"

# A definitive failed receipt releases exclusion; an ambiguous timeout retains it.
setup_case failed-request
export FAKE_REQUEST_MODE=failed
append_authorizing_events "$brief"
output="$(run_submit)" || fail "failed-request case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'session-inbox reported a failed compact request' "$log"
wait_for_absent "$FAKE_CASE/session/files/self-compact.lock"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"

setup_case timeout
export FAKE_REQUEST_MODE=timeout
append_authorizing_events "$brief"
output="$(run_submit)" || fail "timeout case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'outcome is ambiguous .* lock retained' "$log"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "ambiguous request did not retain exclusion"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"

setup_case preflight
export FAKE_REQUEST_MODE=preflight
append_authorizing_events "$brief"
output="$(run_submit)" || fail "preflight case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'rejected the compact request before publication' "$log"
wait_for_absent "$FAKE_CASE/session/files/self-compact.lock"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"

setup_case ambiguous-side-effect
export FAKE_REQUEST_MODE=ambiguous-side-effect
append_authorizing_events "$brief"
output="$(run_submit)" || fail "ambiguous-side-effect case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'extension exited during compact execution' "$log"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "ambiguous side effect did not retain exclusion"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"

setup_case post-compact-receipt-failed
export FAKE_REQUEST_MODE=post-compact-receipt-failed
append_authorizing_events "$brief"
output="$(run_submit)" || fail "post-compact receipt failure case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'verified token-bound compaction checkpoint 2 and one SDK continuation' "$log"
wait_for_absent "$FAKE_CASE/session/files/self-compact.lock"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"

# A completed request must still prove the token-bound event, checkpoint, and wake.
setup_case wrong-token
export FAKE_REQUEST_MODE=wrong-token
append_authorizing_events "$brief"
output="$(run_submit)" || fail "wrong-token case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'matching token-bound compaction completion was not observed' "$log"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "unbound completion did not retain exclusion"

setup_case missing-checkpoint
export FAKE_REQUEST_MODE=missing-checkpoint
append_authorizing_events "$brief"
output="$(run_submit)" || fail "missing-checkpoint case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'did not produce exactly one checkpoint file' "$log"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "missing checkpoint did not retain exclusion"

setup_case wrong-continuation
export FAKE_REQUEST_MODE=wrong-continuation
append_authorizing_events "$brief"
output="$(run_submit)" || fail "wrong-continuation case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'matching compact landed without the fixed continuation' "$log"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "wrong continuation did not retain exclusion"

setup_case continuation-failed
export FAKE_REQUEST_MODE=continuation-failed
append_authorizing_events "$brief"
output="$(run_submit)" || fail "continuation-failed case did not arm"
lock_token="$(printf '%s\n' "$output" | sed -n 's/^self-compact handoff receipt: //p')"
log="$(printf '%s\n' "$output" | sed -n 's/^watcher log: //p')"
complete_authorizing_turn "self-compact handoff receipt: $lock_token"
wait_for_log 'compact succeeded but the SDK continuation was not delivered' "$log"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "failed continuation did not retain exclusion"
assert_count 1 '^1$' "$FAKE_REQUEST_COUNT"

echo "submit-compact tests passed"
