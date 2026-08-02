#!/usr/bin/env bash
# restore-skill.sh — bring a retired skill back from git history.
# Inverse of archive-skill.sh.
#
# archive-skill.sh deletes the skill and writes a retirement record naming the
# commit that still holds it. This reads that record and checks the skill's
# tree back out of that commit. When the record is missing (retired before
# records existed, or state dir wiped), it falls back to finding the delete
# commit in the log, so history alone is always enough.
#
# Root-aware: public repo => git + registry; local native => git only.
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
REPO_ROOT="$(cd "$REPO_ROOT" && pwd -P)"
LOCAL_ROOT="$(cd "$LOCAL_ROOT" && pwd -P)"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state/skill-review}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_SCRIPT="$SCRIPT_DIR/../../skill-review/scripts/daemon-lock.sh"
LOCK_TOKEN=""
release_lock() {
  if [[ -n "$LOCK_TOKEN" ]]; then
    "$LOCK_SCRIPT" release "$LOCK_TOKEN" >/dev/null || true
  fi
}
trap release_lock EXIT

GIT_ROOT=""
SRC_REL=""
DEST_REL=""
RESTORE_SHA=""

RECORD="$STATE_DIR/retired/$NAME.json"
if [[ -n "${SKILLS_RESTORE_GIT_ROOT:-}" ||
      -n "${SKILLS_RESTORE_SRC_REL:-}" ||
      -n "${SKILLS_RESTORE_SHA:-}" ]]; then
  [[ -n "${SKILLS_RESTORE_GIT_ROOT:-}" &&
     -n "${SKILLS_RESTORE_SRC_REL:-}" &&
     -n "${SKILLS_RESTORE_SHA:-}" ]] || {
    echo "REFUSED: incomplete transaction restore identity." >&2
    exit 1
  }
  GIT_ROOT="$(cd "$SKILLS_RESTORE_GIT_ROOT" && pwd -P)"
  [[ "$GIT_ROOT" == "$(cd "$REPO_ROOT" && pwd -P)" ||
     "$GIT_ROOT" == "$(cd "$LOCAL_ROOT" && pwd -P)" ]] || {
    echo "REFUSED: transaction restore root is not managed: $GIT_ROOT" >&2
    exit 1
  }
  SRC_REL="$SKILLS_RESTORE_SRC_REL"
  DEST_REL="$SRC_REL"
  RESTORE_SHA="$SKILLS_RESTORE_SHA"
  if [[ "$GIT_ROOT" == "$(cd "$REPO_ROOT" && pwd -P)" ]]; then
    [[ "$SRC_REL" == "skills/$NAME" ]] || {
      echo "REFUSED: public transaction restore path does not match $NAME." >&2
      exit 1
    }
  else
    [[ "$SRC_REL" == "$NAME" ]] || {
      echo "REFUSED: local transaction restore path does not match $NAME." >&2
      exit 1
    }
  fi
elif [[ -f "$RECORD" ]]; then
  GIT_ROOT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["git_root"])' "$RECORD")
  SRC_REL=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["path"])' "$RECORD")
  DEST_REL=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("dest") or d["path"])' "$RECORD")
  RESTORE_SHA=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["restore_sha"])' "$RECORD")
else
  # No record: search each root's history for the commit that deleted the skill.
  # The restore point is that commit's parent.
  for ROOT in "$REPO_ROOT" "$LOCAL_ROOT"; do
    [[ -d "$ROOT/.git" ]] || continue
    for CANDIDATE in "skills/$NAME" "$NAME"; do
      # --no-renames is required: git's default rename detection reports a
      # move as R, not D, so the delete commit would never be found.
      SHA=$(git -C "$ROOT" log -1 --no-renames --format=%H --diff-filter=D \
        -- "$CANDIDATE/SKILL.md" 2>/dev/null || true)
      [[ -n "$SHA" ]] || continue
      if [[ -n "$GIT_ROOT" ]]; then
        echo "ambiguous: '$NAME' was deleted in more than one root; restore by hand." >&2
        exit 1
      fi
      GIT_ROOT="$ROOT"
      SRC_REL="$CANDIDATE"
      RESTORE_SHA="$SHA^"
    done
  done
fi

if [[ -z "$GIT_ROOT" ]]; then
  echo "no retired skill named '$NAME': no record at $RECORD and no delete commit in either root." >&2
  exit 1
fi
GIT_ROOT="$(cd "$GIT_ROOT" && pwd -P)"

# Verify the skill is actually present at the restore point before touching the
# working tree — a wrong SHA should fail here, not half-restore.
if ! git -C "$GIT_ROOT" cat-file -e "$RESTORE_SHA:$SRC_REL/SKILL.md" 2>/dev/null; then
  echo "REFUSED: $SRC_REL/SKILL.md is not present in $RESTORE_SHA." >&2
  exit 1
fi

[[ -n "$DEST_REL" ]] || DEST_REL="$SRC_REL"
DEST="$GIT_ROOT/$DEST_REL"
if [[ -e "$DEST" ]]; then
  echo "REFUSED: a live skill already exists at $DEST. Rename or remove it before restore." >&2
  exit 1
fi

if [[ -z "${SKILLS_CURATOR_ROLLBACK:-}" ]]; then
  LOCK_TOKEN="$("$LOCK_SCRIPT" acquire --mode session --owner "restore-skill:$NAME")"
fi

USE_REGISTRY=0
[[ "$GIT_ROOT" == "$REPO_ROOT" ]] && USE_REGISTRY=1

cd "$GIT_ROOT"
git checkout "$RESTORE_SHA" -- "$SRC_REL"

# The restore point may predate a layout change, so put the skill where it
# belongs today and leave no empty scaffolding behind.
if [[ "$DEST_REL" != "$SRC_REL" ]]; then
  mkdir -p "$(dirname "$DEST_REL")"
  git mv "$SRC_REL" "$DEST_REL"
  PARENT="$(dirname "$SRC_REL")"
  while [[ "$PARENT" != "." && -d "$PARENT" ]] && [[ -z "$(ls -A "$PARENT")" ]]; do
    rmdir "$PARENT"
    PARENT="$(dirname "$PARENT")"
  done
fi

# Clear any curator tombstone — a deliberate restore means the skill is wanted
# again, so skill-review should no longer be blocked from touching it.
TOMB="$STATE_DIR/tombstones/$NAME.json"
if [[ -f "$TOMB" ]]; then
  rm -f "$TOMB"
  echo "tombstone cleared: $TOMB"
fi

# Re-register in the plugin allowlist (public repo only).
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  if [[ -n "${SKILLS_RESTORE_MANIFEST_SNAPSHOT:-}" ]]; then
    SNAPSHOT="$(cd "$SKILLS_RESTORE_MANIFEST_SNAPSHOT" && pwd -P)"
    while IFS= read -r manifest; do
      [[ -f "$SNAPSHOT/$manifest" ]] || {
        echo "REFUSED: transaction manifest snapshot is incomplete: $manifest" >&2
        exit 1
      }
      cp -p "$SNAPSHOT/$manifest" "$REPO_ROOT/$manifest"
    done < <("$SCRIPT_DIR/registry.sh" --manifest-paths)
  else
    "$SCRIPT_DIR/registry.sh" register "$NAME" || true
  fi
fi

# Stage only this restore's own paths: a bare `git add -A` sweeps unrelated
# working-tree changes into the commit.
STAGE=("$SRC_REL" "$DEST_REL")
if [[ "$USE_REGISTRY" -eq 1 ]]; then
  while IFS= read -r M; do STAGE+=("$M"); done < <("$SCRIPT_DIR/registry.sh" --manifest-paths)
fi
git add -- "${STAGE[@]}"
if ! git commit --only -m "skills/$NAME: restore

Checked $SRC_REL back out of $RESTORE_SHA into $DEST_REL.

${TRAILER}" -- "${STAGE[@]}"; then
  git reset -q -- "${STAGE[@]}" || true
  echo "WARNING: restore succeeded on disk but was not committed." >&2
  exit 1
fi

rm -f "$RECORD"
echo "restored: $DEST_REL from $RESTORE_SHA (root: $GIT_ROOT)"
