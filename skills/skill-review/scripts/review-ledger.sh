#!/usr/bin/env bash
# review-ledger.sh — durable record of which sessions skill-review has already
# processed. This is the idempotency boundary that prevents the sweep
# (scheduled) and dispatch (end-of-task) paths from double-creating skills for
# the same session.
#
# Ledger lives OUTSIDE the public repo at
# ~/.copilot/skill-state/skill-review/ledger.jsonl (one JSON object per line) —
# it is daemon state, not shareable content. Single-machine local-only (no
# cross-machine sync; that is an accepted tradeoff of the local-only model).
# Override with SKILLS_STATE_DIR.
#
# Subcommands:
#   has <session_id>                  exit 0 if a completed entry exists, else 1
#   watermark                         print max reviewed event-timestamp (ISO) or
#                                     empty if ledger is empty — sweep starts here
#   append <json>                     append one JSON object (validated) as a line
#   list [N]                          print last N entries (default 20)
#
# Append payload shape (caller builds it):
#   {"session_id","reviewed_at","mode","prompt_version",
#    "created":[...],"patched":[...],"skipped":[...],
#    "candidate_hashes":[...],"watermark_ts":"<max event ts in window>"}

set -euo pipefail

REPO="$HOME/code/skills"
LEDGER_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state/skill-review}"
LEDGER="$LEDGER_DIR/ledger.jsonl"
mkdir -p "$LEDGER_DIR"
[[ -f "$LEDGER" ]] || : > "$LEDGER"

cmd="${1:-list}"
shift || true

case "$cmd" in
  has)
    [[ $# -eq 1 ]] || { echo "usage: $(basename "$0") has <session_id>" >&2; exit 2; }
    SID="$1"
    python3 - "$LEDGER" "$SID" <<'PY'
import json, sys
ledger, sid = sys.argv[1], sys.argv[2]
found = False
with open(ledger) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("session_id") == sid:
            found = True
            break
sys.exit(0 if found else 1)
PY
    ;;
  watermark)
    python3 - "$LEDGER" <<'PY'
import json, sys
ledger = sys.argv[1]
best = ""
with open(ledger) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = obj.get("watermark_ts") or obj.get("reviewed_at") or ""
        if ts > best:
            best = ts
print(best)
PY
    ;;
  append)
    [[ $# -eq 1 ]] || { echo "usage: $(basename "$0") append '<json>'" >&2; exit 2; }
    PAYLOAD="$1"
    # Append under an exclusive lock, re-checking for an existing entry while the
    # lock is held. The in-session dispatch and scheduled sweep can run at the
    # same time: without the lock, both pass `has` and both append, and the old
    # two-step write (record, then newline) could interleave into a corrupt line.
    python3 - "$LEDGER" "$PAYLOAD" <<'PY'
import fcntl, json, sys, os
from datetime import datetime, timezone

ledger = sys.argv[1]
obj = json.loads(sys.argv[2])
assert obj.get("session_id"), "session_id required"
obj.setdefault("reviewed_at", datetime.now(timezone.utc).isoformat())
sid, mode = obj["session_id"], obj.get("mode")

fd = os.open(ledger, os.O_RDWR | os.O_CREAT, 0o600)
with os.fdopen(fd, "r+") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            prev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if prev.get("session_id") == sid and prev.get("mode") == mode:
            print("ledger entry already present for session %s (mode=%s)" % (sid, mode))
            sys.exit(0)
    f.seek(0, os.SEEK_END)
    f.write(json.dumps(obj) + "\n")
    f.flush()
    os.fsync(f.fileno())
print("appended ledger entry for session %s" % sid)
PY
    ;;
  list)
    N="${1:-20}"
    tail -n "$N" "$LEDGER"
    ;;
  *)
    echo "unknown subcommand: $cmd (use: has | watermark | append | list)" >&2
    exit 2
    ;;
esac
