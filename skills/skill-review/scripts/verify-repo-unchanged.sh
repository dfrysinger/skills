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
# The baseline is the whole guard, so it is write-once: `snapshot` REFUSES to
# overwrite an existing baseline. Re-snapshotting mid-run would silently
# re-baseline away the very damage the guard exists to catch, and `check` would
# then pass on a repo the run had dirtied. Use `reset` to clear a baseline left
# behind by a crashed run.
#
# `check` also asserts the baseline predates this run's own commits in the LOCAL
# root. A baseline captured after the work was committed is out of order and is
# treated as a violation, whatever the file comparison says.
#
# Exit codes:
#   0  clean — public repo matches the captured baseline
#   3  VIOLATION — public repo was modified, or the baseline is unusable;
#      caller must run the UNWIND procedure
#      (skill-review/references/review-prompt.md, contract item 9) and abort
#
# Usage:
#   verify-repo-unchanged.sh snapshot        # write-once; fails if one exists
#   verify-repo-unchanged.sh check
#   verify-repo-unchanged.sh reset           # discard a stale baseline
#   verify-repo-unchanged.sh pristine

set -euo pipefail

REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state}"
BASELINE="${SKILLS_PUBLIC_BASELINE:-$STATE_DIR/skill-review/public-repo-status.baseline}"
cd "$REPO"

case "${1:-check}" in
  snapshot)
    # INTERNAL is set by `check`, which snapshots into a scratch file to compare
    # against the real baseline. Only an external caller is write-once.
    if [[ -f "$BASELINE" && "${SKILLS_BASELINE_INTERNAL:-0}" != "1" ]]; then
      echo "REPO-UNCHANGED VIOLATION — a baseline already exists: $BASELINE" >&2
      echo "  Captured: $(/usr/bin/python3 -c 'import json,sys,datetime; print(datetime.datetime.fromtimestamp(json.load(open(sys.argv[1])).get("captured_at",0)).isoformat())' "$BASELINE" 2>/dev/null || echo unknown)" >&2
      echo "  Overwriting it would re-baseline away any change this run already made." >&2
      echo "  If a previous run crashed and left it behind: verify-repo-unchanged.sh reset" >&2
      exit 3
    fi
    mkdir -p "$(dirname "$BASELINE")"
    /usr/bin/python3 - "$REPO" "$BASELINE" <<'PY'
import hashlib, json, os, stat, subprocess, sys, time
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

# The local root's HEAD at snapshot time marks where this run's own commits
# begin, so `check` can tell whether the baseline predates the work.
local_root = Path(os.environ.get("SKILLS_LOCAL_ROOT", str(Path.home() / ".copilot/skills")))
try:
    local_head = subprocess.check_output(
        ["git", "-C", str(local_root), "rev-parse", "HEAD"], text=True
    ).strip()
except Exception:
    local_head = ""

value = {
    "captured_at": int(time.time()),
    "local_head": local_head,
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
    SKILLS_BASELINE_INTERNAL=1 SKILLS_PUBLIC_BASELINE="$CURRENT" "$0" snapshot >/dev/null
    /usr/bin/python3 - "$BASELINE" "$CURRENT" "$LOCAL_ROOT" <<'PY'
import json, subprocess, sys

before = json.load(open(sys.argv[1]))
after = json.load(open(sys.argv[2]))
local_root = sys.argv[3]

violations = []

# Content comparison. Only the repo-state keys count; captured_at and
# local_head are metadata about the baseline itself and always differ.
for key in ("head", "index_diff_sha256", "worktree_diff_sha256"):
    if before.get(key) != after.get(key):
        violations.append(f"  changed: {key}")
b = set((before.get("untracked") or {}).items())
a = set((after.get("untracked") or {}).items())
for path, _ in sorted(b - a):
    violations.append(f"  changed/removed untracked: {path}")
for path, _ in sorted(a - b):
    violations.append(f"  changed/added untracked: {path}")

# Ordering. Every commit this run made in the local root must be NEWER than the
# baseline. A baseline captured after the work was committed proves it was taken
# too late to witness anything, so it cannot be trusted no matter how it
# compares.
captured_at = before.get("captured_at")
local_head = before.get("local_head")
if captured_at and local_head:
    try:
        run_commits = subprocess.check_output(
            ["git", "-C", local_root, "log", "--format=%ct %h", f"{local_head}..HEAD"],
            text=True,
        ).split("\n")
    except Exception:
        run_commits = []
    for line in run_commits:
        if not line.strip():
            continue
        ts, sha = line.split(None, 1)
        if int(ts) < captured_at:
            violations.append(
                f"  baseline captured AFTER this run's commit {sha} — taken too late to witness changes"
            )

if violations:
    print("REPO-UNCHANGED VIOLATION — this run cannot be trusted:", file=sys.stderr)
    for v in violations:
        print(v, file=sys.stderr)
    sys.exit(3)
PY
    RC=$?
    if [[ "$RC" -ne 0 ]]; then
      git status --short >&2
      echo "Caller must run the UNWIND procedure and discard this run." >&2
      exit 3
    fi
    AGE=$(/usr/bin/python3 -c 'import json,sys,time; print(int(time.time()) - json.load(open(sys.argv[1])).get("captured_at", 0))' "$BASELINE" 2>/dev/null || echo "?")
    echo "repo-unchanged OK: public repo matches pre-run baseline (baseline age: ${AGE}s)"
    ;;
  reset)
    if [[ -f "$BASELINE" ]]; then
      rm -f "$BASELINE"
      echo "baseline discarded: $BASELINE"
    else
      echo "no baseline to discard at $BASELINE"
    fi
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
    echo "usage: verify-repo-unchanged.sh {snapshot|check|reset|pristine}" >&2
    exit 2
    ;;
esac
