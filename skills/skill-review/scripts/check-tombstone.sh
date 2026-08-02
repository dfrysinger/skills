#!/usr/bin/env bash
# check-tombstone.sh — before skill-review CREATES a skill, check whether a
# same-or-similar skill was previously archived/consolidated by the curator.
# Recreating it would cause the create→archive→recreate thrash the rubber-duck
# flagged. Tombstones are written by skill-curator's archive step (for
# agent-created skills) at
# ~/.copilot/skill-state/skill-review/tombstones/<name>.json (daemon state,
# outside the public repo). Override with SKILLS_STATE_DIR.
#
# Exit codes:
#   0  a tombstone matched — caller MUST NOT create; patch `replacement` or skip
#   1  no tombstone matched — safe to proceed
#
# On match (exit 0) prints the tombstone JSON so the caller can read
# `replacement` (the umbrella the content went into) and `reason`.
#
# Usage:
#   check-tombstone.sh <candidate-name>

set -euo pipefail

[[ $# -eq 1 ]] || { echo "usage: $(basename "$0") <candidate-name>" >&2; exit 2; }
NAME="$1"
TOMB_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state/skill-review}/tombstones"
[[ -d "$TOMB_DIR" ]] || exit 1

# Exact match first.
if [[ -f "$TOMB_DIR/$NAME.json" ]]; then
  cat "$TOMB_DIR/$NAME.json"
  exit 0
fi

# Fuzzy: candidate shares the leading token with a tombstoned name, or vice
# versa (e.g. 'gh-token-load' vs a tombstoned 'gh-auth-fix', both 'gh-*').
python3 - "$TOMB_DIR" "$NAME" <<'PY'
import json, os, sys
tdir, name = sys.argv[1], sys.argv[2]
def toks(s): return set(s.lower().replace('_', '-').split('-'))
cand = toks(name)
for fn in os.listdir(tdir):
    if not fn.endswith('.json'):
        continue
    base = fn[:-5]
    shared = cand & toks(base)
    # match if they share the first token AND at least one more, OR names equal
    if base == name or (shared and next(iter(sorted(cand)), '') in toks(base) and len(shared) >= 2):
        print(open(os.path.join(tdir, fn)).read())
        sys.exit(0)
sys.exit(1)
PY
