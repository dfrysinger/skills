#!/usr/bin/env bash
# daemon-run.sh — unattended launchd wrapper for the skills self-learning daemon.
#
# Invokes Copilot CLI headlessly with a version-controlled runbook prompt, under
# a shared PID+staleness lock so the sweep and the curator tick never overlap.
# Used by both LaunchAgents:
#   com.dfrysinger.skills.sweep.plist    (writes only to the local skills root)
#   com.dfrysinger.skills.curator.plist  (dry-run: report only)
#
# Two-root model: the daemon NEVER touches the public repo ~/code/skills. It
# writes only to the local native root ~/.copilot/skills (a local git repo with
# NO remote — nothing is pushed) and the state dir ~/.copilot/skill-state. So
# there is no git-auth / pull / push / clean-public-tree handling here.
#
# Usage:
#   daemon-run.sh --prompt <file> --name <session-name>
#
# Design notes (from rubber-duck review):
#   - Shared lock (two writers) with PID-liveness + age staleness so a
#     crash can't dead-stop the daemon forever.
#   - Halt switch: ~/.copilot/skill-state/skill-review/disable-daemon halts both jobs.
#   - --no-custom-instructions on the copilot call: the runbook prompt is
#     self-contained, and this prevents the headless run from re-triggering the
#     Tier-2 end-of-task review dispatch (recursion guard).

set -u

# --- environment (launchd gives a minimal PATH) --------------------------------
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="$HOME/code/skills"
LOCAL_ROOT="$HOME/.copilot/skills"
COPILOT="$HOME/.local/bin/copilot"
STATE_DIR="$HOME/.copilot/skill-state"
LOG_DIR="$STATE_DIR/daemon-logs"
LOCK_DIR="$STATE_DIR/daemon.lock"
HALT_SWITCH="$STATE_DIR/skill-review/disable-daemon"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-daemon.sh
source "$SCRIPT_DIR/lib-daemon.sh"
STALE_SECS=7200          # 2h: a lock older than this with a dead PID is stolen
LOG_RETENTION_DAYS=30

PROMPT_FILE=""
SESSION_NAME="skills-daemon"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt)   PROMPT_FILE="$2"; shift 2 ;;
    --name)     SESSION_NAME="$2"; shift 2 ;;
    *) echo "daemon-run.sh: unknown arg '$1'" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/${TS}-${SESSION_NAME}.log"

log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "$LOG"; }

fail_notify() {
  # best-effort macOS notification; never fatal
  /usr/bin/osascript -e "display notification \"$1\" with title \"skills daemon\"" >/dev/null 2>&1 || true
}

# --- preconditions -------------------------------------------------------------
[[ -n "$PROMPT_FILE" && -f "$PROMPT_FILE" ]] || { echo "daemon-run.sh: --prompt file missing" >&2; exit 2; }

if [[ -e "$HALT_SWITCH" ]]; then
  log "halt switch present ($HALT_SWITCH) — exiting without running."
  exit 0
fi

[[ -x "$COPILOT" ]] || { log "copilot binary not found/executable at $COPILOT"; fail_notify "copilot binary missing"; exit 1; }

# No git-auth / pull setup: the daemon writes only to the local root (no remote)
# and never touches the public repo, so there is nothing to authenticate or sync.

# --- shared lock with PID-liveness + staleness ---------------------------------
OWNED=0
acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    OWNED=1
  else
    local lpid lstart age
    lpid="$(cat "$LOCK_DIR/pid" 2>/dev/null || echo "")"
    lstart="$(cat "$LOCK_DIR/start" 2>/dev/null || echo 0)"
    age=$(( $(date +%s) - lstart ))
    if [[ -n "$lpid" ]] && kill -0 "$lpid" 2>/dev/null && (( age < STALE_SECS )); then
      log "another daemon run is active (pid=$lpid, age=${age}s) — exiting."
      exit 0
    fi
    log "stealing stale lock (pid=${lpid:-none}, age=${age}s)."
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" 2>/dev/null && OWNED=1
  fi
  [[ "$OWNED" == 1 ]] || { log "could not acquire lock — exiting."; exit 0; }
  echo "$$" > "$LOCK_DIR/pid"
  date +%s > "$LOCK_DIR/start"
}
release_lock() { [[ "$OWNED" == 1 ]] && rm -rf "$LOCK_DIR"; }
trap release_lock EXIT INT TERM

acquire_lock

# --- run ----------------------------------------------------------------------
log "starting headless copilot run: name=$SESSION_NAME prompt=$PROMPT_FILE"
cd "$REPO" || { log "cannot cd $REPO"; exit 1; }

# Run lean: disable every MCP server. The sweep/curator runbooks only need the
# built-in shell/edit/read tools, and disabling MCP shaves startup time.
MCP_FLAGS=(--disable-builtin-mcps)
# Disable every custom MCP server too, derived from the live config so this
# stays correct if the user adds/removes servers.
MCP_CONFIG="$HOME/.copilot/mcp-config.json"
if [[ -f "$MCP_CONFIG" ]]; then
  while IFS= read -r s; do
    [[ -n "$s" ]] && MCP_FLAGS+=(--disable-mcp-server "$s")
  done < <(/usr/bin/python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1]))
    print("\n".join((d.get("mcpServers") or {}).keys()))
except Exception:
    pass' "$MCP_CONFIG" 2>/dev/null)
fi

# Under launchd the headless copilot process finishes its work and prints its
# end-of-session summary footer ("AI Credits <n> (<n>s)") but then never exits.
# The bounded runner waits for that footer (anchored to its numeric shape so
# unrelated output can't false-trigger), allows a short flush grace, then
# terminates — reporting success based on the footer, not the forced exit code.
# $LOG is a fresh per-run file, so a stale footer can't cause a false completion.
DONE_RE='AI Credits[[:space:]]+[0-9]'
ABS_MAX_SECS=1800
GRACE_SECS=20

set +e
skills_run_copilot_bounded "$LOG" "$DONE_RE" "$ABS_MAX_SECS" "$GRACE_SECS" -- \
  "$COPILOT" -p "$(cat "$PROMPT_FILE")" \
  --allow-all --no-custom-instructions --no-color --no-remote \
  "${MCP_FLAGS[@]}" \
  --log-level error -n "$SESSION_NAME"
completed=$?
set -e 2>/dev/null || true

# The footer proves the process stopped, not that the work happened: an agent
# that aborted on a guard, or did nothing at all, prints the same footer. Success
# additionally requires the run's own status sentinel (see sweep-prompt.txt).
RESULT_LINE=$(grep -a 'SKILL_REVIEW_RESULT:' "$LOG" | tail -1 || true)

if (( completed != 0 )); then
  log "headless run did NOT complete within ${ABS_MAX_SECS}s (no footer) — see $LOG"
  fail_notify "$SESSION_NAME did not complete — see $LOG"
  rc=1
elif [[ -z "$RESULT_LINE" ]]; then
  log "headless run stopped but reported no result sentinel — see $LOG"
  fail_notify "$SESSION_NAME finished without reporting a result — see $LOG"
  rc=1
elif [[ "$RESULT_LINE" == *"SKILL_REVIEW_RESULT: ok"* ]]; then
  log "headless run completed: ${RESULT_LINE#*SKILL_REVIEW_RESULT: }"
  rc=0
else
  log "headless run reported failure: ${RESULT_LINE#*SKILL_REVIEW_RESULT: }"
  fail_notify "$SESSION_NAME aborted: ${RESULT_LINE#*SKILL_REVIEW_RESULT: }"
  rc=1
fi

# --- log retention -------------------------------------------------------------
find "$LOG_DIR" -name '*.log' -type f -mtime +"$LOG_RETENTION_DAYS" -delete 2>/dev/null || true

exit "$rc"
