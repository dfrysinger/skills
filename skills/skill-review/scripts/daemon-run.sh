#!/usr/bin/env bash
# Compatibility wrapper for one manually scheduled daemon pass.

set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state}"
LOG_DIR="$STATE_DIR/daemon-logs"
HALT_SWITCH="$STATE_DIR/skill-review/disable-daemon"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS_RUNNER="${DREAMING_PASS_RUNNER:-$SCRIPT_DIR/daemon-pass.sh}"
# shellcheck source=lib-daemon.sh
source "$SCRIPT_DIR/lib-daemon.sh"

PROMPT_FILE=""
SESSION_NAME="skills-daemon"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt) PROMPT_FILE="$2"; shift 2 ;;
    --name) SESSION_NAME="$2"; shift 2 ;;
    *) echo "daemon-run.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

[[ -n "$PROMPT_FILE" && -f "$PROMPT_FILE" ]] || {
  echo "daemon-run.sh: --prompt file missing" >&2
  exit 2
}
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y%m%d-%H%M%S)-${SESSION_NAME}.log"

if [[ -e "$HALT_SWITCH" ]]; then
  echo "halt switch present ($HALT_SWITCH); exiting without running"
  exit 0
fi

LOCK_TOKEN=""
if ! LOCK_TOKEN="$(skills_lock_acquire process "single-pass:$SESSION_NAME")"; then
  echo "daemon-run.sh: shared writer lock unavailable" >&2
  exit 1
fi
trap 'skills_lock_release "$LOCK_TOKEN" >/dev/null 2>&1 || true' EXIT INT TERM

SKILLS_LOCK_HELD_BY_PARENT=1 \
  "$PASS_RUNNER" --prompt "$PROMPT_FILE" --name "$SESSION_NAME" --log "$LOG"
