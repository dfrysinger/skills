#!/usr/bin/env bash
# Wait for a queued compact to increment summary_count, then submit continuation.

set -euo pipefail

PANE="${1:?pane is required}"
WORKSPACE="${2:?workspace.yaml path is required}"
BEFORE="${3:?baseline summary_count is required}"
BEFORE_EVENTS="${4:?baseline event line count is required}"
READY="${5:?ready path is required}"
ARMED="${6:?armed path is required}"
CANCELLED="${7:?cancelled path is required}"
MARKER="${8:?checkpoint marker is required}"
CONTINUATION="${9:-proceed}"
POLL_SECONDS="${SELF_COMPACT_POLL_SECONDS:-1}"
MAX_POLLS="${SELF_COMPACT_MAX_POLLS:-1800}"
RESUME_GRACE_SECONDS="${SELF_COMPACT_RESUME_GRACE_SECONDS:-3}"
CHECKPOINTS_DIR="${WORKSPACE%/workspace.yaml}/checkpoints"
EVENTS="${WORKSPACE%/workspace.yaml}/events.jsonl"

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

compaction_line=""
for ((attempt = 1; attempt <= 300; attempt++)); do
  compaction_line="$(
    awk -v before="$BEFORE_EVENTS" '
      NR > before && /"type":"session.compaction_complete"/ { line = NR }
      END { if (line) print line }
    ' "$EVENTS"
  )"
  [ -n "$compaction_line" ] && break
  sleep 0.1
done

if [ -z "$compaction_line" ]; then
  echo "marked checkpoint landed, but session.compaction_complete was not recorded" >&2
  exit 1
fi

post_compact_activity_exists() {
  awk -v after="$compaction_line" '
    NR > after &&
      (/"type":"user.message"/ || /"type":"assistant.turn_start"/) { found = 1; exit }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"
}

# Autopilot sometimes resumes on its own. Give it one short chance, then inject
# only when no post-compact user message or assistant turn exists.
sleep "$RESUME_GRACE_SECONDS"
if post_compact_activity_exists; then
  echo "post-compact activity already present after event line $compaction_line; continuation not needed"
  exit 0
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

for ((attempt = 1; attempt <= 30; attempt++)); do
  input_is_empty && break
  sleep 0.1
done

if ! input_is_empty; then
  echo "compact landed with no resumed turn, but Copilot input is not empty" >&2
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

# Close the grace-to-submit race without steering an automatically resumed turn.
if post_compact_activity_exists; then
  tmux send-keys -t "$PANE" C-u
  echo "post-compact activity started before submission; continuation not needed"
  exit 0
fi

for ((attempt = 1; attempt <= 10; attempt++)); do
  tmux send-keys -t "$PANE" Enter
  sleep 1
  if awk -v after="$compaction_line" -v continuation="$CONTINUATION" '
    NR > after &&
      /"type":"user.message"/ &&
      index($0, "\"content\":\"" continuation "\"") { found = 1; exit }
    END { exit(found ? 0 : 1) }
  ' "$EVENTS"; then
    echo "submitted post-compact continuation after event line $compaction_line"
    exit 0
  fi
  if [ "$(normalized_input)" != "$expected" ]; then
    break
  fi
done

echo "compact landed, but continuation submission was not confirmed" >&2
exit 1
