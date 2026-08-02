#!/usr/bin/env bash
# Fail-loud freshness and liveness check for the dreaming daemon.

set -u
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state}"
DREAM_DIR="${DREAMING_STATE_DIR:-$STATE_DIR/dreaming}"
LOG_DIR="$STATE_DIR/daemon-logs"
HALT="$STATE_DIR/skill-review/disable-daemon"
ALERT_FILE="$STATE_DIR/skill-review/last-watchdog-alert.json"
RESULT_FILE="$STATE_DIR/skill-review/last-watchdog-result.json"
NOW="${DREAMING_NOW_EPOCH:-$(date +%s)}"
CURRENT_BUCKET=$((NOW / 604800))
mkdir -p "$STATE_DIR/skill-review"

fails=()
advisories=()
notify() {
  local title="$1" body="${2//\"/\\\"}"
  /usr/bin/osascript -e "display notification \"$body\" with title \"$title\" sound name \"Basso\"" 2>/dev/null || true
}

latest_log="$(ls -t "$LOG_DIR"/*-dreaming.log 2>/dev/null | head -1)"
latest_run="$(ls -t "$DREAM_DIR"/runs/*.json 2>/dev/null | head -1)"
if [[ -z "$latest_log" ]]; then
  fails+=("no_dreaming_logs")
else
  age_hours=$(( (NOW - $(stat -f %m "$latest_log")) / 3600 ))
  (( age_hours <= 25 )) || fails+=("dreaming_log_stale:${age_hours}h")
  grep -q "Permission denied and could not request permission" "$latest_log" 2>/dev/null &&
    fails+=("permission_denied")
fi

latest_status="missing"
latest_reason="missing"
if [[ -z "$latest_run" ]]; then
  fails+=("no_run_record")
else
  run_age_hours=$(( (NOW - $(stat -f %m "$latest_run")) / 3600 ))
  (( run_age_hours <= 25 )) || fails+=("run_record_stale:${run_age_hours}h")
  read -r latest_status latest_reason < <(/usr/bin/python3 - "$latest_run" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get("status","missing"), d.get("reason","missing"))
PY
)
  [[ "$latest_status" != "aborted" ]] || fails+=("latest_run_aborted:${latest_reason}")
fi

success_bucket="-1"
if [[ -f "$DREAM_DIR/cadence.json" ]]; then
  success_bucket="$(/usr/bin/python3 - "$DREAM_DIR/cadence.json" <<'PY'
import json,sys
print(int(json.load(open(sys.argv[1])).get("last_success_bucket",-1)))
PY
)"
fi
if (( success_bucket < 0 || CURRENT_BUCKET - success_bucket > 2 )); then
  fails+=("successful_cadence_overdue")
fi

if [[ -e "$HALT" ]]; then
  advisories+=("halt_switch_present")
  notify "Skills dreaming: HALT SWITCH ACTIVE" "Maintenance is paused via the shared halt switch."
fi

failures_json="[]"
advisories_json="[]"
if (( ${#fails[@]} > 0 )); then
  failures_json="$(printf '%s\n' "${fails[@]}" | /usr/bin/python3 -c 'import json,sys; print(json.dumps([x.strip() for x in sys.stdin if x.strip()]))')"
fi
if (( ${#advisories[@]} > 0 )); then
  advisories_json="$(printf '%s\n' "${advisories[@]}" | /usr/bin/python3 -c 'import json,sys; print(json.dumps([x.strip() for x in sys.stdin if x.strip()]))')"
fi
cat > "$RESULT_FILE" <<EOF
{
  "checked_at_epoch": $NOW,
  "latest_log": "$(basename "${latest_log:-none}")",
  "latest_status": "$latest_status",
  "latest_reason": "$latest_reason",
  "latest_run_age_hours": ${run_age_hours:-null},
  "last_success_bucket": $success_bucket,
  "current_bucket": $CURRENT_BUCKET,
  "failures": $failures_json,
  "advisories": $advisories_json
}
EOF

if (( ${#fails[@]} > 0 )); then
  cp "$RESULT_FILE" "$ALERT_FILE"
  notify "Skills dreaming: WATCHDOG FAILURE" "${fails[*]}"
  echo "FAIL  ${fails[*]}" >&2
  exit 1
fi
rm -f "$ALERT_FILE"
echo "PASS  status=$latest_status reason=$latest_reason success_bucket=$success_bucket"
