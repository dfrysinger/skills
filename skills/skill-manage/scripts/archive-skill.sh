#!/usr/bin/env bash
# archive-skill.sh — move a skill to its root's .archive/<name>/ and commit the
# move with traceability metadata.
#
# Root-aware (two-root model):
#   PUBLIC repo  ~/code/skills        -> git commit + plugin.json unregister
#   LOCAL native ~/.copilot/skills    -> git commit (local, no remote), NO registry
# Flattened layout: skills live at <root>/<name>, archived to <root>/.archive/<name>.
# Tombstones (for agent-created skills) always go to the shared state dir
# ~/.copilot/skill-state/skill-review/tombstones/ — outside the public repo.
#
# Lifted from Hermes Agent's curator: archive (not delete) is the maximum
# destructive action; --absorbed-into records consolidation lineage.
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
# plugin registry. Flattened layout => archive base is <root>/.archive.
if [[ "$SRC" == "$REPO_ROOT/skills/"* ]]; then
  GIT_ROOT="$REPO_ROOT"
  ARCHIVE_BASE="$REPO_ROOT/skills/.archive"
  USE_REGISTRY=1
elif [[ "$SRC" == "$LOCAL_ROOT/"* ]]; then
  GIT_ROOT="$LOCAL_ROOT"
  ARCHIVE_BASE="$LOCAL_ROOT/.archive"
  USE_REGISTRY=0
else
  echo "REFUSED: '$SRC' is not under a known skills root." >&2
  exit 1
fi

DEST="$ARCHIVE_BASE/$NAME"
if [[ -e "$DEST" ]]; then
  echo "REFUSED: archive destination already exists at $DEST" >&2
  echo "         Restore or remove it first." >&2
  exit 1
fi
mkdir -p "$ARCHIVE_BASE"

# Tombstone: if this skill was agent-created (skill-review marker present),
# record a tombstone BEFORE moving it, so skill-review never recreates it.
# (Hand-made skills get no tombstone — the curator shouldn't be archiving them
# autonomously anyway; see the tiered-authority rule in skill-curator.)
if [[ -f "$SRC/.agent-created" ]]; then
  TOMB_DIR="$STATE_DIR/tombstones"
  mkdir -p "$TOMB_DIR"
  python3 - "$TOMB_DIR/$NAME.json" "$NAME" "$NAME" "$ABSORBED" <<'PY'
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
  TOMB_FILE="$TOMB_DIR/$NAME.json"
  echo "tombstone written: $TOMB_FILE"
fi

mv "$SRC" "$DEST"
MOVED=1

# De-register from the plugin allowlist (public repo only; native skills need none).
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  "$SCRIPT_DIR/registry.sh" unregister "$NAME" || true
fi

# Roll the working tree back to its pre-archive state, so a failed commit leaves
# nothing half-done. Archiving is only ever as reversible as this.
rollback() {
  if [[ "${MOVED:-0}" -eq 1 && -d "$DEST" && ! -e "$SRC" ]]; then
    mv "$DEST" "$SRC"
    echo "rolled back: $DEST -> $SRC" >&2
  fi
  if [[ "$USE_REGISTRY" -eq 1 ]]; then
    "$SCRIPT_DIR/registry.sh" register "$NAME" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TOMB_FILE:-}" && -f "$TOMB_FILE" ]]; then
    rm -f "$TOMB_FILE"
    echo "rolled back: removed $TOMB_FILE" >&2
  fi
}

# Commit in the owning git root. Stage only this archive's own paths: a bare
# `git add -A` sweeps unrelated working-tree changes into the commit, and a
# revert of that commit would then take the unrelated work down with it.
cd "$GIT_ROOT"
SRC_REL="${SRC#$GIT_ROOT/}"
DEST_REL="${DEST#$GIT_ROOT/}"
STAGE=("$SRC_REL" "$DEST_REL")
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  STAGE+=(".claude-plugin/plugin.json")
fi
if ! git add -- "${STAGE[@]}"; then
  rollback
  echo "REFUSED: could not stage archive paths; working tree restored." >&2
  exit 1
fi
if git diff --cached --quiet; then
  rollback
  echo "REFUSED: archive produced no staged change; working tree restored." >&2
  exit 1
fi
if [[ -n "$ABSORBED" ]]; then
  SUBJECT="skills/$NAME: archive (consolidated into $ABSORBED)"
  BODY="Content absorbed into umbrella skill: $ABSORBED."
else
  SUBJECT="skills/$NAME: archive (pruned)"
  BODY="Archived as stale/obsolete with no consolidation target."
fi

# The tombstone lives outside git, so reverting this commit alone restores the
# skill while still blocking recreation. restore-skill.sh clears both.
if [[ -n "${TOMB_FILE:-}" ]]; then
  BODY="$BODY
Tombstone (outside git): $TOMB_FILE"
fi

if ! git commit -m "$SUBJECT

Moved $NAME → .archive/$NAME by /skill-curator.
$BODY
Restore with: $SCRIPT_DIR/restore-skill.sh $NAME

${TRAILER}"; then
  git reset -q -- "${STAGE[@]}" || true
  rollback
  echo "REFUSED: commit failed; working tree restored." >&2
  exit 1
fi

echo "archived: $NAME → .archive/$NAME (root: $GIT_ROOT)"
