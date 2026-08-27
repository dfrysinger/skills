#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mailbox-send-test.XXXXXX")"
trap '/bin/rm -rf -- "$ROOT"' EXIT
mkdir -p "$ROOT/bin"

cat >"$ROOT/bin/node" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$MAILBOX_SEND_NODE_ARGS"
EOF
chmod +x "$ROOT/bin/node"

cat >"$ROOT/bin/osascript" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$ROOT/bin/osascript"

cat >"$ROOT/bin/tmux" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$ROOT/bin/tmux"

export PATH="$ROOT/bin:/usr/bin:/bin"
export MAILBOX_ROOT="$ROOT/mailbox"
export MAILBOX_STATE_ROOT="$ROOT/mailbox-state"
export MAILBOX_SEND_NODE_ARGS="$ROOT/node-args"

set +e
output="$(/bin/bash "$SCRIPT_DIR/mailbox-send.sh" hotel \
  --summary "no attachments" \
  --message "bash 3.2 empty array proof" 2>&1)"
status=$?
set -e

[[ "$status" -eq 0 ]] || {
  printf '%s\n' "$output" >&2
  exit "$status"
}
grep -Fq "send hotel --summary no attachments --message bash 3.2 empty array proof" \
  "$MAILBOX_SEND_NODE_ARGS"

# --message-file / --summary-file forward the path through to node (the shell
# never touches the prose, so backticks/$()/braces in a file are safe).
printf 'summary from file\n' >"$ROOT/s.txt"
printf 'body with `backticks` and $(x) and { braces }\n' >"$ROOT/m.txt"
: >"$MAILBOX_SEND_NODE_ARGS"
set +e
output="$(/bin/bash "$SCRIPT_DIR/mailbox-send.sh" hotel \
  --summary-file "$ROOT/s.txt" \
  --message-file "$ROOT/m.txt" 2>&1)"
status=$?
set -e
[[ "$status" -eq 0 ]] || { printf '%s\n' "$output" >&2; exit "$status"; }
grep -Fq "send hotel --summary-file $ROOT/s.txt --message-file $ROOT/m.txt" \
  "$MAILBOX_SEND_NODE_ARGS"

# --message with --message-file is rejected without invoking node.
: >"$MAILBOX_SEND_NODE_ARGS"
set +e
output="$(/bin/bash "$SCRIPT_DIR/mailbox-send.sh" hotel \
  --summary "s" --message "a" --message-file "$ROOT/m.txt" 2>&1)"
status=$?
set -e
[[ "$status" -ne 0 ]] || { echo "expected rejection when both --message forms given" >&2; exit 1; }
[[ ! -s "$MAILBOX_SEND_NODE_ARGS" ]] || { echo "node should not run on rejected args" >&2; exit 1; }

echo "mailbox-send tests passed"
