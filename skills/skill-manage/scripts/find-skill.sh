#!/usr/bin/env bash
# find-skill.sh — resolve a skill name to its directory path.
#
# Searches BOTH skill roots:
#   1. PUBLIC repo   ~/code/skills/skills/   (curated, plugin, git)
#   2. LOCAL native  ~/.copilot/skills/      (agent-managed, no remote)
# Override roots with SKILLS_REPO_ROOT / SKILLS_LOCAL_ROOT.
#
# Prints the absolute path on stdout, exit 1 if not found, exit 1 (ambiguous)
# if the name matches in more than one place (including across roots).
#
# Usage: find-skill.sh <skill-name>

set -u

if [[ $# -ne 1 ]]; then
  echo "usage: $(basename "$0") <skill-name>" >&2
  exit 2
fi

NAME="$1"
REPO_ROOT="${SKILLS_REPO_ROOT:-$HOME/code/skills}/skills"
LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"

MATCH=""
for ROOT in "$REPO_ROOT" "$LOCAL_ROOT"; do
  [[ -d "$ROOT" ]] || continue
  found=$(find "$ROOT" -name SKILL.md -print 2>/dev/null | while read -r f; do
    d="$(dirname "$f")"
    if [[ "$(basename "$d")" == "$NAME" ]]; then
      printf '%s\n' "$d"
    fi
  done)
  if [[ -n "$found" ]]; then
    if [[ -n "$MATCH" ]]; then MATCH="$MATCH
$found"; else MATCH="$found"; fi
  fi
done

if [[ -z "$MATCH" ]]; then
  echo "skill '$NAME' not found under $REPO_ROOT or $LOCAL_ROOT" >&2
  exit 1
fi

COUNT=$(printf '%s\n' "$MATCH" | grep -c .)
if [[ "$COUNT" -gt 1 ]]; then
  echo "ambiguous: '$NAME' matched $COUNT skills (resolve by removing duplicates):" >&2
  printf '%s\n' "$MATCH" >&2
  exit 1
fi

printf '%s\n' "$MATCH"
