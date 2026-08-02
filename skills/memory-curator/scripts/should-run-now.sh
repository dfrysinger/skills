#!/usr/bin/env bash
# should-run-now.sh — weekly interval gate for the memory-curator daemon.
# Mirrors skill-curator/should-run-now.sh: exit 0 (proceed) if enabled and
# >= interval_hours since last run; else exit 1 (skip this tick). First run is
# deferred one interval (seed + wait), matching Hermes.
#
# State: ~/.copilot/skill-state/memory-curator/state.json
#   { "paused": false, "last_run_at": "<iso>", "interval_hours": 168 }
#
# Usage: should-run-now.sh   (prints reason to stderr)

set -u
STATE_DIR="$HOME/.copilot/skill-state/memory-curator"
STATE="$STATE_DIR/state.json"
mkdir -p "$STATE_DIR"
[ -f "$STATE" ] || echo '{"paused":false,"last_run_at":null,"interval_hours":168}' > "$STATE"

read_key() { /usr/bin/python3 -c "import json,sys;print(json.load(open('$STATE')).get('$1',''))" 2>/dev/null; }
set_last() { /usr/bin/python3 - "$1" <<PY
import json,sys
s=json.load(open("$STATE")); s["last_run_at"]=sys.argv[1]; json.dump(s,open("$STATE","w"))
PY
}

PAUSED="$(read_key paused)"
if [ "$PAUSED" = "True" ]; then echo "memory-curator: paused — skipping" >&2; exit 1; fi

LAST="$(read_key last_run_at)"
if [ -z "$LAST" ] || [ "$LAST" = "None" ]; then
  set_last "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
  echo "memory-curator: first observation — seeded last_run_at, deferring one interval" >&2
  exit 1
fi

INTERVAL="$(read_key interval_hours)"; [ -n "$INTERVAL" ] && [ "$INTERVAL" != "None" ] || INTERVAL=168
HOURS_SINCE="$(/usr/bin/python3 -c "
from datetime import datetime,timezone
l=datetime.fromisoformat('$LAST'.replace('Z','+00:00'))
if l.tzinfo is None: l=l.replace(tzinfo=timezone.utc)
print(int((datetime.now(timezone.utc)-l).total_seconds()//3600))
")"

if [ "$HOURS_SINCE" -ge "$INTERVAL" ]; then
  echo "memory-curator: ${HOURS_SINCE}h since last run >= ${INTERVAL}h — proceeding" >&2
  exit 0
else
  echo "memory-curator: only ${HOURS_SINCE}h since last run (need ${INTERVAL}h) — skipping" >&2
  exit 1
fi
