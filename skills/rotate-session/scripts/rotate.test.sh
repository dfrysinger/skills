#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rotate.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/rotate-session-test.XXXXXX")"
trap '/bin/rm -rf -- "$ROOT"' EXIT

mkdir -p "$ROOT/home/.copilot/session-state" "$ROOT/tmp"
MOCK_REQUEST="$ROOT/request.mjs"
cat >"$MOCK_REQUEST" <<'EOF'
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
appendFileSync(process.env.MOCK_ARGS, `${JSON.stringify(args)}\n`);
const promptFileIndex = args.indexOf("--prompt-file");
const targetIndex = args.indexOf("--target-session");
const oldSession = args[targetIndex + 1];
const newSession = `${oldSession}-new`;
let prompt = "";
if (promptFileIndex >= 0) {
  prompt = readFileSync(args[promptFileIndex + 1], "utf8");
  appendFileSync(process.env.MOCK_SEEDS, `${prompt}\n`);
}
if (process.env.MOCK_MODE === "fail") {
  console.log('{"status":"failed","error":"command execution rejected"}');
  process.exit(1);
}
const instances = join(process.env.HOME, ".copilot", "session-inbox", "instances");
const state = join(process.env.HOME, ".copilot", "session-state", newSession);
const completedAt = new Date().toISOString();
mkdirSync(instances, { recursive: true });
mkdirSync(state, { recursive: true });
writeFileSync(
  join(instances, `${oldSession}-prior.json`),
  `${JSON.stringify({
    sessionId: `${oldSession}-prior`,
    generation: "prior-generation",
    hostPid: 4242,
    updatedAt: "2000-01-01T00:00:00.000Z",
  })}\n`,
);
writeFileSync(
  join(instances, `${newSession}.json`),
  `${JSON.stringify({
    sessionId: newSession,
    generation: "new-generation",
    hostPid: 4242,
    updatedAt: completedAt,
  })}\n`,
);
writeFileSync(
  join(state, "events.jsonl"),
  `${JSON.stringify({ type: "user.message", data: { content: prompt, delivery: "idle" } })}\n`,
);
console.log("request: /tmp/request.json");
console.log("receipt: /tmp/completed.json");
console.log(
  JSON.stringify({
    status: "completed",
    sessionId: oldSession,
    hostPid: 4242,
    completedAt,
    result: {
      commandInvoked: true,
      mechanism: "commands.invoke",
      resultKind: "completed",
    },
  }),
);
EOF

wait_for_result() {
  local log="$1"
  local _
  for _ in $(/usr/bin/seq 1 200); do
    grep -q 'RESULT:' "$log" 2>/dev/null && return 0
    /bin/sleep 0.02
  done
  return 1
}

start_case() {
  local old="$1"
  local mode="$2"
  local label="$3"
  local prompt="$4"
  local consume="${5:-yes}"
  local state="$ROOT/home/.copilot/session-state/$old"
  local input="$ROOT/$label-input.txt"
  local log="$ROOT/$label.log"
  local args="$ROOT/$label-args.jsonl"
  local seeds="$ROOT/$label-seeds.txt"

  mkdir -p "$state"
  printf '%s' "$prompt" >"$input"

  local -a invocation=("$SCRIPT" "$old" "$input")
  [ "$consume" = yes ] && invocation+=(--consume-prompt)

  HOME="$ROOT/home" TMPDIR="$ROOT/tmp" ROTATE_LOG="$log" \
    SESSION_INBOX_REQUEST_CLI="$MOCK_REQUEST" \
    MOCK_ARGS="$args" MOCK_SEEDS="$seeds" MOCK_MODE="$mode" \
    "${invocation[@]}" >"$ROOT/$label.out"

  if [ "$consume" = yes ]; then
    [ ! -e "$input" ]
  else
    [ -e "$input" ]
  fi

  printf '%s\t%s\t%s\t%s\n' "$log" "$args" "$seeds" "$input"
}

bash -n "$SCRIPT"

IFS=$'\t' read -r success_log success_args success_seeds _ < <(
  start_case old-success success success 'continue retired session old-success'
)
wait_for_result "$success_log"
grep -Fq 'recovery snapshot:' "$success_log"
grep -Fq 'RESULT: rotated to old-success-new, seeded' "$success_log"
grep -Fq '["new-session-direct","--target-session","old-success","--prompt-file"' "$success_args"
grep -Fq '"--timeout","360"]' "$success_args"
grep -Fq 'continue retired session old-success' "$success_seeds"
! find "$ROOT/tmp" -maxdepth 1 -name 'copilot-rotate-recovery-old-success.*' | grep -q .

IFS=$'\t' read -r failure_log _ failure_seeds _ < <(
  start_case old-failure fail failure 'continue retired session old-failure'
)
wait_for_result "$failure_log"
grep -Fq 'rotation request failed with exit status 1' "$failure_log"
grep -Fq 'request output preserved at ' "$failure_log"
recovery="$(sed -n 's/^recovery snapshot: \([^ ]*\).*/\1/p' "$failure_log" | tail -1)"
[ -f "$recovery" ]
[ -f "$recovery.request-output" ]
grep -Fq 'continue retired session old-failure' "$recovery"
grep -Fq 'continue retired session old-failure' "$failure_seeds"
[ "$(stat -f '%Lp' "$recovery")" = 600 ]

IFS=$'\t' read -r generic_log _ _ generic_input < <(
  start_case old-generic success generic 'continue retired session old-generic' no
)
wait_for_result "$generic_log"
[ -f "$generic_input" ]

invalid="$ROOT/invalid-input.txt"
mkdir -p "$ROOT/home/.copilot/session-state/old-invalid"
printf 'wrong session' >"$invalid"
if HOME="$ROOT/home" TMPDIR="$ROOT/tmp" SESSION_INBOX_REQUEST_CLI="$MOCK_REQUEST" \
  MOCK_ARGS="$ROOT/invalid-args" MOCK_SEEDS="$ROOT/invalid-seeds" \
  "$SCRIPT" old-invalid "$invalid" --consume-prompt >"$ROOT/invalid.out" 2>&1; then
  exit 1
fi
grep -Fq 'prompt does not name expected session old-invalid' "$ROOT/invalid.out"
[ -f "$invalid" ]
[ ! -e "$ROOT/invalid-args" ]

log_failure="$ROOT/log-failure-input.txt"
mkdir -p "$ROOT/home/.copilot/session-state/old-log-failure"
printf 'continue retired session old-log-failure' >"$log_failure"
if HOME="$ROOT/home" TMPDIR="$ROOT/tmp" SESSION_INBOX_REQUEST_CLI="$MOCK_REQUEST" \
  ROTATE_LOG="$ROOT/missing/rotation.log" MOCK_ARGS="$ROOT/log-failure-args" \
  MOCK_SEEDS="$ROOT/log-failure-seeds" \
  "$SCRIPT" old-log-failure "$log_failure" --consume-prompt >"$ROOT/log-failure.out" 2>&1; then
  exit 1
fi
grep -Fq 'could not open rotation log; original prompt retained at ' "$ROOT/log-failure.out"
[ -f "$log_failure" ]
[ ! -e "$ROOT/log-failure-args" ]

timeout_input="$ROOT/timeout-input.txt"
mkdir -p "$ROOT/home/.copilot/session-state/old-timeout"
printf 'continue retired session old-timeout' >"$timeout_input"
if HOME="$ROOT/home" TMPDIR="$ROOT/tmp" ROTATE_SESSION_TIMEOUT_SECONDS=361 \
  SESSION_INBOX_REQUEST_CLI="$MOCK_REQUEST" \
  "$SCRIPT" old-timeout "$timeout_input" >"$ROOT/timeout.out" 2>&1; then
  exit 1
fi
grep -Fq 'timeout must be between 1 and 360 seconds' "$ROOT/timeout.out"

! grep -Eq 'send-keys|capture-pane|paste-buffer|load-buffer' "$SCRIPT"
echo "rotate-session tests: pass"
