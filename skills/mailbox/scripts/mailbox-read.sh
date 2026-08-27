#!/usr/bin/env bash
# mailbox-read.sh <id>
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec node "$SCRIPT_DIR/mailbox.mjs" read "$@"
