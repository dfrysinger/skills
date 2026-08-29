# shellcheck shell=bash
# common helpers for mailbox scripts.
set -euo pipefail
MAILBOX_LOCAL_ROOT="${MAILBOX_LOCAL_ROOT:-${MAILBOX_ROOT:-$HOME/.copilot/mailbox}}"

own_name() {
  # current tmux session name = agent name (per `ca` convention)
  if [[ -n "${TMUX:-}" ]]; then
    tmux display-message -p '#{session_name}'
  else
    echo "ERROR: not running inside tmux; mailbox needs tmux for routing." >&2
    return 1
  fi
}

ts_id() {  # 20260604T152011Z-<short-uuid>
  local d
  d="$(date -u +%Y%m%dT%H%M%SZ)"
  local u
  u="$(uuidgen 2>/dev/null | tr '[:upper:]' '[:lower:]' | cut -c1-8)" || u="$(printf '%08x' $RANDOM$RANDOM)"
  echo "${d}-${u}"
}

ensure_mailbox() {  # ensure_mailbox <name>
  mkdir -p "$MAILBOX_LOCAL_ROOT/$1/pending" "$MAILBOX_LOCAL_ROOT/$1/delivered"
}
