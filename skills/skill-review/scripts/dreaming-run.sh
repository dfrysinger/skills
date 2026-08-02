#!/usr/bin/env bash
# One effective-weekly owner for consolidate -> roll -> prune.

set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
STATE_BASE="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state}"
LOG_DIR="$STATE_BASE/daemon-logs"
HALT_SWITCH="$STATE_BASE/skill-review/disable-daemon"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS_RUNNER="${DREAMING_PASS_RUNNER:-$SCRIPT_DIR/daemon-pass.sh}"
STATE_TOOL="${DREAMING_STATE_TOOL:-$SCRIPT_DIR/dreaming-state.py}"
CURATOR_STATE="${DREAMING_LEGACY_CURATOR_STATE:-$STATE_BASE/curator.json}"
MEMORY_STATE="${DREAMING_LEGACY_MEMORY_STATE:-$STATE_BASE/memory-curator/state.json}"
# shellcheck source=lib-daemon.sh
source "$SCRIPT_DIR/lib-daemon.sh"

mkdir -p "$LOG_DIR" "$STATE_BASE/dreaming"
START_EPOCH="${DREAMING_NOW_EPOCH:-$(date +%s)}"
START_ISO="$(date -u -r "$START_EPOCH" +%Y-%m-%dT%H:%M:%S+00:00)"
RUN_ID="$(date -u -r "$START_EPOCH" +%Y%m%dT%H%M%SZ)-$$"
RUN_LOG="$LOG_DIR/${RUN_ID}-dreaming.log"
PASSES_FILE="$STATE_BASE/dreaming/.passes-${RUN_ID}.tsv"
: > "$PASSES_FILE"
exec > >(/usr/bin/tee -a "$RUN_LOG") 2>&1

log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*"; }
notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"skills dreaming\"" >/dev/null 2>&1 || true
}
record_terminal() {
  local status="$1" reason="$2"
  "$STATE_TOOL" record \
    --run-id "$RUN_ID" --status "$status" --reason "$reason" \
    --started-at "$START_ISO" --start-epoch "$START_EPOCH" \
    --passes-file "$PASSES_FILE"
}
abort_with_record() {
  local reason="$1" message="$2"
  log "$message"
  if ! record_terminal aborted "$reason"; then
    log "failed to persist aborted run record for $reason"
  fi
  notify "dreaming aborted: $message"
  exit 1
}
append_pass() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" >> "$PASSES_FILE"
}
mark_remaining() {
  local reason="$1"
  shift
  local name
  for name in "$@"; do
    append_pass "$name" "not_started" "" "" "" "$reason"
  done
}
cleanup() {
  if [[ -n "${LOCK_TOKEN:-}" ]]; then
    skills_lock_release "$LOCK_TOKEN" >/dev/null 2>&1 || true
  fi
  /bin/rm -f "$PASSES_FILE"
}
trap cleanup EXIT INT TERM

if [[ -e "$HALT_SWITCH" ]]; then
  log "halt switch present; recording healthy skip"
  record_terminal skipped "halt-switch"
  exit 0
fi

LOCK_TOKEN=""
if LOCK_TOKEN="$(skills_lock_acquire process "dreaming:$RUN_ID")"; then
  :
else
  lock_rc=$?
  if (( lock_rc == 1 )); then
    log "writer lock is active or ambiguous; recording contention skip"
    record_terminal skipped "lock-contention"
    /bin/rm -f "$PASSES_FILE"
    exit 0
  fi
  log "writer lock is malformed; aborting fail closed"
  record_terminal aborted "lock-malformed"
  /bin/rm -f "$PASSES_FILE"
  notify "dreaming aborted: malformed writer lock"
  exit 1
fi

if ! "$STATE_TOOL" ensure-seed --curator "$CURATOR_STATE" --memory "$MEMORY_STATE" >/dev/null; then
  abort_with_record "state-init-failed" "cadence state initialization failed"
fi
if ! "$STATE_TOOL" repair; then
  abort_with_record "state-repair-failed" "state repair failed"
fi
if ! /usr/bin/python3 - "$MEMORY_STATE" <<'PY'
import json, os, sys, tempfile
path = os.path.expanduser(sys.argv[1])
if not os.path.exists(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state.", dir=os.path.dirname(path))
    with os.fdopen(fd, "w") as handle:
        json.dump({"paused": False, "last_run_at": None, "interval_hours": 168}, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
PY
then
  abort_with_record "memory-state-init-failed" "memory state initialization failed"
fi

if [[ -e "$HALT_SWITCH" ]]; then
  log "halt switch appeared after lock acquisition"
  record_terminal skipped "halt-switch"
  exit 0
fi

if [[ "${DREAMING_FORCE_DUE:-0}" != "1" ]]; then
  set +e
  "$STATE_TOOL" due
  due_rc=$?
  set -e
  if (( due_rc == 1 )); then
    log "weekly bucket already completed; recording cadence skip"
    record_terminal skipped "cadence-not-due"
    exit 0
  elif (( due_rc != 0 )); then
    abort_with_record "cadence-eval-failed" "cadence state could not be evaluated"
  fi
fi

PASSES=(consolidate roll prune)
PROMPTS=(
  "$REPO/skills/skill-review/references/sweep-prompt.txt"
  "$REPO/skills/memory-curator/references/memory-curate-prompt.txt"
  "$REPO/skills/skill-curator/references/tick-prompt.txt"
)
NAMES=(skills-consolidate skills-roll skills-prune)

for index in 0 1 2; do
  pass="${PASSES[$index]}"
  if [[ -e "$HALT_SWITCH" ]]; then
    log "halt switch appeared before $pass"
    append_pass "$pass" "not_started" "" "" "" "halt-switch"
    if (( index < 2 )); then
      mark_remaining "upstream-halted" "${PASSES[@]:$((index + 1))}"
    fi
    record_terminal aborted "halt-before-$pass"
    exit 1
  fi
  if ! skills_lock_renew "$LOCK_TOKEN"; then
    log "lost writer lock before $pass"
    append_pass "$pass" "not_started" "" "" "" "lock-lost"
    if (( index < 2 )); then
      mark_remaining "upstream-lock-lost" "${PASSES[@]:$((index + 1))}"
    fi
    record_terminal aborted "lock-lost-before-$pass"
    exit 1
  fi

  pass_started_epoch="${DREAMING_NOW_EPOCH:-$(date +%s)}"
  pass_started="$(date -u -r "$pass_started_epoch" +%Y-%m-%dT%H:%M:%S+00:00)"
  pass_log="$LOG_DIR/${RUN_ID}-${pass}.log"
  log "starting $pass"
  if DREAMING_ORCHESTRATED=1 SKILLS_LOCK_HELD_BY_PARENT=1 "$PASS_RUNNER" \
      --prompt "${PROMPTS[$index]}" --name "${NAMES[$index]}" --log "$pass_log"; then
    pass_ended_epoch="${DREAMING_NOW_EPOCH:-$(date +%s)}"
    pass_ended="$(date -u -r "$pass_ended_epoch" +%Y-%m-%dT%H:%M:%S+00:00)"
    append_pass "$pass" "ok" "$pass_started" "$pass_ended" "$pass_log" ""
    log "$pass completed"
  else
    pass_ended_epoch="${DREAMING_NOW_EPOCH:-$(date +%s)}"
    pass_ended="$(date -u -r "$pass_ended_epoch" +%Y-%m-%dT%H:%M:%S+00:00)"
    append_pass "$pass" "aborted" "$pass_started" "$pass_ended" "$pass_log" "pass-failed"
    if (( index < 2 )); then
      mark_remaining "upstream-failed" "${PASSES[@]:$((index + 1))}"
    fi
    record_terminal aborted "$pass-failed"
    notify "dreaming aborted in $pass"
    exit 1
  fi
done

record_terminal ok "completed"
"$STATE_TOOL" commit-success --run-id "$RUN_ID"
log "dreaming pipeline completed"

find "$LOG_DIR" -name '*.log' -type f -mtime +30 -delete 2>/dev/null || true
