#!/usr/bin/env bash
set -euo pipefail

pane="${1:-}"
command="${2:-}"
receipt_dir="${HOME}/.copilot/autopilot-enqueue"
mkdir -p "$receipt_dir"
receipt="${receipt_dir}/$(date -u +%Y%m%dT%H%M%SZ)-$$.txt"

finish() {
  local status="$1"
  local detail="$2"
  printf 'status=%s\ntime=%s\npane=%s\ncommand=%s\ndetail=%s\n' \
    "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pane" "$command" "$detail" >"$receipt"
  if [[ "$status" != "confirmed" ]] && command -v osascript >/dev/null 2>&1; then
    osascript -e 'display notification "Autopilot handoff failed. The latest receipt in ~/.copilot/autopilot-enqueue contains the objective." with title "Copilot unattended run"' >/dev/null 2>&1 || true
  fi
}

highest_objective_number() {
  grep -Eo 'Started autopilot objective #[0-9]+:' |
    grep -Eo '[0-9]+' |
    sort -n |
    tail -1
}

if [[ -z "$pane" || -z "$command" || "$command" == *$'\n'* ]]; then
  finish "invalid" "pane and one-line command are required"
  exit 64
fi

if ! tmux display-message -p -t "$pane" '#{pane_id}' >/dev/null 2>&1; then
  finish "unavailable" "tmux pane is not available"
  exit 2
fi

idle_samples=0
for _ in $(seq 1 300); do
  if ! screen="$(tmux capture-pane -p -t "$pane" 2>/dev/null)"; then
    finish "unavailable" "tmux pane disappeared while waiting for idle"
    exit 2
  fi
  if grep -Eq '(^|[^[:alpha:]])Working([^[:alpha:]]|$).*esc interrupt|◉ Working' <<<"$screen"; then
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
  finish "timeout" "pane did not reach a stable idle boundary within 300 seconds"
  exit 1
fi

baseline_number="$(highest_objective_number <<<"$screen" || true)"
baseline_number="${baseline_number:-0}"
baseline_legacy=false
if grep -Eq 'Started autopilot objective:|Autopilot objective:' <<<"$screen"; then
  baseline_legacy=true
fi

if ! tmux send-keys -t "$pane" -l -- "$command"; then
  finish "unavailable" "tmux pane disappeared before objective entry"
  exit 2
fi
sleep 0.5
if ! tmux send-keys -t "$pane" Enter; then
  finish "unavailable" "tmux pane disappeared before objective submission"
  exit 2
fi

for _ in $(seq 1 60); do
  if ! screen="$(tmux capture-pane -p -t "$pane" 2>/dev/null)"; then
    finish "unavailable" "tmux pane disappeared while confirming objective"
    exit 2
  fi
  current_number="$(highest_objective_number <<<"$screen" || true)"
  current_number="${current_number:-0}"
  if ((current_number > baseline_number)); then
    finish "confirmed" "objective accepted"
    exit 0
  fi
  if [[ "$baseline_legacy" == false ]] &&
    grep -Eq 'Started autopilot objective:|Autopilot objective:' <<<"$screen"; then
    finish "confirmed" "objective accepted by legacy CLI"
    exit 0
  fi
  sleep 1
done

finish "unconfirmed" "no accepted-objective confirmation appeared within 60 seconds"
exit 1
