#!/usr/bin/env bash
# Append evidence to an existing agent-created skill without changing authority.

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $(basename "$0") <name> <session_id> <mode> --task-key <key> --summary <text> --routing-reason <text> [flags]" >&2
  exit 2
fi

NAME="$1"
SID="$2"
MODE="$3"
shift 3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIND="$SCRIPT_DIR/../../skill-manage/scripts/find-skill.sh"
TASK_KEY=""
INDEPENDENCE=""
EVIDENCE_KIND="independent-recurrence"
SUMMARY=""
ROUTING_REASON=""
DESTINATION="skill"
LEASE_TOKEN="${SKILLS_LOCK_TOKEN:-}"
OWN_LEASE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-key) TASK_KEY="$2"; shift 2 ;;
    --independence) INDEPENDENCE="$2"; shift 2 ;;
    --evidence-kind) EVIDENCE_KIND="$2"; shift 2 ;;
    --summary) SUMMARY="$2"; shift 2 ;;
    --destination) DESTINATION="$2"; shift 2 ;;
    --routing-reason) ROUTING_REASON="$2"; shift 2 ;;
    --lease-token) LEASE_TOKEN="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$TASK_KEY" && -n "$SUMMARY" && -n "$ROUTING_REASON" ]] || {
  echo "task key, summary, and routing reason are required" >&2
  exit 2
}
if [[ -z "$INDEPENDENCE" ]]; then
  [[ "$MODE" == "dispatch" ]] && INDEPENDENCE="verified" || INDEPENDENCE="unverified"
fi

DIR="$("$FIND" "$NAME")" || exit 1
[[ -f "$DIR/.agent-created" ]] || {
  echo "REFUSED: '$NAME' is hand-made; patching it must not create agent authority" >&2
  exit 1
}
[[ -f "$DIR/.agent-created.json" ]] || {
  echo "REFUSED: '$NAME' has an authority marker but no evidence envelope" >&2
  exit 1
}

cleanup() {
  if [[ "$OWN_LEASE" == "1" && -n "$LEASE_TOKEN" ]]; then
    "$SCRIPT_DIR/daemon-lock.sh" release "$LEASE_TOKEN" >/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "${SKILLS_LOCK_HELD_BY_PARENT:-0}" != "1" && -z "$LEASE_TOKEN" ]]; then
  LEASE_TOKEN="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner "append-skill-evidence:$SID")"
  OWN_LEASE=1
fi
if [[ "${SKILLS_LOCK_HELD_BY_PARENT:-0}" != "1" ]]; then
  "$SCRIPT_DIR/daemon-lock.sh" renew "$LEASE_TOKEN" >/dev/null
fi

"$SCRIPT_DIR/evidence-envelope.py" upsert "$DIR/.agent-created.json" \
  --skill "$NAME" \
  --session-id "$SID" \
  --source-mode "$MODE" \
  --task-key "$TASK_KEY" \
  --independence "$INDEPENDENCE" \
  --evidence-kind "$EVIDENCE_KIND" \
  --summary "$SUMMARY" \
  --destination "$DESTINATION" \
  --reason "$ROUTING_REASON"
