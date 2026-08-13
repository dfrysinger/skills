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
#   (default) — require a ready Copilot CLI with an empty input prompt now.
#   --wait    — poll for that same ready state for up to 30s. Use this
#              immediately after launching a fresh Copilot.
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

PANE="$(
  tmux list-panes -a -F $'#{session_name}\t#{pane_id}\t#{window_active}\t#{pane_active}' 2>/dev/null |
    awk -F $'\t' -v name="$NAME" '$1 == name && $3 == "1" && $4 == "1" { print $2 }'
)"
if [[ -z "$PANE" || "$PANE" == *$'\n'* ]]; then
  echo "UNVERIFIED: tmux session '$NAME' is not running; the mail is queued for pickup." >&2
  exit 3
fi

if [[ "$(tmux display-message -p -t "$PANE" '#{session_name}' 2>/dev/null || true)" != "$NAME" ]]; then
  echo "UNVERIFIED: resolved pane does not belong to exact session '$NAME'; no keys were sent." >&2
  exit 3
fi

current_input() {
  awk '
    /^[[:space:]]*❯/ {
      line = $0
      sub(/[[:space:]]*$/, "", line)
      active = 1
      next
    }
    active && /^[[:space:]]*─/ {
      active = 0
      next
    }
    active {
      continuation = $0
      sub(/^[[:space:]]*/, "", continuation)
      sub(/[[:space:]]*$/, "", continuation)
      line = line continuation
    }
    END {
      sub(/^[[:space:]]*/, "", line)
      sub(/[[:space:]]*$/, "", line)
      print line
    }
  '
}

input_signature() {
  tr -d '[:space:]'
}

copilot_ready() {
  local command screen input
  command="$(tmux display-message -p -t "$PANE" '#{pane_current_command}' 2>/dev/null || true)"
  [[ "$command" == "copilot" ]] || return 1
  screen="$(tmux capture-pane -p -J -t "$PANE" 2>/dev/null || true)"
  input="$(current_input <<<"$screen")"
  grep -q 'Session:.*AIC used' <<<"$screen" &&
    [[ "$input" == "❯" ]]
}

if [[ "$WAIT" -eq 1 ]]; then
  for _ in $(seq 1 60); do
    copilot_ready && break
    sleep 0.5
  done
fi

if ! copilot_ready; then
  echo "UNVERIFIED: '$NAME' is not at a ready Copilot prompt; the mail is queued and no keys were sent." >&2
  exit 3
fi

MARKER="[mb:${NEWEST_ID##*-}]"
PROMPT="check mailbox; skip if empty $MARKER"
PROMPT_SIGNATURE="$(input_signature <<<"❯ $PROMPT")"
if tmux send-keys -t "$PANE" -l -- "$PROMPT"; then
  sleep 0.5
  SUBMITTED=0
  for _ in 1 2 3 4 5; do
    SCREEN="$(tmux capture-pane -p -J -t "$PANE" 2>/dev/null || true)"
    INPUT="$(current_input <<<"$SCREEN")"
    INPUT_SIGNATURE="$(input_signature <<<"$INPUT")"
    if [[ "$(tmux display-message -p -t "$PANE" '#{pane_current_command}' 2>/dev/null || true)" != "copilot" ]] ||
      [[ "$INPUT_SIGNATURE" != "$PROMPT_SIGNATURE" ]]; then
      break
    fi
    tmux send-keys -t "$PANE" Enter
    sleep 1.5
    SCREEN="$(tmux capture-pane -p -J -t "$PANE" 2>/dev/null || true)"
    INPUT="$(current_input <<<"$SCREEN")"
    if [[ "$INPUT" == "❯" ]] &&
      grep -Fq "$MARKER" <<<"$SCREEN"; then
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
  echo "UNVERIFIED: '$NAME' disappeared before the poke could be entered; the mail is queued." >&2
  exit 3
fi
