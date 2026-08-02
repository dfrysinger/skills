#!/usr/bin/env bash
# promote-skill.sh — promote an agent-created LOCAL skill into the PUBLIC plugin
# repo so it can be shared/versioned. USER-RUN ONLY (never invoked by the
# unattended daemon — promotion to a published, recommend-only root is a
# deliberate human act).
#
# Moves ~/.copilot/skills/<name> -> ~/code/skills/skills/<name>, validates,
# strips the .agent-created provenance (it becomes a curated skill), registers
# it in plugin.json, and commits BOTH repos (local: removal; public: addition).
#
# Usage: promote-skill.sh <name>

set -euo pipefail
TRAILER="${SKILLS_COAUTHOR_TRAILER:-Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>}"

if [[ $# -ne 1 ]]; then
  echo "usage: $(basename "$0") <name>" >&2
  exit 2
fi

NAME="$1"
REPO_ROOT="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SRC="$LOCAL_ROOT/$NAME"
DEST="$REPO_ROOT/skills/$NAME"

[[ -f "$SRC/SKILL.md" ]] || { echo "no local skill '$NAME' at $SRC" >&2; exit 1; }
[[ -e "$DEST" ]] && { echo "REFUSED: '$NAME' already exists in public repo at $DEST" >&2; exit 1; }

# Validate before moving anything.
"$SCRIPT_DIR/validate-skill.sh" "$SRC/SKILL.md"

# Move into the public repo.
mkdir -p "$(dirname "$DEST")"
mv "$SRC" "$DEST"

# Strip agent provenance — promoted skills are curated, not agent-managed.
rm -f "$DEST/.agent-created" "$DEST/.agent-created.json"

# Register in plugin.json (public root only).
"$SCRIPT_DIR/registry.sh" register "$NAME" || true

# Commit the public repo (addition + registration). Stage only this promotion's
# own paths: a bare `git add -A` sweeps unrelated working-tree changes into the
# commit, and a revert of that commit would take the unrelated work with it.
cd "$REPO_ROOT"
git add -- "skills/$NAME" ".claude-plugin/plugin.json"
git commit -m "skills/$NAME: promote from local (agent-created -> curated)

Promoted ~/.copilot/skills/$NAME into the public plugin repo by the user.
Provenance markers stripped; registered in plugin.json.

${TRAILER}"

# Commit the local repo removal. A failure here leaves the skill in BOTH roots,
# so surface it rather than swallowing it.
cd "$LOCAL_ROOT"
git add -- "$NAME"
if ! git commit -m "skills/$NAME: promoted to public repo (removed from local)

${TRAILER}"; then
  echo "WARNING: public promotion committed, but the local removal did not." >&2
  echo "         '$NAME' now exists in BOTH roots. Commit $LOCAL_ROOT by hand." >&2
  exit 1
fi

echo "promoted: $NAME (local -> public). Run 'git -C $REPO_ROOT push' and refresh the plugin to share."
