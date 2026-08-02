#!/usr/bin/env bash
# mark-agent-created.sh — stamp provenance on a skill that skill-review created
# autonomously. This is what lets skill-curator manage agent-created skills
# aggressively while leaving hand-made skills alone (Hermes "agent_created"
# marker, ContextVar-based there; a marker file + frontmatter here).
#
# Effects:
#   1. Writes and validates `.agent-created.json` evidence atomically.
#   2. Drops the `.agent-created` authority marker after the envelope is valid.
#   3. Adds `author: skill-review` to SKILL.md frontmatter if not present.
#
# Usage:
#   mark-agent-created.sh <name> <session_id> <mode> [prompt_version] [flags]

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $(basename "$0") <name> <session_id> <mode> [prompt_version] [flags]" >&2
  exit 2
fi

NAME="$1"; SID="$2"; MODE="$3"; PV="skill-review-2"
shift 3
if [[ $# -gt 0 && "$1" != --* ]]; then
  PV="$1"
  shift
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIND="$SCRIPT_DIR/../../skill-manage/scripts/find-skill.sh"
ENVELOPE="$SCRIPT_DIR/evidence-envelope.py"
TASK_KEY=""
INDEPENDENCE=""
EVIDENCE_KIND="successful-procedure"
SUMMARY="Agent-created reusable procedure"
ROUTING_REASON="Reusable procedure justified skill creation"
CREATED_BY="skill-review"
TASK_KEY_EXPLICIT=0
INDEPENDENCE_EXPLICIT=0
EVIDENCE_KIND_EXPLICIT=0
SUMMARY_EXPLICIT=0
ROUTING_REASON_EXPLICIT=0
REPAIR_MARKER_ONLY=0
LEASE_TOKEN="${SKILLS_LOCK_TOKEN:-}"
OWN_LEASE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-key) TASK_KEY="$2"; TASK_KEY_EXPLICIT=1; shift 2 ;;
    --independence) INDEPENDENCE="$2"; INDEPENDENCE_EXPLICIT=1; shift 2 ;;
    --evidence-kind) EVIDENCE_KIND="$2"; EVIDENCE_KIND_EXPLICIT=1; shift 2 ;;
    --summary) SUMMARY="$2"; SUMMARY_EXPLICIT=1; shift 2 ;;
    --routing-reason) ROUTING_REASON="$2"; ROUTING_REASON_EXPLICIT=1; shift 2 ;;
    --created-by) CREATED_BY="$2"; shift 2 ;;
    --lease-token) LEASE_TOKEN="$2"; shift 2 ;;
    --repair-marker-only) REPAIR_MARKER_ONLY=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$TASK_KEY" ]] || TASK_KEY="task:$(python3 -c 'import uuid; print(uuid.uuid4())')"
if [[ -z "$INDEPENDENCE" ]]; then
  if [[ "$TASK_KEY_EXPLICIT" == "1" && "$MODE" == "dispatch" ]]; then
    INDEPENDENCE="verified"
  else
    INDEPENDENCE="unverified"
  fi
fi

DIR="$("$FIND" "$NAME")" || { echo "skill not found: $NAME" >&2; exit 1; }
SKILL_MD="$DIR/SKILL.md"
[[ -f "$SKILL_MD" ]] || { echo "no SKILL.md in $DIR" >&2; exit 1; }

if [[ -f "$DIR/.agent-created" && ! -f "$DIR/.agent-created.json" ]]; then
  if [[ "$REPAIR_MARKER_ONLY" != "1" ]]; then
    echo "REFUSED: '$NAME' has an authority marker but no evidence envelope; use explicit --repair-marker-only inputs" >&2
    exit 1
  fi
  if [[ "$TASK_KEY_EXPLICIT" != "1" || "$INDEPENDENCE_EXPLICIT" != "1" ||
        "$EVIDENCE_KIND_EXPLICIT" != "1" || "$SUMMARY_EXPLICIT" != "1" ||
        "$ROUTING_REASON_EXPLICIT" != "1" ]]; then
    echo "REFUSED: marker-only repair requires explicit task key, independence, evidence kind, summary, and routing reason" >&2
    exit 1
  fi
fi

renew() {
  if [[ "${SKILLS_LOCK_HELD_BY_PARENT:-0}" == "1" ]]; then
    return
  fi
  "$SCRIPT_DIR/daemon-lock.sh" renew "$LEASE_TOKEN" >/dev/null
}

cleanup() {
  if [[ "$OWN_LEASE" == "1" && -n "$LEASE_TOKEN" ]]; then
    "$SCRIPT_DIR/daemon-lock.sh" release "$LEASE_TOKEN" >/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "${SKILLS_LOCK_HELD_BY_PARENT:-0}" != "1" && -z "$LEASE_TOKEN" ]]; then
  LEASE_TOKEN="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner "mark-agent-created:$SID")"
  OWN_LEASE=1
fi

# 1. metadata
renew
"$ENVELOPE" upsert "$DIR/.agent-created.json" \
  --skill "$NAME" \
  --created-by "$CREATED_BY" \
  --session-id "$SID" \
  --source-mode "$MODE" \
  --prompt-version "$PV" \
  --task-key "$TASK_KEY" \
  --independence "$INDEPENDENCE" \
  --evidence-kind "$EVIDENCE_KIND" \
  --summary "$SUMMARY" \
  --destination skill \
  --reason "$ROUTING_REASON" >/dev/null

# 2. marker
renew
touch "$DIR/.agent-created"

# 3. frontmatter author (only if absent)
renew
python3 - "$SKILL_MD" "$CREATED_BY" <<'PY'
import sys, re
p, author = sys.argv[1:3]
src = open(p).read()
m = re.match(r'^---\n(.*?\n)---\n', src, re.S)
if not m:
    sys.exit(0)  # malformed frontmatter; validator will catch it
fm = m.group(1)
if re.search(r'(?m)^author:', fm):
    sys.exit(0)
new_fm = fm + f"author: {author}\n"
open(p, "w").write(src[:m.start(1)] + new_fm + src[m.end(1):])
PY

echo "marked agent-created: $NAME (creator=$CREATED_BY session=$SID mode=$MODE task=$TASK_KEY independence=$INDEPENDENCE)"
