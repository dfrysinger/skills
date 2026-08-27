#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/enqueue-autopilot.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/unattended-run-test.XXXXXX")"
trap '/bin/rm -rf -- "$ROOT"' EXIT

mkdir -p "$ROOT/home" "$ROOT/tmp"
MOCK_REQUEST="$ROOT/request.mjs"
cat >"$MOCK_REQUEST" <<'EOF'
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";

const args = process.argv.slice(2);
appendFileSync(process.env.MOCK_ARGS, `${JSON.stringify(args)}\n`);
const promptIndex = args.indexOf("--prompt-file");
if (process.env.MOCK_MODE === "mutate-source") {
  writeFileSync(process.env.MOCK_SOURCE, "/allow-all");
}
if (promptIndex >= 0) {
  appendFileSync(process.env.MOCK_PROMPTS, `${readFileSync(args[promptIndex + 1], "utf8")}\n`);
}
if (process.env.MOCK_MODE === "fail") {
  console.log('{"status":"failed","error":"recipient rejected request"}');
  process.exit(1);
}
if (process.env.MOCK_MODE === "non-idle") {
  console.log('{"status":"completed","result":{"delivery":"queued"}}');
  process.exit(0);
}
console.log("request: /tmp/request.json");
console.log("receipt: /tmp/completed.json");
console.log('{"status":"completed","result":{"messageId":"message-1","delivery":"idle"}}');
EOF

run_case() {
  local label="$1"
  local mode="$2"
  local target_flag="$3"
  local target="$4"
  local objective="$5"
  local objective_file="$ROOT/$label-objective.txt"
  local args_file="$ROOT/$label-args.jsonl"
  local prompts_file="$ROOT/$label-prompts.txt"
  local output="$ROOT/$label.out"

  printf '%s' "$objective" >"$objective_file"
  if HOME="$ROOT/home" TMPDIR="$ROOT/tmp" \
    SESSION_INBOX_REQUEST_CLI="$MOCK_REQUEST" \
    MOCK_ARGS="$args_file" MOCK_PROMPTS="$prompts_file" MOCK_MODE="$mode" \
    MOCK_SOURCE="$objective_file" \
    "$SCRIPT" "$target_flag" "$target" "$objective_file" >"$output" 2>&1; then
    result=0
  else
    result=$?
  fi
  printf '%s\t%s\t%s\t%s\n' "$result" "$args_file" "$prompts_file" "$output"
}

bash -n "$SCRIPT"

IFS=$'\t' read -r result args prompts output < <(
  run_case session-success success --target-session session-1 "finish the objective"
)
[[ "$result" -eq 0 ]]
grep -Fq '["send","--target-session","session-1","--prompt-file"' "$args"
grep -Fq '"--agent-mode","autopilot","--mode","immediate","--dedupe-key","autopilot:session:session-1:' "$args"
grep -Fq '"--timeout","360"]' "$args"
grep -Fq 'finish the objective' "$prompts"
grep -Fq 'autopilot handoff confirmed; receipt:' "$output"
receipt="$(sed -n 's/.*receipt: //p' "$output" | tail -1)"
grep -Fq 'status=confirmed' "$receipt"
grep -Fq 'delivery":"idle' "$receipt"

IFS=$'\t' read -r result args _ output < <(
  run_case tmux-success success --target-tmux whisky "continue from the plan"
)
[[ "$result" -eq 0 ]]
grep -Fq '["send","--target-tmux","whisky","--prompt-file"' "$args"

IFS=$'\t' read -r result _ prompts _ < <(
  run_case immutable mutate-source --target-session session-immutable \
    "validated immutable objective"
)
[[ "$result" -eq 0 ]]
grep -Fq 'validated immutable objective' "$prompts"
! grep -Fq '/allow-all' "$prompts"

IFS=$'\t' read -r result _ _ output < <(
  run_case failed fail --target-session session-2 "keep working"
)
[[ "$result" -eq 1 ]]
grep -Fq 'SDK handoff failed; receipt:' "$output"
receipt="$(sed -n 's/.*receipt: //p' "$output" | tail -1)"
grep -Fq 'status=failed' "$receipt"
grep -Fq 'recipient rejected request' "$receipt"

IFS=$'\t' read -r result _ _ output < <(
  run_case non-idle non-idle --target-session session-3 "keep working"
)
[[ "$result" -eq 1 ]]
grep -Fq 'did not prove idle delivery' "$output"

for invalid in '/autopilot do it' '/goal do it' '/allow-all' 'contains <SLOT>'; do
  IFS=$'\t' read -r result _ _ _ < <(
    run_case invalid success --target-session session-4 "$invalid"
  )
  [[ "$result" -eq 64 ]]
done

IFS=$'\t' read -r result _ _ _ < <(
  run_case permission-line success --target-session session-4 $'work\n/allow-all'
)
[[ "$result" -eq 64 ]]

IFS=$'\t' read -r result _ _ _ < <(
  run_case whitespace success --target-session session-4 $' \n\t'
)
[[ "$result" -eq 64 ]]

IFS=$'\t' read -r result _ _ _ < <(
  AUTOPILOT_HANDOFF_TIMEOUT_SECONDS=361 \
    run_case timeout success --target-session session-5 "work"
)
[[ "$result" -eq 64 ]]

! grep -Eq 'send-keys|capture-pane|paste-buffer|load-buffer' "$SCRIPT"
echo "unattended-run enqueue tests: pass"
