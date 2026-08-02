#!/usr/bin/env bash
# verify-repo-unchanged.sh — assert the PUBLIC plugin repo (~/code/skills) was
# NOT modified by an autonomous skill-review sweep.
#
# In the two-root model the daemon writes ONLY to the local native root
# (~/.copilot/skills) and the state dir. The public repo is curated/recommend-
# only and must never be mutated by an unattended run. This guard is the
# enforcement: if the public repo working tree is dirty after a sweep, the run
# is untrusted and the caller must discard it (and investigate).
#
# Exit codes:
#   0  clean — public repo working tree is pristine (porcelain empty)
#   3  VIOLATION — public repo was modified; caller must
#      run the UNWIND procedure (skill-review/references/review-prompt.md,
#      contract item 9) and abort
#
# Usage: verify-repo-unchanged.sh

set -euo pipefail

REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
cd "$REPO"

DIRTY="$(git status --porcelain)"
if [[ -n "$DIRTY" ]]; then
  echo "REPO-UNCHANGED VIOLATION — the public repo was modified by the sweep:" >&2
  echo "$DIRTY" >&2
  echo "Caller must: run the UNWIND procedure (contract item 9 of" >&2
  echo "  skill-review/references/review-prompt.md) and discard this run." >&2
  exit 3
fi

echo "repo-unchanged OK: public repo working tree is pristine"
