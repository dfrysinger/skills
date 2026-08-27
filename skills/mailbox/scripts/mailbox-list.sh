#!/usr/bin/env bash
# mailbox-list.sh — show all known mailboxes and active tmux sessions.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
node "$SCRIPT_DIR/mailbox.mjs" list "$@"
echo
echo "=== active tmux sessions ==="
tmux list-sessions 2>/dev/null | awk -F: '{print "  "$1}' || echo "  (tmux not running)"
