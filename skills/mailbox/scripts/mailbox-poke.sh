#!/usr/bin/env bash
# mailbox-poke.sh <session-name> [--wait|--terminal-only]
#
# If <session-name>'s mailbox has pending mail, send a natural-language wakeup
# prompt through the recipient backend. Copilot uses the session-inbox SDK
# extension first; a definitively rejected immediate send may retry through
# guarded terminal submission with --terminal-only.
#
# Why not "/mailbox"? Slash dispatch races cold-start skill-snapshot
# loading: the input box appears before skills are registered, so a slash
# command sent immediately after the box renders hits the router before the
# mailbox skill is recognized → "unknown command". A natural-language
# prompt goes through the agent's reasoning loop, which tolerates the
# load delay.
#
# Modes:
#   (default) — wait up to 20s for a Copilot SDK receipt, or require a ready
#               Claude/Codex input now.
#   --wait    — extend the Copilot receipt wait to 35s, or poll Claude/Codex
#               readiness for up to 30s after a fresh launch.
#
# Designed to be backgrounded by the user's `ca` launcher:
#   ( mailbox-poke.sh "$NAME" --wait ) &
#   exec tmux new-session ...

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/_common.sh"
. "$SCRIPT_DIR/../../_lib/agent-pane.sh"
REQUEST_CLI="$SCRIPT_DIR/../../../extensions/session-inbox/request.mjs"

[[ $# -lt 1 ]] && { echo "usage: mailbox-poke.sh <name> [--wait]" >&2; exit 2; }
NAME="$1"; shift
WAIT=0
TERMINAL_ONLY=0
EXPECTED_SESSION_ID=""
EXPECTED_GENERATION=""
EXPECTED_HOST_PID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --wait) WAIT=1; shift ;;
    --terminal-only) TERMINAL_ONLY=1; shift ;;
    --expected-session-id) EXPECTED_SESSION_ID="${2:-}"; shift 2 ;;
    --expected-generation) EXPECTED_GENERATION="${2:-}"; shift 2 ;;
    --expected-host-pid) EXPECTED_HOST_PID="${2:-}"; shift 2 ;;
    *) echo "usage: mailbox-poke.sh <name> [--wait] [--terminal-only --expected-session-id ID --expected-generation ID --expected-host-pid PID]" >&2; exit 2 ;;
  esac
done

if [[ "$TERMINAL_ONLY" -eq 0 ]]; then
  NODE_ARGS=(poke "$NAME")
  [[ "$WAIT" -eq 1 ]] && NODE_ARGS+=(--wait)
  set +e
  NODE_OUTPUT="$(node "$SCRIPT_DIR/mailbox.mjs" "${NODE_ARGS[@]}" 2>&1)"
  NODE_STATUS=$?
  set -e
  if [[ "$NODE_STATUS" -eq 0 ]]; then
    [[ -n "$NODE_OUTPUT" ]] && printf '%s\n' "$NODE_OUTPUT"
    exit 0
  elif [[ "$NODE_STATUS" -eq 5 ]]; then
    [[ -n "$NODE_OUTPUT" ]] && printf '%s\n' "$NODE_OUTPUT"
    exit 5
  elif [[ "$NODE_STATUS" -ne 4 ]]; then
    [[ -n "$NODE_OUTPUT" ]] && printf '%s\n' "$NODE_OUTPUT" >&2
    exit 3
  fi
fi

DIR="$MAILBOX_LOCAL_ROOT/$NAME/pending"
STATE_ROOT="${MAILBOX_STATE_ROOT:-$HOME/.copilot/mailbox-state}"
WATERMARK_FILE="$STATE_ROOT/watermarks/$NAME.txt"
TARGET_NAME="${NAME%%@*}"
mkdir -p "$(dirname "$WATERMARK_FILE")"
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
    awk -F $'\t' -v name="$TARGET_NAME" '$1 == name && $3 == "1" && $4 == "1" { print $2 }'
)"
if [[ -z "$PANE" || "$PANE" == *$'\n'* ]]; then
  echo "UNVERIFIED: tmux session '$TARGET_NAME' is not running; the mail is queued for pickup." >&2
  exit 4
fi

if [[ "$(tmux display-message -p -t "$PANE" '#{session_name}' 2>/dev/null || true)" != "$TARGET_NAME" ]]; then
  echo "UNVERIFIED: resolved pane does not belong to exact session '$TARGET_NAME'; no keys were sent." >&2
  exit 3
fi

BACKEND="$(ap_pane_backend "$PANE" 2>/dev/null || true)"
if [[ -z "$BACKEND" ]]; then
  echo "UNVERIFIED: '$NAME' is not a recognized Copilot, Claude, or Codex pane; the mail is queued and no keys were sent." >&2
  exit 3
fi

MARKER="[mb:${NEWEST_ID##*-}]"
PROMPT="check mailbox; skip if empty $MARKER"

if [[ "$BACKEND" == "copilot" && "$TERMINAL_ONLY" -eq 0 ]]; then
  if [[ ! -r "$REQUEST_CLI" ]]; then
    echo "UNVERIFIED: session-inbox request helper is unavailable; the mail is queued." >&2
    exit 3
  fi
  PROMPT_FILE="$(mktemp "${TMPDIR:-/tmp}/mailbox-poke.XXXXXX")" || exit 3
  trap 'rm -f -- "$PROMPT_FILE"' EXIT
  chmod 600 "$PROMPT_FILE"
  printf '%s' "$PROMPT" >"$PROMPT_FILE"
  ATTEMPT_FILE="$STATE_ROOT/notified/$NAME/$NEWEST_ID.attempt"
  mkdir -p "$(dirname "$ATTEMPT_FILE")"
  ATTEMPT_ID=""
  [[ -f "$ATTEMPT_FILE" ]] && ATTEMPT_ID="$(cat "$ATTEMPT_FILE" 2>/dev/null || true)"
  if [[ -z "$ATTEMPT_ID" ]]; then
    ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%S)-$$-${RANDOM:-0}"
    printf '%s\n' "$ATTEMPT_ID" >"$ATTEMPT_FILE"
  fi
  TIMEOUT=20
  [[ "$WAIT" -eq 1 ]] && TIMEOUT=35
  REQUEST_OUTPUT=""
  if REQUEST_OUTPUT="$(node "$REQUEST_CLI" send \
    --target-name "$TARGET_NAME" \
    --prompt-file "$PROMPT_FILE" \
    --mode immediate \
    --dedupe-key "mailbox:immediate-v3:$NAME:$NEWEST_ID:$ATTEMPT_ID" \
    --timeout "$TIMEOUT" 2>&1)"; then
    if grep -Eq '"delivery":"(idle|steering)"' <<<"$REQUEST_OUTPUT"; then
      printf '%s\n' "$NEWEST_ID" >"$WATERMARK_FILE"
      rm -f -- "$ATTEMPT_FILE"
      echo "poked: $NAME (SDK wakeup accepted)"
      exit 0
    fi
    if grep -Eq '"ambiguousSideEffect":true|"delivery":"unconfirmed"' <<<"$REQUEST_OUTPUT"; then
      printf '%s\n' "$(date -u +%Y%m%dT%H%M%S)-$$-${RANDOM:-0}" >"$ATTEMPT_FILE"
    fi
    echo "UNVERIFIED: '$NAME' did not confirm that the SDK delivered the wakeup; the envelope remains pending for a later attempt." >&2
    exit 3
  fi
  if grep -Eq '"ambiguousSideEffect":true|"delivery":"unconfirmed"' <<<"$REQUEST_OUTPUT"; then
    printf '%s\n' "$(date -u +%Y%m%dT%H%M%S)-$$-${RANDOM:-0}" >"$ATTEMPT_FILE"
  fi
  echo "UNVERIFIED: '$NAME' did not acknowledge the SDK wakeup; the envelope and request remain queued." >&2
  exit 3
fi

verify_copilot_fallback_identity() {
  local inbox_root="${COPILOT_SESSION_INBOX_DIR:-$HOME/.copilot/session-inbox}"
  local session_state_root="${COPILOT_SESSION_STATE_ROOT:-$HOME/.copilot/session-state}"
  [[ -n "$EXPECTED_SESSION_ID" && -n "$EXPECTED_GENERATION" ]] || return 1
  [[ "$EXPECTED_HOST_PID" =~ ^[0-9]+$ ]] || return 1
  ap_pane_contains_pid "$PANE" "$EXPECTED_HOST_PID" || return 1
  node -e '
      const fs = require("node:fs");
      const path = require("node:path");
      const [root, stateRoot, targetName, sessionId, generation, hostPid] =
        process.argv.slice(1);
      if (fs.existsSync(path.join(stateRoot, sessionId, "rotation.barrier"))) process.exit(1);
      const now = Date.now();
      const matches = [];
      for (const name of fs.readdirSync(path.join(root, "instances"))) {
        if (!name.endsWith(".json")) continue;
        try {
          const instance = JSON.parse(
            fs.readFileSync(path.join(root, "instances", name), "utf8"),
          );
          const age = now - Date.parse(instance.updatedAt);
          if (
            instance.tmuxSession === targetName &&
            Number.isFinite(age) &&
            age >= 0 &&
            age <= 15_000
          ) {
            matches.push(instance);
          }
        } catch {}
      }
      if (matches.length !== 1) process.exit(1);
      const instance = matches[0];
      if (
        instance.sessionId !== sessionId ||
        instance.generation !== generation ||
        String(instance.hostPid) !== hostPid
      ) {
        process.exit(1);
      }
    ' \
    "$inbox_root" \
    "$session_state_root" \
    "$TARGET_NAME" \
    "$EXPECTED_SESSION_ID" \
    "$EXPECTED_GENERATION" \
    "$EXPECTED_HOST_PID"
}

if [[ "$BACKEND" == "copilot" && "$TERMINAL_ONLY" -eq 1 ]]; then
  if ! verify_copilot_fallback_identity; then
    echo "UNVERIFIED: '$NAME' no longer matches the session authorized for terminal fallback; no keys were sent." >&2
    exit 3
  fi
fi

agent_ready() { ap_pane_accepts_input "$PANE" "$BACKEND"; }

if [[ "$WAIT" -eq 1 ]]; then
  for _ in $(seq 1 60); do
    agent_ready && break
    sleep 0.5
  done
fi

if ! agent_ready; then
  echo "UNVERIFIED: '$NAME' is not at a ready $BACKEND prompt; the mail is queued and no keys were sent." >&2
  exit 3
fi

if [[ "$BACKEND" == "copilot" && "$TERMINAL_ONLY" -eq 1 ]] &&
  ! verify_copilot_fallback_identity; then
  echo "UNVERIFIED: '$NAME' changed before terminal fallback input; no keys were sent." >&2
  exit 3
fi

PROMPT_SIGNATURE="$(ap_input_signature <<<"$PROMPT")"

# Reads the pane into BOX ("empty", "text", or "none") and INPUT_SIGNATURE.
# "none" means the input box could not be located at all, which is not the same
# as an empty box and must never be treated as a successful submission.
read_input() {
  local text
  if text="$(ap_input_region "$BACKEND" <<<"$SCREEN")"; then
    INPUT_SIGNATURE="$(ap_input_signature <<<"$text")"
    [[ -z "$INPUT_SIGNATURE" ]] && BOX=empty || BOX=text
  else
    INPUT_SIGNATURE=""
    BOX=none
  fi
}

if tmux send-keys -t "$PANE" -l -- "$PROMPT"; then
  SUBMITTED=0
  for _ in 1 2 3 4; do
    SCREEN="$(ap_capture "$PANE" "$BACKEND" 2>/dev/null || true)"
    read_input

    if [[ "$BOX" == empty ]] && grep -Fq "$MARKER" <<<"$SCREEN"; then
      SUBMITTED=1
      break
    fi

    if ! ap_pane_is_backend "$PANE" "$BACKEND"; then
      break
    fi

    if [[ "$INPUT_SIGNATURE" == "$PROMPT_SIGNATURE" ]]; then
      if [[ "$BACKEND" == "copilot" && "$TERMINAL_ONLY" -eq 1 ]] &&
        ! verify_copilot_fallback_identity; then
        break
      fi
      tmux send-keys -t "$PANE" Enter
    elif [[ "$BOX" != empty ]]; then
      break
    fi

    # Copilot can take a few seconds to move submitted text into the transcript.
    # Do not send another Enter during that transition.
    for _ in 1 2 3 4 5 6; do
      sleep 0.5
      SCREEN="$(ap_capture "$PANE" "$BACKEND" 2>/dev/null || true)"
      read_input
      if [[ "$BOX" == empty ]] && grep -Fq "$MARKER" <<<"$SCREEN"; then
        SUBMITTED=1
        break 2
      fi
      if [[ "$BOX" != empty && "$INPUT_SIGNATURE" != "$PROMPT_SIGNATURE" ]]; then
        break 2
      fi
    done
  done
  if [[ "$SUBMITTED" -eq 1 ]]; then
    # Mark this envelope as already-poked-about so re-attaches don't re-nag.
    # New mail will get a newer ID and re-trigger naturally.
    printf '%s\n' "$NEWEST_ID" >"$WATERMARK_FILE"
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
