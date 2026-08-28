#!/usr/bin/env bash
# mailbox-send.sh <recipient-name> --summary "..." --message "..." [--file PATH ...]
# Writes a durable envelope under ~/.copilot/mailbox/<recipient>/pending/, copies
# any attachments, then attempts a best-effort SDK wakeup by live session name.
# Claude and Codex retain the guarded tmux fallback on macOS.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/_common.sh"

usage() { echo "usage: mailbox-send.sh <recipient> --summary <s> --message <m> [--file <path>]..." >&2; exit 2; }
[[ $# -lt 1 ]] && usage
RECIPIENT="$1"; shift
SUMMARY=""; MESSAGE=""; FILES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --summary) SUMMARY="$2"; shift 2 ;;
    --message) MESSAGE="$2"; shift 2 ;;
    --file)    FILES+=("$2"); shift 2 ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done
[[ -z "$SUMMARY" || -z "$MESSAGE" ]] && usage

FROM_NAME="$(own_name 2>/dev/null || echo unknown)"
NODE_ARGS=(send "$RECIPIENT" --summary "$SUMMARY" --message "$MESSAGE" --from "$FROM_NAME" --no-wakeup)
if [[ ${#FILES[@]} -gt 0 ]]; then
  for f in "${FILES[@]}"; do NODE_ARGS+=(--file "$f"); done
fi
node "$SCRIPT_DIR/mailbox.mjs" "${NODE_ARGS[@]}"

# === wakeup attempt ===
# Delegate to mailbox-poke.sh so the high-water-mark dedup applies to ALL
# wakeup paths (send + ca-attach + ca-cold-start) uniformly. Poke is a
# no-op if newest envelope was already poked-about or recipient session
# isn't running.
# The poke reports whether it actually saw the recipient submit the message.
# Report that verdict rather than the mere fact that keys were sent: an
# unsubmitted poke sits in the recipient's input box and wakes nobody.
WAKEUP_STATUS="not_attempted"
set +e
"$SCRIPT_DIR/mailbox-poke.sh" "$RECIPIENT" >/dev/null 2>&1
POKE_STATUS=$?
set -e
if [[ "$POKE_STATUS" -eq 0 ]]; then
  WAKEUP_STATUS="delivered"
elif [[ "$POKE_STATUS" -eq 5 ]]; then
  WAKEUP_STATUS="deferred"
elif [[ "$POKE_STATUS" -eq 4 ]]; then
  WAKEUP_STATUS="not_attempted"
else
  WAKEUP_STATUS="unverified"
fi

case "$WAKEUP_STATUS" in
  delivered)     echo "wakeup: recipient accepted the mailbox nudge (verified)" ;;
  deferred)      echo "wakeup: deferred to the recipient machine watcher; envelope waits in pending/" ;;
  unverified)    echo "wakeup: recipient did not acknowledge the nudge (NOT verified) — envelope waits in pending/ and will be re-poked" ;;
  not_attempted) echo "wakeup: skipped (no active session named '$RECIPIENT'; envelope waits in pending/)" ;;
esac

# Always-on macOS notification — works regardless of TUI state.
if command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"$SUMMARY\" with title \"mailbox -> $RECIPIENT\" subtitle \"from $FROM_NAME\"" 2>/dev/null || true
fi
