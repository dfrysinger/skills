#!/usr/bin/env bash
# registry.sh — add/remove a skill path in .claude-plugin/plugin.json `.skills[]`.
#
# Copilot CLI's plugin loader treats `.skills[]` as an explicit allowlist: a
# skill dir that is not listed there is silently ignored and never becomes a
# `/<slug>` command. Every create/archive/restore must keep this list in sync.
#
# Usage:
#   registry.sh register   <name>   # add ./skills/<name>, bump minor version
#   registry.sh unregister <name>   # remove ./skills/<name>, bump minor version
#
# A change bumps the minor version in EVERY versioned manifest at once
# (.claude-plugin/plugin.json, .claude-plugin/marketplace.json, and
# .codex-plugin/plugin.json). validate-plugin-manifests.mjs requires all three
# to agree, so bumping only one leaves the repo failing validation.
#
# Does NOT commit — the caller stages and commits the manifests alongside its
# own move, staging every path this script prints with --manifest-paths.
# Prints the new version to stdout. No-op (exit 0) if already in desired state.

set -euo pipefail

# Every manifest carrying a version, relative to the repo root. Callers stage
# exactly these paths.
MANIFEST_PATHS=(
  ".claude-plugin/plugin.json"
  ".claude-plugin/marketplace.json"
  ".codex-plugin/plugin.json"
)

if [[ "${1:-}" == "--manifest-paths" ]]; then
  printf '%s\n' "${MANIFEST_PATHS[@]}"
  exit 0
fi

if [[ $# -ne 2 ]]; then
  echo "usage: $(basename "$0") {register|unregister} <name>" >&2
  echo "       $(basename "$0") --manifest-paths" >&2
  exit 2
fi

ACTION="$1"
REL="$2"
REPO_ROOT="${SKILLS_REPO_ROOT:-$HOME/code/skills}"

for M in "${MANIFEST_PATHS[@]}"; do
  if [[ ! -f "$REPO_ROOT/$M" ]]; then
    echo "manifest not found at $REPO_ROOT/$M" >&2
    exit 1
  fi
done

case "$ACTION" in
  register|unregister) ;;
  *) echo "unknown action: $ACTION (expected register|unregister)" >&2; exit 2 ;;
esac

python3 - "$REPO_ROOT" "$ACTION" "$REL" <<'PY'
import json, pathlib, sys

repo, action, rel = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
pj_path = repo / ".claude-plugin/plugin.json"
d = json.load(open(pj_path))
skills = d.setdefault("skills", [])
entry = "./skills/" + rel.strip("/")

if action == "register":
    changed = entry not in skills
    if changed:
        skills.append(entry)
else:
    changed = entry in skills
    if changed:
        skills.remove(entry)

if not changed:
    print(d.get("version", ""), "(no change)")
    sys.exit(0)


def write(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


major, minor, *_ = (d.get("version", "0.0.0").split(".") + ["0", "0"])[:2]
new = f"{major}.{int(minor) + 1}.0"
d["version"] = new
write(pj_path, d)

codex_path = repo / ".codex-plugin/plugin.json"
codex = json.load(open(codex_path))
codex["version"] = new
write(codex_path, codex)

mp_path = repo / ".claude-plugin/marketplace.json"
mp = json.load(open(mp_path))
mp.setdefault("metadata", {})["version"] = new
for plugin in mp.get("plugins", []):
    if plugin.get("name") == mp.get("name"):
        plugin["version"] = new
write(mp_path, mp)

print(new)
PY
