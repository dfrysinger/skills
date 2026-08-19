#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/../../_lib/copilot-pane.sh"

pane="${1:-}"
objective_file="${2:-}"
objective=""
receipt_dir="${HOME}/.copilot/autopilot-enqueue"
mkdir -p "$receipt_dir"
receipt="${receipt_dir}/$(date -u +%Y%m%dT%H%M%SZ)-$$.txt"
buffer_name="copilot-autopilot-$$"
payload_file=""
handoff_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"

finish() {
  local status="$1"
  local detail="$2"
  {
    printf 'status=%s\ntime=%s\npane=%s\nhandoff_id=%s\ndetail=%s\nobjective_begin\n' \
      "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pane" "$handoff_id" "$detail"
    printf '%s\nobjective_end\n' "$objective"
  } >"$receipt"
  if [[ "$status" != "confirmed" ]] && command -v osascript >/dev/null 2>&1; then
    osascript -e 'display notification "Autopilot handoff failed. The latest receipt in ~/.copilot/autopilot-enqueue contains the objective." with title "Copilot unattended run"' >/dev/null 2>&1 || true
  fi
}

cleanup() {
  if [[ -n "$payload_file" ]]; then
    rm -f "$payload_file"
  fi
  tmux delete-buffer -b "$buffer_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

highest_objective_number() {
  grep -Eo 'Started autopilot objective #[0-9]+:' |
    grep -Eo '[0-9]+' |
    sort -n |
    tail -1
}

if [[ -z "$objective_file" || ! -r "$objective_file" ]]; then
  finish "invalid" "readable objective file is required"
  exit 64
fi

if ! objective="$(cat -- "$objective_file")" || [[ -z "$objective" ]]; then
  finish "invalid" "objective file must contain a non-empty objective"
  exit 64
fi

if [[ -z "$pane" ]]; then
  finish "invalid" "tmux pane is required"
  exit 64
fi

if [[ "$objective" == /autopilot* ]]; then
  finish "invalid" "objective file must contain the objective body without the slash command"
  exit 64
fi

if ! tmux display-message -p -t "$pane" '#{pane_id}' >/dev/null 2>&1; then
  finish "unavailable" "tmux pane is not available"
  exit 2
fi

pane_command="$(tmux display-message -p -t "$pane" '#{pane_current_command}' 2>/dev/null || true)"
if [[ "$pane_command" != "copilot" ]]; then
  finish "unavailable" "target pane is not running Copilot CLI"
  exit 2
fi

idle_samples=0
for _ in $(seq 1 300); do
  if ! screen="$(tmux capture-pane -p -J -t "$pane" 2>/dev/null)"; then
    finish "unavailable" "tmux pane disappeared while waiting for idle"
    exit 2
  fi
  if ! cp_is_loaded <<<"$screen" ||
    ! cp_input_is_empty <<<"$screen" ||
    cp_is_busy <<<"$screen"; then
    idle_samples=0
  else
    idle_samples=$((idle_samples + 1))
    if ((idle_samples >= 2)); then
      break
    fi
  fi
  sleep 1
done

if ((idle_samples < 2)); then
  if ! cp_is_loaded <<<"${screen:-}" ||
    ! cp_input_is_empty <<<"${screen:-}"; then
    finish "timeout" "Copilot prompt did not become ready within 300 seconds"
  else
    finish "timeout" "pane did not reach a stable idle boundary within 300 seconds"
  fi
  exit 1
fi

baseline_number="$(highest_objective_number <<<"$screen" || true)"
baseline_number="${baseline_number:-0}"

payload_file="$(mktemp "${TMPDIR:-/tmp}/copilot-autopilot.XXXXXX")"
chmod 600 "$payload_file"
printf '/autopilot [handoff-id:%s] %s' "$handoff_id" "$objective" >"$payload_file"

if ! tmux load-buffer -b "$buffer_name" "$payload_file"; then
  finish "unavailable" "tmux could not stage the objective"
  exit 2
fi
if ! tmux paste-buffer -p -r -d -b "$buffer_name" -t "$pane"; then
  finish "unavailable" "tmux pane disappeared before objective entry"
  exit 2
fi
sleep 0.5
if ! tmux send-keys -t "$pane" Enter; then
  finish "unavailable" "tmux pane disappeared before objective submission"
  exit 2
fi

for _ in $(seq 1 60); do
  if ! screen="$(tmux capture-pane -p -J -t "$pane" 2>/dev/null)"; then
    finish "unavailable" "tmux pane disappeared while confirming objective"
    exit 2
  fi
  current_number="$(highest_objective_number <<<"$screen" || true)"
  current_number="${current_number:-0}"
  if ((current_number > baseline_number)); then
    finish "confirmed" "objective accepted"
    exit 0
  fi
  if grep -Fq "Autopilot objective: [handoff-id:${handoff_id}]" <<<"$screen" ||
    grep -Fq "Started autopilot objective: [handoff-id:${handoff_id}]" <<<"$screen"; then
    finish "confirmed" "objective accepted by legacy CLI"
    exit 0
  fi
  sleep 1
done

finish "unconfirmed" "no accepted-objective confirmation appeared within 60 seconds"
exit 1
