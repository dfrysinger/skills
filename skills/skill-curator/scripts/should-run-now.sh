#!/usr/bin/env bash
# should-run-now.sh — interval gate for the curator.
# Mirrors Hermes Agent's agent/curator.should_run_now(): returns exit 0 (TRUE)
# if curator is enabled, not paused, and >= interval_hours since last_run_at.
# Otherwise exit 1 (skip this tick).
#
# Use from the SKILL.md `tick` mode to decide whether to proceed with a full
# dry-run pass on this scheduled invocation. Prints a one-line status to
# stderr so the agent can show why it skipped.
#
# Usage: should-run-now.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE=$("$SCRIPT_DIR/curator-state.sh" read)

PAUSED=$(printf '%s' "$STATE" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("paused", False))')
if [[ "$PAUSED" == "True" ]]; then
  echo "curator: paused — skipping tick" >&2
  exit 1
fi

# First run: Hermes defers the very first run by one full interval (seed and
# wait). We do the same: if last_run_at is null, seed it to now and skip.
LAST=$(printf '%s' "$STATE" | python3 -c 'import json,sys; v=json.load(sys.stdin).get("last_run_at"); print(v or "")')
if [[ -z "$LAST" ]]; then
  "$SCRIPT_DIR/curator-state.sh" set last_run_at "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" >/dev/null
  "$SCRIPT_DIR/curator-state.sh" set last_run_summary "deferred first run — seeded; next dry-run in 168h" >/dev/null
  echo "curator: first observation — seeded last_run_at, deferring first real run by one interval" >&2
  exit 1
fi

INTERVAL_HOURS=$(printf '%s' "$STATE" | python3 -c '
import json, sys
s = json.load(sys.stdin)
o = (s.get("config_overrides") or {}).get("interval_hours")
print(int(o) if o is not None else 168)
')

HOURS_SINCE=$(python3 -c "
from datetime import datetime, timezone
last = datetime.fromisoformat('$LAST'.replace('Z', '+00:00'))
if last.tzinfo is None:
    last = last.replace(tzinfo=timezone.utc)
delta = datetime.now(timezone.utc) - last
print(int(delta.total_seconds() // 3600))
")

if [[ "$HOURS_SINCE" -ge "$INTERVAL_HOURS" ]]; then
  echo "curator: ${HOURS_SINCE}h since last run >= ${INTERVAL_HOURS}h interval — proceeding" >&2
  exit 0
else
  REMAINING=$((INTERVAL_HOURS - HOURS_SINCE))
  echo "curator: only ${HOURS_SINCE}h since last run (need ${INTERVAL_HOURS}h) — ${REMAINING}h remaining, skipping" >&2
  exit 1
fi
