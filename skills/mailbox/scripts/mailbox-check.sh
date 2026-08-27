#!/usr/bin/env bash
# mailbox-check.sh
# Lists pending envelopes addressed to the current agent.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec node "$SCRIPT_DIR/mailbox.mjs" check "$@"
