#!/usr/bin/env bash
# mailbox-ack.sh <id>
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/_common.sh"

[[ $# -ne 1 ]] && { echo "usage: mailbox-ack.sh <id>" >&2; exit 2; }
ID="$1"
NAME="$(own_name)"
P="$MAILBOX_ROOT/$NAME/pending"
D="$MAILBOX_ROOT/$NAME/delivered"
mkdir -p "$D"
ENV="$P/${ID}.json"
ATT="$P/${ID}"
[[ -f "$ENV" ]] || { echo "no envelope: $ID" >&2; exit 3; }
mv "$ENV" "$D/"
[[ -d "$ATT" ]] && mv "$ATT" "$D/"
echo "acked: $ID -> delivered/"
