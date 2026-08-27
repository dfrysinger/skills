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
echo "mailbox-send tests passed"
