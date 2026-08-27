#!/usr/bin/env bash
# mailbox-resume-hook.sh [<name>]
# Designed to be called by the user's `ca <name>` script before launching
# Copilot CLI. Outputs a one-liner the caller can prepend/append to the
# resume prompt so the recipient agent sees mail at session start.
#
# If <name> is omitted, defaults to current tmux session name.
#
#   ca usage example:
#     RESUME_HINT="$(~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-resume-hook.sh juliett)"
#     copilot --resume <id> ${RESUME_HINT:+--prompt "$RESUME_HINT"}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec node "$SCRIPT_DIR/mailbox.mjs" resume-hint "$@"
