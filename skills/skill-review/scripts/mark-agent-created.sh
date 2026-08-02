#!/usr/bin/env bash
# mark-agent-created.sh — stamp provenance on a skill that skill-review created
# autonomously. This is what lets skill-curator manage agent-created skills
# aggressively while leaving hand-made skills alone (Hermes "agent_created"
# marker, ContextVar-based there; a marker file + frontmatter here).
#
# Effects:
#   1. Drops a `.agent-created` marker file in the skill dir.
#   2. Writes `.agent-created.json` metadata (session, mode, prompt version, ts).
#   3. Adds `author: skill-review` to SKILL.md frontmatter if not present.
#
# Usage:
#   mark-agent-created.sh <name> <session_id> <mode> [prompt_version]

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $(basename "$0") <name> <session_id> <mode> [prompt_version]" >&2
  exit 2
fi

NAME="$1"; SID="$2"; MODE="$3"; PV="${4:-skill-review-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIND="$SCRIPT_DIR/../../skill-manage/scripts/find-skill.sh"

DIR="$("$FIND" "$NAME")" || { echo "skill not found: $NAME" >&2; exit 1; }
SKILL_MD="$DIR/SKILL.md"
[[ -f "$SKILL_MD" ]] || { echo "no SKILL.md in $DIR" >&2; exit 1; }

# 1. marker
touch "$DIR/.agent-created"

# 2. metadata
python3 - "$DIR/.agent-created.json" "$NAME" "$SID" "$MODE" "$PV" <<'PY'
import json, sys
from datetime import datetime, timezone
out, name, sid, mode, pv = sys.argv[1:6]
json.dump({
    "skill": name,
    "created_by": "skill-review",
    "source_session_id": sid,
    "source_mode": mode,
    "review_prompt_version": pv,
    "created_at": datetime.now(timezone.utc).isoformat(),
}, open(out, "w"), indent=2)
open(out, "a").write("\n")
PY

# 3. frontmatter author (only if absent)
python3 - "$SKILL_MD" <<'PY'
import sys, re
p = sys.argv[1]
src = open(p).read()
m = re.match(r'^---\n(.*?\n)---\n', src, re.S)
if not m:
    sys.exit(0)  # malformed frontmatter; validator will catch it
fm = m.group(1)
if re.search(r'(?m)^author:', fm):
    sys.exit(0)
new_fm = fm + "author: skill-review\n"
open(p, "w").write(src[:m.start(1)] + new_fm + src[m.end(1):])
PY

echo "marked agent-created: $NAME (session=$SID mode=$MODE)"
