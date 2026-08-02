#!/usr/bin/env bash
# restore-skill.sh — move a previously-archived skill back to its live location.
# Inverse of archive-skill.sh. Root-aware: searches both roots' .archive/ and
# restores within the same root (public repo => git + registry; local native =>
# git only, no registry). Flattened layout: <root>/.archive/<name> -> <root>/<name>.
#
# Usage: restore-skill.sh <name>

set -euo pipefail
TRAILER="${SKILLS_COAUTHOR_TRAILER:-Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>}"

if [[ $# -ne 1 ]]; then
  echo "usage: $(basename "$0") <name>" >&2
  exit 2
fi

NAME="$1"
REPO_ROOT="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state/skill-review}"

# Search both roots' archives. Each candidate carries its root context.
ARCHIVED=""
for BASE in "$REPO_ROOT/skills/.archive" "$LOCAL_ROOT/.archive"; do
  [[ -d "$BASE" ]] || continue
  if [[ -f "$BASE/$NAME/SKILL.md" ]]; then
    if [[ -n "$ARCHIVED" ]]; then ARCHIVED="$ARCHIVED
$BASE/$NAME"; else ARCHIVED="$BASE/$NAME"; fi
  fi
done

if [[ -z "$ARCHIVED" ]]; then
  echo "no archived skill named '$NAME' under either root's .archive/" >&2
  exit 1
fi
COUNT=$(printf '%s\n' "$ARCHIVED" | grep -c .)
if [[ "$COUNT" -gt 1 ]]; then
  echo "ambiguous: '$NAME' matched $COUNT archived skills:" >&2
  printf '%s\n' "$ARCHIVED" >&2
  exit 1
fi

ARCHIVED_DIR="$ARCHIVED"
if [[ "$ARCHIVED_DIR" == "$REPO_ROOT/skills/.archive/"* ]]; then
  GIT_ROOT="$REPO_ROOT"
  DEST="$REPO_ROOT/skills/$NAME"
  USE_REGISTRY=1
else
  GIT_ROOT="$LOCAL_ROOT"
  DEST="$LOCAL_ROOT/$NAME"
  USE_REGISTRY=0
fi

if [[ -e "$DEST" ]]; then
  echo "REFUSED: a live skill already exists at $DEST. Rename or remove it before restore." >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
mv "$ARCHIVED_DIR" "$DEST"

# Clear any curator tombstone — a deliberate restore means the skill is wanted
# again, so skill-review should no longer be blocked from touching it.
TOMB="$STATE_DIR/tombstones/$NAME.json"
if [[ -f "$TOMB" ]]; then
  rm -f "$TOMB"
  echo "tombstone cleared: $TOMB"
fi

# Re-register in the plugin allowlist (public repo only).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  "$SCRIPT_DIR/registry.sh" register "$NAME" || true
fi

# Stage only this restore's own paths: a bare `git add -A` sweeps unrelated
# working-tree changes into the commit.
cd "$GIT_ROOT"
SRC_REL="${ARCHIVED_DIR#$GIT_ROOT/}"
DEST_REL="${DEST#$GIT_ROOT/}"
STAGE=("$SRC_REL" "$DEST_REL")
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  STAGE+=(".claude-plugin/plugin.json")
fi
git add -- "${STAGE[@]}"
if ! git commit -m "skills/$NAME: restore from archive

Moved .archive/$NAME → $NAME.

${TRAILER}"; then
  git reset -q -- "${STAGE[@]}" || true
  echo "WARNING: restore succeeded on disk but was not committed." >&2
  exit 1
fi

echo "restored: .archive/$NAME → $NAME (root: $GIT_ROOT)"
