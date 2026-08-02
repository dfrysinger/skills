#!/usr/bin/env bash
# mailbox-read.sh <id>
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/_common.sh"

[[ $# -ne 1 ]] && { echo "usage: mailbox-read.sh <id>" >&2; exit 2; }
ID="$1"
NAME="$(own_name)"
ENV="$MAILBOX_ROOT/$NAME/pending/${ID}.json"
[[ -f "$ENV" ]] || { echo "no envelope: $ID" >&2; exit 3; }
ATTACH="$MAILBOX_ROOT/$NAME/pending/${ID}"

python3 - "$ENV" "$ATTACH" <<'PY'
import json, sys, os
env, attach = sys.argv[1], sys.argv[2]
d=json.load(open(env))
print(f"FROM: {d['from']['name']}")
print(f"TO:   {d['to']['name']}")
print(f"SENT: {d['sent_at']}")
print(f"ID:   {d['id']}")
print(f"SUMMARY: {d['summary']}")
print()
print(d['message'])
if d.get('attachments'):
    print()
    print("ATTACHMENTS:")
    for a in d['attachments']:
        full = os.path.join(attach, a)
        sz = os.path.getsize(full) if os.path.isfile(full) else "missing"
        print(f"  {full}  ({sz} bytes)")
PY
