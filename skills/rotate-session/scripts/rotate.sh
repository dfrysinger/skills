#!/usr/bin/env bash
# Rotate the current Copilot CLI session into a fresh one seeded with a prompt.
#
#   rotate.sh <old-session-id> <prompt-file> [--consume-prompt]
#
# Typing `/new <prompt>` into the CLI input is racy. The CLI queues any message
# that arrives while it is busy, and a queued message only drains at a turn
# boundary. A freshly created session has no turn in flight, so the seed can sit
# in the queue indefinitely while the session looks empty. This script closes
# that gap by refusing to submit until the whole prompt is on screen, and by
# confirming the fresh session actually received a message rather than assuming
# it did.
#
# Prompt validation and snapshotting happen synchronously. The tmux interaction
# runs in a detached child because the caller's turn ends when rotation fires.

set -uo pipefail

USAGE="usage: rotate.sh <old-session-id> <prompt-file> [--consume-prompt]"
OLD="${1:?$USAGE}"
PROMPT_FILE="${2:?$USAGE}"
CONSUME_PROMPT="${3:-}"
PANE="${TMUX_PANE:?TMUX_PANE is not set. This script drives a tmux pane and cannot run outside one; print the expanded /new command for the user to run instead (see the SKILL.md outside-tmux branch).}"
STATE="$HOME/.copilot/session-state"
LOG="${ROTATE_LOG:-/tmp/rotate-session-$OLD.log}"
TMP_ROOT="${TMPDIR:-/tmp}"
TMP_ROOT="${TMP_ROOT%/}"
[ -n "$TMP_ROOT" ] || TMP_ROOT=/

case "$CONSUME_PROMPT" in
  ""|--consume-prompt) ;;
  *) echo "rotate.sh: $USAGE" >&2; exit 1 ;;
esac

[ -s "$PROMPT_FILE" ] || { echo "rotate.sh: prompt file is empty" >&2; exit 1; }
[ -d "$STATE/$OLD" ] || { echo "rotate.sh: no such session $OLD" >&2; exit 1; }

PROMPT=$(cat -- "$PROMPT_FILE") || {
  echo "rotate.sh: could not read prompt file $PROMPT_FILE" >&2
  exit 1
}
case "$PROMPT" in
  *"$OLD"*) ;;
  *)
    echo "rotate.sh: prompt does not name expected session $OLD" >&2
    exit 1
    ;;
esac

# Freeze the prompt before the detached child starts. The caller's input file
# may be cleaned up or replaced after this command returns; the recovery copy
# remains private to this rotation and is retained only when seeding fails.
umask 077
RECOVERY_FILE=$(mktemp "$TMP_ROOT/copilot-rotate-recovery-$OLD.XXXXXX") || {
  echo "rotate.sh: could not create private prompt snapshot" >&2
  exit 1
}
if ! printf '%s' "$PROMPT" >"$RECOVERY_FILE"; then
  if rm -f -- "$RECOVERY_FILE"; then
    echo "rotate.sh: could not write private prompt snapshot" >&2
  else
    echo "rotate.sh: could not write private prompt snapshot; incomplete copy may remain at $RECOVERY_FILE" >&2
  fi
  exit 1
fi

# Documented callers opt in to consuming their unique temporary input. The
# explicit flag keeps generic prompt files caller-owned.
if [ "$CONSUME_PROMPT" = "--consume-prompt" ] && ! rm -f -- "$PROMPT_FILE"; then
  echo "rotate.sh: could not remove consumed prompt; recovery copy preserved at $RECOVERY_FILE" >&2
  exit 1
fi

# Record the recovery path before detaching so an interrupted child cannot
# leave an undiscoverable snapshot.
if ! {
  echo "=== rotate $OLD at $(date -Iseconds) ==="
  echo "recovery snapshot: $RECOVERY_FILE (removed after successful seeding)"
} >>"$LOG"; then
  echo "rotate.sh: could not write rotation log; recovery copy preserved at $RECOVERY_FILE" >&2
  exit 1
fi

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

_finish_success() {
  local result="$1"
  if ! rm -f -- "$RECOVERY_FILE"; then
    echo "RESULT: $result, but recovery cleanup failed; prompt preserved at $RECOVERY_FILE"
    exit 1
  fi
  echo "RESULT: $result"
  exit 0
}

(
  exec >>"$LOG" 2>&1
  BEFORE=$(_sessions_here | sort)

  if ! _type_and_submit "/new $PROMPT"; then
    echo "RESULT: rotation did not fire; the old session is untouched; prompt preserved at $RECOVERY_FILE"
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
    echo "RESULT: no new session appeared; prompt preserved at $RECOVERY_FILE"
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
    _finish_success "rotated to $NEW, seeded"
  fi

  echo "seed did not arrive; re-sending it as a plain message"
  DUP="NOTE: the original copy of this message was queued rather than delivered, so it may still arrive again later. If it does, treat it as a duplicate: do not redo the work and do not arm a second schedule. "
  if _type_and_submit "$DUP$PROMPT" && { sleep 5; _seeded "$NEW"; }; then
    _finish_success "rotated to $NEW, seeded on retry"
  fi

  echo "RESULT: rotated to $NEW but it is NOT seeded; prompt preserved at $RECOVERY_FILE"
  exit 1
) &

disown 2>/dev/null
echo "rotation started; result will be written to $LOG"
