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
#   0  clean — public repo matches the captured baseline
#   3  VIOLATION — public repo was modified; caller must
#      run the UNWIND procedure (skill-review/references/review-prompt.md,
#      contract item 9) and abort
#
# Usage:
#   verify-repo-unchanged.sh snapshot
#   verify-repo-unchanged.sh check
#   verify-repo-unchanged.sh pristine

set -euo pipefail

REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state}"
BASELINE="${SKILLS_PUBLIC_BASELINE:-$STATE_DIR/skill-review/public-repo-status.baseline}"
cd "$REPO"

case "${1:-check}" in
  snapshot)
    mkdir -p "$(dirname "$BASELINE")"
    /usr/bin/python3 - "$REPO" "$BASELINE" <<'PY'
import hashlib, json, os, stat, subprocess, sys
from pathlib import Path

repo, output = Path(sys.argv[1]), Path(sys.argv[2])
def git_bytes(*args):
    return subprocess.check_output(["git", "-C", str(repo), *args])

def sha(data):
    return hashlib.sha256(data).hexdigest()

untracked = {}
for raw in git_bytes("ls-files", "-z", "--others", "--exclude-standard").split(b"\0"):
    if not raw:
        continue
    rel = os.fsdecode(raw)
    path = repo / rel
    info = path.lstat()
    digest = hashlib.sha256()
    digest.update(str(stat.S_IMODE(info.st_mode)).encode() + b"\0")
    if path.is_symlink():
        digest.update(b"L\0" + os.fsencode(os.readlink(path)))
    elif path.is_file():
        digest.update(b"F\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    else:
        digest.update(b"D\0")
    untracked[rel] = digest.hexdigest()

head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
value = {
    "head": head,
    "index_diff_sha256": sha(git_bytes("diff", "--cached", "--binary", "--no-ext-diff")),
    "worktree_diff_sha256": sha(git_bytes("diff", "--binary", "--no-ext-diff")),
    "untracked": untracked,
}
tmp = output.with_name(output.name + ".tmp")
tmp.write_text(json.dumps(value, sort_keys=True) + "\n")
os.replace(tmp, output)
PY
    echo "repo baseline captured: $BASELINE"
    ;;
  check)
    [[ -f "$BASELINE" ]] || {
      echo "REPO-UNCHANGED VIOLATION — baseline missing: $BASELINE" >&2
      exit 3
    }
    CURRENT="${BASELINE}.current.$$"
    trap 'rm -f "$CURRENT"' EXIT
    SKILLS_PUBLIC_BASELINE="$CURRENT" "$0" snapshot >/dev/null
    if ! cmp -s "$BASELINE" "$CURRENT"; then
      echo "REPO-UNCHANGED VIOLATION — public repo changed during the run:" >&2
      /usr/bin/python3 - "$BASELINE" "$CURRENT" <<'PY' >&2
import json,sys
before=json.load(open(sys.argv[1])); after=json.load(open(sys.argv[2]))
for key in ("head", "index_diff_sha256", "worktree_diff_sha256"):
    if before.get(key) != after.get(key):
        print(f"  changed: {key}")
b=set((before.get("untracked") or {}).items())
a=set((after.get("untracked") or {}).items())
for path, _ in sorted(b-a):
    print(f"  changed/removed untracked: {path}")
for path, _ in sorted(a-b):
    print(f"  changed/added untracked: {path}")
PY
      git status --short >&2
      echo "Caller must run the UNWIND procedure and discard this run." >&2
      exit 3
    fi
    echo "repo-unchanged OK: public repo matches pre-run baseline"
    ;;
  pristine)
    DIRTY="$(git status --porcelain)"
    [[ -z "$DIRTY" ]] || {
      echo "REPO-UNCHANGED VIOLATION — public repo is not pristine:" >&2
      echo "$DIRTY" >&2
      exit 3
    }
    echo "repo-unchanged OK: public repo working tree is pristine"
    ;;
  *)
    echo "usage: verify-repo-unchanged.sh {snapshot|check|pristine}" >&2
    exit 2
    ;;
esac
