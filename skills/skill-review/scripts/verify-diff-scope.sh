#!/usr/bin/env bash
# verify-diff-scope.sh — containment guard for autonomous skill-review runs,
# scoped to the LOCAL native skills repo (~/.copilot/skills).
#
# Copilot CLI cannot code-enforce a tool whitelist on a subagent the way Hermes
# restricts its review fork, so this is the practical substitute: after a sweep,
# assert that the local skills repo changed ONLY allowed paths. If anything else
# moved, the run is untrusted (possible prompt injection from reviewed
# conversation content) and must be reverted by the caller.
#
# Pairs with verify-repo-unchanged.sh, which asserts the PUBLIC repo was not
# touched at all. The daemon writes only to ~/.copilot/skills + the state dir.
#
# Allowed paths (relative to ~/.copilot/skills):
#   <name>/**        any skill directory (content + support files)
#   README.md        local-root readme
#
# Exit codes:
#   0  clean — every change is within the allowlist (or no changes at all)
#   3  VIOLATION — at least one change is out of scope; caller must
#      run the UNWIND procedure (skill-review/references/review-prompt.md,
#      contract item 9) and abort the run
#
# Usage:
#   verify-diff-scope.sh                 # checks working tree + index
#   verify-diff-scope.sh [BASE_REF]      # also checks BASE_REF..HEAD

set -euo pipefail

LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"
cd "$LOCAL_ROOT"

BASE="${1:-}"

{
  git status --porcelain | awk '{print $2}'
  if [[ -n "$BASE" ]]; then
    git diff --name-only "$BASE"..HEAD
  fi
} | sed '/^$/d' | sort -u > "/tmp/.sr-diff-scope.$$" || true

VIOL=0
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    README.md) ;;
    */*) ;;            # any path nested under a skill dir
    *)
      echo "OUT-OF-SCOPE: $path" >&2
      VIOL=1
      ;;
  esac
done < "/tmp/.sr-diff-scope.$$"
rm -f "/tmp/.sr-diff-scope.$$"

if [[ "$VIOL" -ne 0 ]]; then
  echo "DIFF-SCOPE VIOLATION — sweep touched paths outside the local skills allowlist." >&2
  echo "Caller must: run the UNWIND procedure (contract item 9 of" >&2
  echo "  skill-review/references/review-prompt.md) and discard this run." >&2
  exit 3
fi

echo "diff-scope OK: all local changes within <name>/**, README.md"
