#!/usr/bin/env bash
# Rotate the current Copilot CLI session into a fresh one seeded with a prompt.
#
#   rotate.sh <old-session-id> <prompt-file>
#
# Typing `/new <prompt>` into the CLI input is racy. The CLI queues any message
# that arrives while it is busy, and a queued message only drains at a turn
# boundary. A freshly created session has no turn in flight, so the seed can sit
# in the queue indefinitely while the session looks empty. This script closes
# that gap by refusing to submit until the whole prompt is on screen, and by
# confirming the fresh session actually received a message rather than assuming
# it did.
#
# All of the work happens in a detached child, because the caller's turn ends
# the moment the rotation fires.

set -uo pipefail

OLD="${1:?usage: rotate.sh <old-session-id> <prompt-file>}"
PROMPT_FILE="${2:?usage: rotate.sh <old-session-id> <prompt-file>}"
PANE="${TMUX_PANE:?TMUX_PANE is not set. This script drives a tmux pane and cannot run outside one; print the expanded /new command for the user to run instead (see the SKILL.md outside-tmux branch).}"
STATE="$HOME/.copilot/session-state"
LOG="${ROTATE_LOG:-/tmp/rotate-session-$OLD.log}"

[ -s "$PROMPT_FILE" ] || { echo "rotate.sh: prompt file is empty" >&2; exit 1; }
[ -d "$STATE/$OLD" ] || { echo "rotate.sh: no such session $OLD" >&2; exit 1; }

# The input box is the region between the last two horizontal rules. A long
# prompt wraps below the `❯` marker, so the whole region has to be read.
_input_region() {
  tmux capture-pane -p -t "$PANE" 2>/dev/null | awk '
    /^─+$/ { n++; sep[n] = NR }
    { line[NR] = $0 }
    END {
      if (n < 2) exit 1
      for (i = sep[n-1] + 1; i < sep[n]; i++) print line[i]
    }'
}

# Wrapping inserts newlines and padding at arbitrary points, so compare with all
# whitespace removed.
_squash() { tr -d '[:space:]'; }

_input_is_empty() {
  local t
  t=$(_input_region | tr -d '❯' | _squash) || return 1
  [ -z "$t" ]
}

_sessions_here() {
  local cwd="$PWD" ws
  for ws in "$STATE"/*/workspace.yaml; do
    [ -r "$ws" ] || continue
    [ "$(awk -F': ' '/^cwd: /{sub(/[[:space:]]+$/,"",$2);print $2;exit}' "$ws")" = "$cwd" ] || continue
    basename "$(dirname "$ws")"
  done
}

# Types text and presses Enter until the input box is empty. Returns non-zero if
# the payload never fully rendered, so the caller never submits a truncated one.
_type_and_submit() {
  local text="$1" marker attempt
  # The tail is what stays visible once a long prompt wraps.
  marker=$(printf '%s' "$text" | tail -c 60 | _squash)

  tmux send-keys -t "$PANE" -l -- "$text"

  for attempt in $(seq 1 40); do
    _input_region | _squash | grep -qF -- "$marker" && break
    sleep 0.5
  done
  if ! _input_region | _squash | grep -qF -- "$marker"; then
    echo "prompt never fully rendered in the input box; not submitting" >>"$LOG"
    return 1
  fi

  for attempt in $(seq 1 10); do
    tmux send-keys -t "$PANE" Enter
    sleep 1.5
    _input_is_empty && return 0
  done
  return 1
}

_seeded() { [ -s "$STATE/$1/events.jsonl" ]; }

(
  exec >>"$LOG" 2>&1
  echo "=== rotate $OLD at $(date -Iseconds) ==="
  PROMPT=$(cat "$PROMPT_FILE")
  BEFORE=$(_sessions_here | sort)

  if ! _type_and_submit "/new $PROMPT"; then
    echo "RESULT: rotation did not fire; the old session is untouched"
    exit 1
  fi

  # Wait for the replacement session to appear.
  NEW=""
  for _ in $(seq 1 60); do
    NEW=$(comm -13 <(printf '%s\n' "$BEFORE") <(_sessions_here | sort) | head -1)
    [ -n "$NEW" ] && break
    sleep 1
  done
  if [ -z "$NEW" ]; then
    echo "RESULT: no new session appeared"
    exit 1
  fi
  echo "new session: $NEW"

  # A seeded session records the prompt as its first event. A bare `/new` leaves
  # no event log at all, which is the failure this script exists to catch.
  for _ in $(seq 1 30); do
    _seeded "$NEW" && break
    sleep 1
  done

  if _seeded "$NEW"; then
    echo "RESULT: rotated to $NEW, seeded"
    exit 0
  fi

  echo "seed did not arrive; re-sending it as a plain message"
  DUP="NOTE: the original copy of this message was queued rather than delivered, so it may still arrive again later. If it does, treat it as a duplicate: do not redo the work and do not arm a second schedule. "
  if _type_and_submit "$DUP$PROMPT" && { sleep 5; _seeded "$NEW"; }; then
    echo "RESULT: rotated to $NEW, seeded on retry"
    exit 0
  fi

  echo "RESULT: rotated to $NEW but it is NOT seeded; prompt is at $PROMPT_FILE"
  exit 1
) &

disown 2>/dev/null
echo "rotation started; result will be written to $LOG"
