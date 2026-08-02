#!/usr/bin/env bash
# mailbox-send.sh <recipient-name> --summary "..." --message "..." [--file PATH ...]
# Writes a durable envelope under ~/.copilot/mailbox/<recipient>/pending/, copies
# any attachments, then attempts a best-effort wakeup of the recipient's tmux
# pane. ALWAYS reports wakeup_status; fall-through is osascript notification +
# the recipient's `ca` resume-hook.
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

ensure_mailbox "$RECIPIENT"
ID="$(ts_id)"
ENVELOPE="$MAILBOX_ROOT/$RECIPIENT/pending/${ID}.json"
ATTACH_DIR="$MAILBOX_ROOT/$RECIPIENT/pending/${ID}"
ATTACH_NAMES=()
if [[ ${#FILES[@]} -gt 0 ]]; then
  mkdir -p "$ATTACH_DIR"
  for f in "${FILES[@]}"; do
    [[ -f "$f" ]] || { echo "ERROR: attachment not found: $f" >&2; exit 3; }
    bn="$(basename "$f")"
    # Two attachments can share a basename. Overwriting one with the other while
    # recording both names delivers a lie, so disambiguate instead.
    if [[ -e "$ATTACH_DIR/$bn" ]]; then
      stem="${bn%.*}"; ext="${bn##*.}"
      [[ "$ext" == "$bn" ]] && ext=""
      n=2
      while [[ -e "$ATTACH_DIR/${stem}-${n}${ext:+.$ext}" ]]; do n=$((n+1)); done
      bn="${stem}-${n}${ext:+.$ext}"
    fi
    cp "$f" "$ATTACH_DIR/$bn"
    ATTACH_NAMES+=("$bn")
  done
fi

FROM_NAME="$(own_name 2>/dev/null || echo unknown)"
SENT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Summary and message travel in the environment, not argv: any user on the
# machine can read a process's arguments with ps, and a message may quote a
# credential by accident. (stdin is unavailable here — it carries the program.)
MAILBOX_SUMMARY="$SUMMARY" MAILBOX_MESSAGE="$MESSAGE" \
python3 - "$ENVELOPE" "$ID" "$FROM_NAME" "$RECIPIENT" "$SENT_AT" ${ATTACH_NAMES[@]+"${ATTACH_NAMES[@]}"} <<'PY'
import json, os, sys
out, eid, frm, to, sent, *atts = sys.argv[1:]
json.dump({"id":eid,"from":{"name":frm},"to":{"name":to},
          "summary":os.environ["MAILBOX_SUMMARY"],
          "message":os.environ["MAILBOX_MESSAGE"],
          "attachments":atts,"sent_at":sent},
         open(out,"w"), indent=2)
PY
echo "envelope: $ENVELOPE"

# === wakeup attempt ===
# Delegate to mailbox-poke.sh so the high-water-mark dedup applies to ALL
# wakeup paths (send + ca-attach + ca-cold-start) uniformly. Poke is a
# no-op if newest envelope was already poked-about or recipient session
# isn't running.
# The poke reports whether it actually saw the recipient submit the message.
# Report that verdict rather than the mere fact that keys were sent: an
# unsubmitted poke sits in the recipient's input box and wakes nobody.
WAKEUP_STATUS="not_attempted"
if tmux has-session -t "$RECIPIENT" 2>/dev/null; then
  if "$SCRIPT_DIR/mailbox-poke.sh" "$RECIPIENT" >/dev/null 2>&1; then
    WAKEUP_STATUS="delivered"
  else
    WAKEUP_STATUS="unverified"
  fi
fi

case "$WAKEUP_STATUS" in
  delivered)     echo "wakeup: send-keys -> $RECIPIENT (verified)" ;;
  unverified)    echo "wakeup: send-keys -> $RECIPIENT (NOT verified) — envelope waits in pending/ and will be re-poked" ;;
  not_attempted) echo "wakeup: skipped (no tmux session named '$RECIPIENT'; envelope waits in pending/)" ;;
esac

# Always-on macOS notification — works regardless of TUI state.
if command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"$SUMMARY\" with title \"mailbox -> $RECIPIENT\" subtitle \"from $FROM_NAME\"" 2>/dev/null || true
fi
