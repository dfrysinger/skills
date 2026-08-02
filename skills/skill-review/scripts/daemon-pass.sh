#!/usr/bin/env bash
# Run one lock-free, bounded Copilot daemon pass.

set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
COPILOT="${COPILOT_BIN:-$HOME/.local/bin/copilot}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-daemon.sh
source "$SCRIPT_DIR/lib-daemon.sh"

PROMPT_FILE=""
SESSION_NAME=""
LOG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt) PROMPT_FILE="$2"; shift 2 ;;
    --name) SESSION_NAME="$2"; shift 2 ;;
    --log) LOG="$2"; shift 2 ;;
    *) echo "daemon-pass.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

[[ -n "$PROMPT_FILE" && -f "$PROMPT_FILE" ]] || {
  echo "daemon-pass.sh: --prompt file missing" >&2
  exit 2
}
[[ -n "$SESSION_NAME" && -n "$LOG" ]] || {
  echo "daemon-pass.sh: --name and --log are required" >&2
  exit 2
}
[[ -x "$COPILOT" ]] || {
  echo "daemon-pass.sh: copilot binary not executable at $COPILOT" >&2
  exit 1
}

mkdir -p "$(dirname "$LOG")"
: > "$LOG"
cd "$REPO" || exit 1

MCP_FLAGS=(--disable-builtin-mcps)
MCP_CONFIG="$HOME/.copilot/mcp-config.json"
if [[ -f "$MCP_CONFIG" ]]; then
  while IFS= read -r server; do
    [[ -n "$server" ]] && MCP_FLAGS+=(--disable-mcp-server "$server")
  done < <(/usr/bin/python3 -c 'import json,sys
try:
    data=json.load(open(sys.argv[1]))
    print("\n".join((data.get("mcpServers") or {}).keys()))
except Exception:
    pass' "$MCP_CONFIG" 2>/dev/null)
fi

DONE_RE='AI Credits[[:space:]]+[0-9]'
ABS_MAX_SECS="${DREAMING_PASS_MAX_SECS:-1800}"
GRACE_SECS="${DREAMING_PASS_GRACE_SECS:-20}"

set +e
skills_run_copilot_bounded "$LOG" "$DONE_RE" "$ABS_MAX_SECS" "$GRACE_SECS" -- \
  "$COPILOT" -p "$(<"$PROMPT_FILE")" \
  --allow-all --no-custom-instructions --no-color --no-remote \
  "${MCP_FLAGS[@]}" \
  --log-level error -n "$SESSION_NAME"
completed=$?
set -e 2>/dev/null || true

result_line="$(grep -a 'DREAM_PASS_RESULT:' "$LOG" | tail -1 || true)"
if (( completed != 0 )); then
  echo "daemon-pass.sh: $SESSION_NAME did not complete within ${ABS_MAX_SECS}s" >&2
  exit 1
fi
if [[ -z "$result_line" ]]; then
  echo "daemon-pass.sh: $SESSION_NAME reported no DREAM_PASS_RESULT sentinel" >&2
  exit 1
fi
if [[ "$result_line" == *"DREAM_PASS_RESULT: ok"* ]]; then
  echo "${result_line#*DREAM_PASS_RESULT: }"
  exit 0
fi

echo "daemon-pass.sh: ${result_line#*DREAM_PASS_RESULT: }" >&2
exit 1
