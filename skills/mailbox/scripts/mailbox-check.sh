#!/usr/bin/env bash
# mailbox-check.sh
# Lists pending envelopes addressed to the current tmux session.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/_common.sh"

NAME="$(own_name)"
DIR="$MAILBOX_ROOT/$NAME/pending"
[[ -d "$DIR" ]] || { echo "no mailbox yet for $NAME (none pending)"; exit 0; }

shopt -s nullglob
ENVS=("$DIR"/*.json)
if [[ ${#ENVS[@]} -eq 0 ]]; then echo "no pending mail for $NAME"; exit 0; fi

echo "$NAME has ${#ENVS[@]} pending envelope(s):"
for e in "${ENVS[@]}"; do
  python3 - "$e" <<'PY'
import json, sys, os
p=sys.argv[1]
d=json.load(open(p))
attach_dir = p[:-5]  # strip .json
n_att = len(d.get('attachments', []))
print(f"  [{d['id']}]  from={d['from']['name']}  sent={d['sent_at']}")
print(f"     summary: {d['summary']}")
if n_att:
    print(f"     attachments ({n_att}):")
    for a in d['attachments']:
        print(f"       {os.path.join(attach_dir, a)}")
PY
done
echo
echo "Read one with: mailbox-read.sh <id>    Ack with: mailbox-ack.sh <id>"
