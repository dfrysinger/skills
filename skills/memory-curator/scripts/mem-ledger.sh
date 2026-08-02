#!/usr/bin/env bash
# mem-ledger.sh — record which memories have been processed, keyed by a stable
# content-hash, so weekly runs don't re-audit the same memory forever.
#
# Ledger: ~/.copilot/skill-state/memory-curator/ledger.jsonl
# One JSON object per line: {hash, action, subject, ts, body_preview}
#   action ∈ rolled | dup | obsolete | keep | deleted
#
# Subcommands:
#   hash "<body>"                      -> print content-hash
#   seen "<body>"                      -> exit 0 if already in ledger, 1 if not
#   add <action> "<subject>" "<body>"  -> append a ledger entry (idempotent)
#   filter-new                          -> stdin JSON array of {body,subject};
#                                          stdout the subset NOT yet in ledger
#   stats                               -> counts by action

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/mem-lib.sh"
mkdir -p "$MEM_STATE_DIR"
touch "$MEM_LEDGER"

mem_hash() { # normalize then sha1 first 200 chars — resilient to whitespace churn
  /usr/bin/python3 -c '
import sys,re,hashlib
b=sys.argv[1]
n=re.sub(r"\s+"," ",b).strip().lower()[:200]
print(hashlib.sha1(n.encode()).hexdigest()[:16])
' "$1"
}

case "${1:-}" in
  hash) mem_hash "${2:-}" ;;

  seen)
    h="$(mem_hash "${2:-}")"
    grep -q "\"hash\": *\"$h\"" "$MEM_LEDGER" && exit 0 || exit 1 ;;

  add)
    action="${2:-}"; subject="${3:-}"; body="${4:-}"
    h="$(mem_hash "$body")"
    if grep -q "\"hash\": *\"$h\"" "$MEM_LEDGER"; then exit 0; fi
    /usr/bin/python3 -c '
import sys,json,time
print(json.dumps({
  "hash": sys.argv[1], "action": sys.argv[2], "subject": sys.argv[3],
  "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
  "body_preview": sys.argv[4][:80]
}))
' "$h" "$action" "$subject" "$body" >> "$MEM_LEDGER" ;;

  filter-new)
    MEM_LEDGER="$MEM_LEDGER" /usr/bin/python3 -c '
import sys,os,json,re,hashlib
ledger=os.environ["MEM_LEDGER"]
seen=set()
try:
    for line in open(ledger):
        line=line.strip()
        if line: seen.add(json.loads(line).get("hash"))
except FileNotFoundError:
    pass
def h(b):
    n=re.sub(r"\s+"," ",b).strip().lower()[:200]
    return hashlib.sha1(n.encode()).hexdigest()[:16]
arr=json.loads(sys.stdin.read())
out=[m for m in arr if h(m.get("body","")) not in seen]
print(json.dumps(out))
' ;;

  stats)
    /usr/bin/python3 -c '
import sys,json,collections
c=collections.Counter()
try:
    for line in open(sys.argv[1]):
        line=line.strip()
        if line: c[json.loads(line).get("action","?")]+=1
except FileNotFoundError: pass
print("ledger:", dict(c), "total:", sum(c.values()))
' "$MEM_LEDGER" ;;

  *) echo "usage: mem-ledger.sh {hash|seen|add|filter-new|stats} ..." >&2; exit 2 ;;
esac
