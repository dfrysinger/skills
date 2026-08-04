#!/usr/bin/env bash
# Wait for a queued compact to increment summary_count, then submit continuation.

set -euo pipefail

PANE="${1:?pane is required}"
WORKSPACE="${2:?workspace.yaml path is required}"
BEFORE="${3:?baseline summary_count is required}"
READY="${4:?ready path is required}"
ARMED="${5:?armed path is required}"
CANCELLED="${6:?cancelled path is required}"
MARKER="${7:?checkpoint marker is required}"
CONTINUATION="${8:-proceed}"
POLL_SECONDS="${SELF_COMPACT_POLL_SECONDS:-1}"
MAX_POLLS="${SELF_COMPACT_MAX_POLLS:-1800}"
CHECKPOINTS_DIR="${WORKSPACE%/workspace.yaml}/checkpoints"

cleanup() {
  rm -f "$READY" "$ARMED" "$CANCELLED"
}
trap cleanup EXIT

: > "$READY"

for ((attempt = 1; attempt <= 1200; attempt++)); do
  [ -e "$CANCELLED" ] && {
    echo "continuation watcher cancelled before compact submission" >&2
    exit 1
  }
  [ -e "$ARMED" ] && break
  sleep 0.1
done

if [ ! -e "$ARMED" ]; then
  echo "continuation watcher was never armed" >&2
  exit 1
fi

landed=false
for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  current="$(awk -F': ' '/^summary_count: /{print $2; exit}' "$WORKSPACE" 2>/dev/null || true)"
  case "$current" in
    ''|*[!0-9]*) ;;
    *)
      if [ "$current" -gt "$BEFORE" ] &&
        grep -R -F -q -- "$MARKER" "$CHECKPOINTS_DIR" 2>/dev/null; then
        landed=true
        break
      fi
      ;;
  esac
  sleep "$POLL_SECONDS"
done

if [ "$landed" != true ]; then
  echo "timed out waiting for compact checkpoint marker $MARKER beyond summary_count $BEFORE" >&2
  exit 1
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

for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
  input_is_empty && break
  sleep "$POLL_SECONDS"
done

if ! input_is_empty; then
  echo "compact landed, but Copilot input never became empty" >&2
  exit 1
fi

expected="$(printf '%s' "$CONTINUATION" | squash)"
tmux send-keys -t "$PANE" -l -- "$CONTINUATION"

rendered=false
for ((attempt = 1; attempt <= 40; attempt++)); do
  if [ "$(normalized_input || true)" = "$expected" ]; then
    rendered=true
    break
  fi
  sleep 0.5
done

if [ "$rendered" != true ]; then
  echo "compact landed, but continuation never rendered exactly" >&2
  exit 1
fi

for ((attempt = 1; attempt <= 10; attempt++)); do
  tmux send-keys -t "$PANE" Enter
  sleep 1.5
  if input_is_empty; then
    echo "submitted post-compact continuation after summary_count advanced to $current"
    exit 0
  fi
  if [ "$(normalized_input)" != "$expected" ]; then
    break
  fi
done

echo "compact landed, but continuation submission was not confirmed" >&2
exit 1
