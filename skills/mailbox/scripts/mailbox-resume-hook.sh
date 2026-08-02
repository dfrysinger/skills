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
. "$SCRIPT_DIR/_common.sh"

NAME="${1:-}"
if [[ -z "$NAME" ]]; then
  NAME="$(own_name 2>/dev/null || true)"
fi
[[ -z "$NAME" ]] && exit 0  # silent no-op

DIR="$MAILBOX_ROOT/$NAME/pending"
[[ -d "$DIR" ]] || exit 0
shopt -s nullglob
ENVS=("$DIR"/*.json)
N=${#ENVS[@]}
[[ $N -eq 0 ]] && exit 0

echo "You have $N unread mailbox envelope(s) in ~/.copilot/mailbox/$NAME/pending/. Run /mailbox check (or ~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh) to read them before continuing other work."
