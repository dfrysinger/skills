#!/usr/bin/env bash
# Submit a steered /compact command through the current Copilot tmux pane.

set -euo pipefail

PANE="${TMUX_PANE:?TMUX_PANE is not set; run inside tmux}"
STEER="${*:-}"

if [ -z "$STEER" ]; then
  echo "usage: submit-compact.sh '<steer>'" >&2
  exit 2
fi

COMMAND="/compact $STEER"
CONTINUATION="proceed"
COMPACT_SUBMITTED=false

case "$STEER" in
  *$'\n'*)
    echo "submit-compact.sh: steer must be a single line" >&2
    exit 2
    ;;
esac

if printf '%s' "$STEER" | LC_ALL=C grep -q '[[:cntrl:]]'; then
  echo "submit-compact.sh: steer must not contain control characters" >&2
  exit 2
fi

input_region() {
  tmux capture-pane -p -t "$PANE" 2>/dev/null | awk '
    /^─+$/ { n++; sep[n] = NR }
    { line[NR] = $0 }
    END {
      if (n < 2) exit 1
      for (i = sep[n-1] + 1; i < sep[n]; i++) print line[i]
    }'
}

squash() {
  tr -d '[:space:]'
}

input_is_empty() {
  local text
  text=$(input_region | tr -d '❯' | squash) || return 1
  [ -z "$text" ]
}

normalized_input() {
  input_region | tr -d '❯' | squash
}

clear_input() {
  local attempt
  for ((attempt = 1; attempt <= 3; attempt++)); do
    if ! tmux send-keys -t "$PANE" C-u; then
      return 1
    fi
    sleep 0.5
    input_is_empty && return 0
  done
  return 1
}

abort_after_send() {
  local reason="$1"
  local prefix="submit-compact.sh:"
  if [ "$COMPACT_SUBMITTED" = true ]; then
    prefix="$prefix compact is already queued; do not rerun the helper; send 'proceed' manually."
  fi
  if clear_input; then
    echo "$prefix $reason; input cleared" >&2
  else
    echo "$prefix $reason; input cleanup failed" >&2
  fi
  exit 1
}

submit_command() {
  local command="$1"
  local label="$2"
  local detect_scroll="$3"
  local expected actual rendered scrolled attempt

  if ! input_is_empty; then
    if [ "$COMPACT_SUBMITTED" = true ]; then
      echo "submit-compact.sh: compact is already queued; do not rerun the helper; send 'proceed' manually. Copilot input is not empty; refusing to append $label" >&2
    else
      echo "submit-compact.sh: Copilot input is not empty; refusing to append $label" >&2
    fi
    return 1
  fi

  expected=$(printf '%s' "$command" | squash)
  if ! tmux send-keys -t "$PANE" -l -- "$command"; then
    abort_after_send "could not type $label"
  fi

  rendered=false
  scrolled=false
  for ((attempt = 1; attempt <= 40; attempt++)); do
    actual=$(normalized_input || true)
    if [ "$actual" = "$expected" ]; then
      rendered=true
      break
    fi
    if [ "$detect_scroll" = true ] &&
      [ -n "$actual" ] &&
      [ "${#actual}" -lt "${#expected}" ] &&
      [[ "$expected" == *"$actual" ]]; then
      scrolled=true
      break
    fi
    sleep 0.5
  done

  if [ "$scrolled" = true ]; then
    abort_after_send "steer is too long to verify; shorten it or reference the durable artifact"
  fi

  if [ "$rendered" != true ]; then
    abort_after_send "$label never rendered exactly"
  fi

  for ((attempt = 1; attempt <= 10; attempt++)); do
    if ! tmux send-keys -t "$PANE" Enter; then
      abort_after_send "could not submit $label"
    fi
    sleep 1.5
    if input_is_empty; then
      return 0
    fi
    if [ "$(normalized_input)" != "$expected" ]; then
      break
    fi
  done

  abort_after_send "$label submission was not confirmed"
}

submit_command "$COMMAND" "compact command" true
COMPACT_SUBMITTED=true

# Compaction produces context, not a user turn. Queue an explicit continuation
# behind it instead of relying on autopilot to generate another turn.
if ! submit_command "$CONTINUATION" "continuation prompt" false; then
  exit 1
fi

echo "submitted compact and continuation"
