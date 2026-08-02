#!/usr/bin/env bash
# mailbox-poke.sh <session-name> [--wait]
#
# If <session-name>'s mailbox has pending mail, send a natural-language
# wakeup prompt into its tmux pane that nudges the Copilot agent to invoke
# the mailbox skill (which then runs mailbox-check.sh).
#
# Why not "/mailbox"? Slash dispatch races cold-start skill-snapshot
# loading: the `❯` prompt appears before skills are registered, so a slash
# command sent immediately after detecting `❯` hits the router before the
# mailbox skill is recognized → "unknown command". A natural-language
# prompt goes through the agent's reasoning loop, which tolerates the
# load delay.
#
# Modes:
#   (default) — assume Copilot CLI is already running in the pane. Send keys
#              right away. Use this when reattaching to an existing session.
#   --wait    — poll the pane for Copilot CLI readiness (the `❯` input box
#              marker) for up to 30s, then send keys. Use this immediately
#              after launching a fresh Copilot in a new tmux session.
#
# Designed to be backgrounded by the user's `ca` launcher:
#   ( mailbox-poke.sh "$NAME" --wait ) &
#   exec tmux new-session ...

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/_common.sh"

[[ $# -lt 1 ]] && { echo "usage: mailbox-poke.sh <name> [--wait]" >&2; exit 2; }
NAME="$1"; shift
WAIT=0
[[ "${1:-}" == "--wait" ]] && WAIT=1

DIR="$MAILBOX_ROOT/$NAME/pending"
WATERMARK_FILE="$MAILBOX_ROOT/$NAME/.last-poked-id"
shopt -s nullglob
ENVS=("$DIR"/*.json)
[[ ${#ENVS[@]} -eq 0 ]] && exit 0  # no mail, no poke

# High-water-mark dedup: env IDs are timestamp-prefixed (lexical sort = chronological).
# If the newest pending envelope was already poked about, don't re-nag.
NEWEST_PATH="$(printf '%s\n' "${ENVS[@]}" | sort | tail -1)"
NEWEST_ID="$(basename "$NEWEST_PATH" .json)"
LAST_POKED=""
[[ -f "$WATERMARK_FILE" ]] && LAST_POKED="$(cat "$WATERMARK_FILE" 2>/dev/null || true)"
[[ "$NEWEST_ID" == "$LAST_POKED" ]] && exit 0

if [[ "$WAIT" -eq 1 ]]; then
  # Poll up to 30s for Copilot CLI's input prompt marker
  for _ in $(seq 1 60); do
    if tmux has-session -t "$NAME" 2>/dev/null && \
       tmux capture-pane -p -t "$NAME" 2>/dev/null | tail -10 | grep -q '❯'; then
      break
    fi
    sleep 0.5
  done
  sleep 0.5  # small grace once we see the prompt
fi

# Only send if the recipient tmux session is actually up
if tmux has-session -t "$NAME" 2>/dev/null; then
  PROMPT='check mailbox; skip if empty'
  tmux send-keys -t "$NAME" -l -- "$PROMPT"
  sleep 0.5
  # A single Enter often fails to submit, leaving the poke unsent in the
  # recipient's input box. Retry until their input line is empty again.
  SUBMITTED=0
  for _ in 1 2 3 4 5; do
    tmux send-keys -t "$NAME" Enter
    sleep 1.5
    if tmux capture-pane -p -t "$NAME" | grep -q '^❯[[:space:]]*$'; then
      SUBMITTED=1
      break
    fi
  done
  if [[ "$SUBMITTED" -eq 1 ]]; then
    # Mark this envelope as already-poked-about so re-attaches don't re-nag.
    # New mail will get a newer ID and re-trigger naturally.
    printf '%s\n' "$NEWEST_ID" > "$WATERMARK_FILE"
    echo "poked: $NAME (submission observed)"
  else
    # The poke is still sitting in the recipient's input box. Leaving the
    # watermark unwritten is what makes the next attempt retry instead of
    # treating undelivered mail as delivered.
    echo "UNVERIFIED: sent the poke to '$NAME' but never saw it submit; the mail is queued and will be re-poked." >&2
    exit 3
  fi
else
  echo "UNVERIFIED: tmux session '$NAME' is not running; the mail is queued for pickup." >&2
  exit 3
fi
