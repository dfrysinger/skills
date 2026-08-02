#!/usr/bin/env bash
# daemon-watchdog.sh — fail-loud freshness check for the skills self-learning
# daemon. Runs daily after the sweep should have completed. If anything looks
# wrong, it fires a macOS notification AND writes a structured alert file so
# the user discovers silent outages on day 1, not day 7.
#
# Checks (each emits its own alert if it fails):
#   1. Sweep log freshness — newest *-skills-sweep.log must be < 25h old.
#      Catches "launchd job didn't fire at all" failures (logged-out user,
#      laptop asleep past the wake window, agent booted out, plist missing).
#   2. Sweep run completion — newest sweep log must contain the
#      "headless run completed" footer. Catches abort/timeout/crash mid-run.
#   3. Sweep run health — newest sweep log must NOT contain "Permission denied
#      and could not request permission". Catches Copilot CLI permission-flag
#      regressions.
#   4. Sweep run engagement — at least ONE of:
#        a) ledger appended in last 25h (a real review happened), OR
#        b) sweep log says "Nothing to save" / "no candidates" /
#           "above the skill's threshold" (intentional no-op).
#      Catches pre-flight halts and "ran but did nothing for unclear reasons".
#   5. Halt switch advisory — if present, NOTIFY (informational, not failure)
#      so the user remembers a paused daemon.
#
# On any failure: macOS notification + a JSON alert at
#   ~/.copilot/skill-state/skill-review/last-watchdog-alert.json
# Exit code 0 = all checks passed (or only the advisory tripped); non-zero
# encodes failure bitmask for launchctl visibility.

set -u
STATE_DIR="$HOME/.copilot/skill-state"
LOG_DIR="$STATE_DIR/daemon-logs"
LEDGER="$STATE_DIR/skill-review/ledger.jsonl"
HALT="$STATE_DIR/skill-review/disable-daemon"
ALERT_FILE="$STATE_DIR/skill-review/last-watchdog-alert.json"
RESULT_FILE="$STATE_DIR/skill-review/last-watchdog-result.json"

mkdir -p "$STATE_DIR/skill-review"

now_epoch=$(date +%s)
now_iso=$(date '+%Y-%m-%dT%H:%M:%S%z')
fails=()

# macOS notification helper. Background-job notifications need a real title
# AND subtitle; without them macOS drops them silently. We also escape any
# double quotes in the message body.
notify() {
  local title="$1" body="$2"
  local body_escaped="${body//\"/\\\"}"
  /usr/bin/osascript -e "display notification \"$body_escaped\" with title \"$title\" sound name \"Basso\"" 2>/dev/null || true
}

# 1. Sweep log freshness — newest log under 25h old.
latest_log=$(ls -t "$LOG_DIR"/*-skills-sweep.log 2>/dev/null | head -1)
if [[ -z "$latest_log" ]]; then
  fails+=("no_sweep_logs_ever")
  notify "Skills daemon: NO SWEEP LOGS" "Watchdog found zero sweep logs under $LOG_DIR. Daemon may not be installed."
else
  log_mtime=$(stat -f %m "$latest_log")
  age_hours=$(( (now_epoch - log_mtime) / 3600 ))
  if (( age_hours > 25 )); then
    fails+=("sweep_log_stale:${age_hours}h")
    notify "Skills daemon: NO RECENT RUN" "Newest sweep log is ${age_hours}h old (expected <25h). LaunchAgent may not be firing. File: $(basename "$latest_log")"
  fi
fi

# 2. Run completion — newest log has the footer.
if [[ -n "$latest_log" ]] && ! grep -q "headless run completed" "$latest_log" 2>/dev/null; then
  fails+=("last_run_incomplete")
  notify "Skills daemon: LAST RUN INCOMPLETE" "Newest sweep log is missing the completion footer. Run may have crashed or timed out. File: $(basename "$latest_log")"
fi

# 3. Run health — no permission-denied (catches CLI permission-flag drift).
if [[ -n "$latest_log" ]] && grep -q "Permission denied and could not request permission" "$latest_log" 2>/dev/null; then
  fails+=("permission_denied_in_run")
  notify "Skills daemon: PERMISSION DENIED" "Sweep hit 'Permission denied' — Copilot CLI permission flag may have changed. Check daemon-run.sh --allow-all."
fi

# 4. Engagement — either ledger advanced or run explicitly said "nothing to save".
ledger_recent=0
if [[ -f "$LEDGER" ]]; then
  ledger_mtime=$(stat -f %m "$LEDGER")
  ledger_age_hours=$(( (now_epoch - ledger_mtime) / 3600 ))
  (( ledger_age_hours <= 25 )) && ledger_recent=1
fi
intentional_noop=0
if [[ -n "$latest_log" ]]; then
  if grep -qiE "nothing to save|no candidates|above the skill's threshold|backlog of lower-scoring|reviewed 0 session" "$latest_log" 2>/dev/null; then
    intentional_noop=1
  fi
fi
if (( ledger_recent == 0 && intentional_noop == 0 )); then
  # Check pre-flight halt specifically — distinct symptom worth its own alert.
  if [[ -n "$latest_log" ]] && grep -qiE "untracked|dirty.*tree|pre-flight failed|halting per" "$latest_log" 2>/dev/null; then
    fails+=("preflight_halt_no_work")
    notify "Skills daemon: PRE-FLIGHT HALT" "Sweep halted at pre-flight (likely dirty local tree). No work done. Check: ~/.copilot/skills git status"
  else
    fails+=("ran_but_no_engagement")
    notify "Skills daemon: RAN BUT NO WORK" "Sweep finished but ledger didn't advance and log doesn't say 'nothing to save'. Worth a manual look at $(basename "$latest_log")."
  fi
fi

# 5. Halt switch advisory (informational, not a failure).
halt_advisory=""
if [[ -e "$HALT" ]]; then
  halt_advisory="halt_switch_present"
  notify "Skills daemon: HALT SWITCH ACTIVE" "Daemon is intentionally paused via $HALT. Remove the file to resume."
fi

# Compose JSON result. Always written, so users can `cat` it for status.
nfails=${#fails[@]}
fails_json=$(printf '"%s",' "${fails[@]:-}" | sed 's/,$//')
[[ -z "${fails[*]:-}" ]] && fails_json=""
cat > "$RESULT_FILE" <<EOF
{
  "checked_at": "$now_iso",
  "latest_sweep_log": "$(basename "${latest_log:-none}")",
  "latest_sweep_log_age_hours": ${age_hours:-null},
  "ledger_recent_25h": $ledger_recent,
  "intentional_noop": $intentional_noop,
  "halt_switch": "${halt_advisory:-absent}",
  "failures": [${fails_json}],
  "failure_count": $nfails
}
EOF

# Alert file only written on failure — separate from the rolling result file so
# downstream tooling can `test -f last-watchdog-alert.json` for "needs human".
if (( nfails > 0 )); then
  cp "$RESULT_FILE" "$ALERT_FILE"
  echo "FAIL  $nfails check(s) failed: ${fails[*]}" >&2
  exit 1
else
  rm -f "$ALERT_FILE"
  echo "PASS  all checks ok ($latest_log age=${age_hours:-0}h ledger_recent=$ledger_recent noop=$intentional_noop)"
  exit 0
fi
