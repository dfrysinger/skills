#!/usr/bin/env bash
# mailbox-list.sh — show all known mailboxes and active tmux sessions.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/_common.sh"

echo "=== mailboxes (~/.copilot/mailbox) ==="
if [[ -d "$MAILBOX_ROOT" ]]; then
  shopt -s nullglob
  for d in "$MAILBOX_ROOT"/*/; do
    [[ -d "$d" ]] || continue
    name="$(basename "$d")"
    pending=("$d"pending/*.json)
    delivered=("$d"delivered/*.json)
    printf "  %-20s  pending=%d  delivered=%d\n" "$name" "${#pending[@]}" "${#delivered[@]}"
  done
else
  echo "  (none)"
fi
echo
echo "=== active tmux sessions ==="
tmux list-sessions 2>/dev/null | awk -F: '{print "  "$1}' || echo "  (tmux not running)"
