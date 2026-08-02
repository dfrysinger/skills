#!/usr/bin/env bash
# curator-state.sh — read/write ~/.copilot/skill-state/curator.json
# Mirrors Hermes Agent's agent/curator.py load_state / save_state / set_paused
# helpers, with atomic write via tempfile + mv.
#
# Subcommands:
#   read                    — print the JSON state (creates default if missing)
#   set <key> <value>       — set a top-level key; value parsed as JSON if it
#                             looks like JSON (numbers, true/false, null, objects).
#   note <last_run_summary> — convenience: stamps last_run_at + bumps run_count.
#
# Defaults match Hermes constants from agent/curator.py.

set -euo pipefail

STATE_DIR="$HOME/.copilot/skill-state"
STATE_FILE="$STATE_DIR/curator.json"
mkdir -p "$STATE_DIR" "$STATE_DIR/reports"

DEFAULT_JSON='{
  "last_run_at": null,
  "last_run_duration_seconds": null,
  "last_run_summary": null,
  "last_run_summary_shown_at": null,
  "last_report_path": null,
  "paused": false,
  "run_count": 0,
  "config_overrides": {
    "interval_hours": 168,
    "stale_after_days": 30,
    "archive_after_days": 90
  }
}'

ensure_state() {
  if [[ ! -f "$STATE_FILE" ]]; then
    printf '%s\n' "$DEFAULT_JSON" > "$STATE_FILE"
  fi
}

atomic_write() {
  local content="$1"
  local tmp
  tmp=$(mktemp "${STATE_FILE}.XXXXXX")
  printf '%s\n' "$content" > "$tmp"
  mv "$tmp" "$STATE_FILE"
}

cmd="${1:-read}"
shift || true

case "$cmd" in
  read)
    ensure_state
    cat "$STATE_FILE"
    ;;
  set)
    if [[ $# -ne 2 ]]; then
      echo "usage: $(basename "$0") set <key> <value>" >&2
      exit 2
    fi
    ensure_state
    KEY="$1"
    VALUE="$2"
    # Decide if VALUE is JSON-typed or string.
    case "$VALUE" in
      true|false|null) JSON_VAL="$VALUE" ;;
      [0-9]*) JSON_VAL="$VALUE" ;;
      '{'*|'['*|'"'*) JSON_VAL="$VALUE" ;;
      *) JSON_VAL=$(printf '%s' "$VALUE" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))') ;;
    esac
    NEW=$(python3 - "$STATE_FILE" "$KEY" "$JSON_VAL" <<'PY'
import json, sys
path, key, raw = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    state = json.load(f)
try:
    state[key] = json.loads(raw)
except json.JSONDecodeError:
    state[key] = raw
print(json.dumps(state, indent=2, sort_keys=True))
PY
)
    atomic_write "$NEW"
    echo "$NEW"
    ;;
  note)
    if [[ $# -lt 1 ]]; then
      echo "usage: $(basename "$0") note <summary>" >&2
      exit 2
    fi
    ensure_state
    SUMMARY="$*"
    NEW=$(python3 - "$STATE_FILE" "$SUMMARY" <<'PY'
import json, sys
from datetime import datetime, timezone
path, summary = sys.argv[1], sys.argv[2]
with open(path) as f:
    state = json.load(f)
state["last_run_at"] = datetime.now(timezone.utc).isoformat()
state["last_run_summary"] = summary
state["run_count"] = int(state.get("run_count", 0)) + 1
print(json.dumps(state, indent=2, sort_keys=True))
PY
)
    atomic_write "$NEW"
    echo "$NEW"
    ;;
  *)
    echo "unknown subcommand: $cmd (use: read | set <k> <v> | note <summary>)" >&2
    exit 2
    ;;
esac
