#!/usr/bin/env bash
# archive-skill.sh — retire a skill by deleting it in a git commit, and record
# the commit that still holds it so restore-skill.sh can bring it back.
#
# Git history IS the archive. An earlier design moved the skill to
# <root>/.archive/<name>, which published dead skills to everyone installing
# the plugin and forced every other script to remember to filter .archive out
# (a filter that was, at least once, forgotten). Deleting keeps the tree honest
# and loses nothing: the retirement record below names the exact commit to
# restore from.
#
# Root-aware (two-root model):
#   PUBLIC repo  ~/code/skills        -> git commit + plugin.json unregister
#   LOCAL native ~/.copilot/skills    -> git commit (local, no remote), NO registry
#
# Retirement records go to ~/.copilot/skill-state/skill-review/retired/<name>.json.
# Tombstones (for agent-created skills) live beside them in tombstones/ — both
# outside the public repo.
#
# Lifted from Hermes Agent's curator: retiring (recoverably) rather than
# destroying is the maximum destructive action; --absorbed-into records
# consolidation lineage.
#
# Usage:
#   archive-skill.sh <name>                          # prune (no consolidation target)
#   archive-skill.sh <name> --absorbed-into <umbr>   # consolidation (merged into <umbr>)

set -euo pipefail
TRAILER="${SKILLS_COAUTHOR_TRAILER:-Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>}"

if [[ $# -lt 1 ]]; then
  echo "usage: $(basename "$0") <name> [--absorbed-into <umbrella>]" >&2
  exit 2
fi

NAME="$1"
shift
ABSORBED=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --absorbed-into)
      ABSORBED="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC=$("$SCRIPT_DIR/find-skill.sh" "$NAME") || exit 1

# Pinned guard.
if [[ -f "$SRC/.pinned" ]]; then
  echo "REFUSED: '$NAME' is pinned (.pinned file present at $SRC)." >&2
  echo "         Unpin first: pin-skill.sh $NAME --unpin" >&2
  exit 1
fi

REPO_ROOT="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state/skill-review}"

# Determine which root SRC lives in, and set the git root + whether to touch the
# plugin registry.
if [[ "$SRC" == "$REPO_ROOT/skills/"* ]]; then
  GIT_ROOT="$REPO_ROOT"
  USE_REGISTRY=1
elif [[ "$SRC" == "$LOCAL_ROOT/"* ]]; then
  GIT_ROOT="$LOCAL_ROOT"
  USE_REGISTRY=0
else
  echo "REFUSED: '$SRC' is not under a known skills root." >&2
  exit 1
fi

# A retirement is only recoverable if the tree is committed first: the restore
# point is HEAD, and uncommitted edits to this skill would not be in it.
if [[ -n "$(git -C "$GIT_ROOT" status --porcelain -- "${SRC#$GIT_ROOT/}")" ]]; then
  echo "REFUSED: '$NAME' has uncommitted changes; they would not be recoverable." >&2
  echo "         Commit or discard them first." >&2
  exit 1
fi

# The commit that still holds the skill. restore-skill.sh checks the tree out
# of exactly this SHA.
RESTORE_SHA="$(git -C "$GIT_ROOT" rev-parse HEAD)"

# Was this skill agent-created? The marker lives inside the skill, so read it
# before the delete.
AGENT_CREATED=0
[[ -f "$SRC/.agent-created" ]] && AGENT_CREATED=1

cd "$GIT_ROOT"
SRC_REL="${SRC#$GIT_ROOT/}"

# Delete the skill and stage the deletion in one step.
if ! git rm -r -q -- "$SRC_REL"; then
  echo "REFUSED: could not remove $SRC_REL." >&2
  exit 1
fi
REMOVED=1

# De-register from the plugin allowlist (public repo only; native skills need none).
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  "$SCRIPT_DIR/registry.sh" unregister "$NAME" || true
fi

# Roll the working tree back to its pre-retirement state, so a failed commit
# leaves nothing half-done.
rollback() {
  if [[ "${REMOVED:-0}" -eq 1 ]]; then
    git reset -q -- "$SRC_REL" || true
    git checkout -- "$SRC_REL" || true
    echo "rolled back: restored $SRC_REL" >&2
  fi
  if [[ "$USE_REGISTRY" -eq 1 ]]; then
    "$SCRIPT_DIR/registry.sh" register "$NAME" >/dev/null 2>&1 || true
  fi
}

# Stage only this retirement's own paths: a bare `git add -A` sweeps unrelated
# working-tree changes into the commit, and a revert of that commit would then
# take the unrelated work down with it.
STAGE=("$SRC_REL")
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  # Every versioned manifest moves together; staging a subset leaves the repo
  # failing validate-plugin-manifests.mjs.
  while IFS= read -r M; do STAGE+=("$M"); done < <("$SCRIPT_DIR/registry.sh" --manifest-paths)
fi
if ! git add -- "${STAGE[@]}"; then
  rollback
  echo "REFUSED: could not stage retirement paths; working tree restored." >&2
  exit 1
fi
if git diff --cached --quiet; then
  rollback
  echo "REFUSED: retirement produced no staged change; working tree restored." >&2
  exit 1
fi
if [[ -n "$ABSORBED" ]]; then
  SUBJECT="skills/$NAME: retire (consolidated into $ABSORBED)"
  BODY="Content absorbed into umbrella skill: $ABSORBED."
else
  SUBJECT="skills/$NAME: retire (pruned)"
  BODY="Retired as stale/obsolete with no consolidation target."
fi

if ! git commit -m "$SUBJECT

Deleted $SRC_REL by /skill-curator. The content is not lost: it is intact in
commit $RESTORE_SHA, which this commit's parent chain preserves.
$BODY
Restore with: $SCRIPT_DIR/restore-skill.sh $NAME

${TRAILER}"; then
  git reset -q -- "${STAGE[@]}" || true
  rollback
  echo "REFUSED: commit failed; working tree restored." >&2
  exit 1
fi

# Records are written only after the commit lands, so a failed retirement never
# leaves a record pointing at a skill that is still live.
RETIRED_DIR="$STATE_DIR/retired"
mkdir -p "$RETIRED_DIR"
python3 - "$RETIRED_DIR/$NAME.json" "$NAME" "$SRC_REL" "$GIT_ROOT" "$RESTORE_SHA" "$ABSORBED" <<'PY'
import json, sys
from datetime import datetime, timezone
out, name, rel, git_root, sha, absorbed = sys.argv[1:7]
json.dump({
    "skill": name,
    # Where it lived in restore_sha, and where it should land today. These are
    # equal at retirement, but a record migrated from an older layout can point
    # at a path that no longer exists in the live tree.
    "path": rel,
    "dest": rel,
    "git_root": git_root,
    "restore_sha": sha,
    "retired_at": datetime.now(timezone.utc).isoformat(),
    "reason": "consolidated" if absorbed else "pruned",
    "replacement": absorbed or None,
}, open(out, "w"), indent=2)
open(out, "a").write("\n")
PY
echo "retirement record: $RETIRED_DIR/$NAME.json"

# Tombstone: agent-created skills get one so skill-review never recreates them.
# (Hand-made skills get no tombstone — the curator shouldn't be retiring them
# autonomously anyway; see the tiered-authority rule in skill-curator.)
if [[ "$AGENT_CREATED" -eq 1 ]]; then
  TOMB_DIR="$STATE_DIR/tombstones"
  mkdir -p "$TOMB_DIR"
  python3 - "$TOMB_DIR/$NAME.json" "$NAME" "$SRC_REL" "$ABSORBED" <<'PY'
import json, sys
from datetime import datetime, timezone
out, name, rel, absorbed = sys.argv[1:5]
json.dump({
    "skill": name,
    "archived_rel": rel,
    "archived_at": datetime.now(timezone.utc).isoformat(),
    "reason": "consolidated" if absorbed else "pruned",
    "replacement": absorbed or None,
    "tombstoned_by": "skill-curator",
}, open(out, "w"), indent=2)
open(out, "a").write("\n")
PY
  echo "tombstone written: $TOMB_DIR/$NAME.json"
fi

echo "retired: $NAME deleted from $GIT_ROOT (restore from $RESTORE_SHA)"
