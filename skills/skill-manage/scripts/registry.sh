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
# Does NOT commit — caller stages and commits plugin.json alongside its own move.
# Prints the new version to stdout. No-op (exit 0) if already in desired state.

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $(basename "$0") {register|unregister} <name>" >&2
  exit 2
fi

ACTION="$1"
REL="$2"
PJ="$HOME/code/skills/.claude-plugin/plugin.json"

if [[ ! -f "$PJ" ]]; then
  echo "plugin.json not found at $PJ" >&2
  exit 1
fi

case "$ACTION" in
  register|unregister) ;;
  *) echo "unknown action: $ACTION (expected register|unregister)" >&2; exit 2 ;;
esac

python3 - "$PJ" "$ACTION" "$REL" <<'PY'
import json, sys
pj, action, rel = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(pj))
skills = d.setdefault("skills", [])
entry = "./skills/" + rel.strip("/")

changed = False
if action == "register":
    if entry not in skills:
        skills.append(entry)
        changed = True
else:  # unregister
    if entry in skills:
        skills.remove(entry)
        changed = True

if changed:
    major, minor, *_ = (d.get("version", "0.0.0").split(".") + ["0", "0"])[:2]
    d["version"] = f"{major}.{int(minor)+1}.0"
    with open(pj, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")
    print(d["version"])
else:
    print(d.get("version", ""), "(no change)")
PY
