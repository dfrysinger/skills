#!/usr/bin/env bash
# list-clusters.sh — group dfrysinger/skills by name prefix to surface
# candidate consolidation clusters for the curator.
#
# A "cluster" = ≥2 skills sharing the same first word (split on '-' or '_').
# Output: clusters with ≥2 members, one cluster per block.
#
# Usage: list-clusters.sh [--min-size N]    (default min-size=2)

set -u

MIN_SIZE=2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --min-size) MIN_SIZE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="${SKILLS_REPO_ROOT:-$HOME/code/skills}/skills"
LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"

# Collect every live skill name from BOTH roots.
for ROOT in "$REPO_ROOT" "$LOCAL_ROOT"; do
  [[ -d "$ROOT" ]] || continue
  find "$ROOT" -name SKILL.md -print 2>/dev/null | while read -r f; do
    d="$(dirname "$f")"
    basename "$d"
  done
done | sort -u | awk -v min="$MIN_SIZE" -F'[-_]' '
  { prefix = $1; names[prefix] = (names[prefix] ? names[prefix] "\n  - " : "  - ") $0; count[prefix]++ }
  END {
    n = 0
    for (p in count) if (count[p] >= min) {
      printf "cluster: %s (%d members)\n%s\n\n", p, count[p], names[p]
      n++
    }
    if (n == 0) printf "no clusters with >= %d members\n", min
  }
'
