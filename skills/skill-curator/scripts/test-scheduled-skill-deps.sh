#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCANNER="$SCRIPT_DIR/scheduled-skill-deps.py"
ARCHIVER="$REPO_ROOT/skills/skill-manage/scripts/archive-skill.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PUBLIC="$TMP/public"
LOCAL="$TMP/local"
PLISTS="$TMP/plists"
mkdir -p \
  "$PUBLIC/skills/daemon-skill/scripts" \
  "$PUBLIC/skills/daemon-skill/references" \
  "$PUBLIC/skills/direct-skill/scripts" \
  "$PUBLIC/skills/alias-skill/scripts" \
  "$PUBLIC/skills/target-skill" \
  "$PUBLIC/skills/sibling-skill" \
  "$PUBLIC/skills/replacement-skill" \
  "$LOCAL" "$PLISTS"
PUBLIC="$(cd "$PUBLIC" && pwd -P)"
LOCAL="$(cd "$LOCAL" && pwd -P)"
PLISTS="$(cd "$PLISTS" && pwd -P)"
ALIAS="$TMP/public-alias"
ln -s "$PUBLIC" "$ALIAS"
PLIST_PREFIX="com.fixture.skills"

for skill in daemon-skill direct-skill alias-skill target-skill sibling-skill replacement-skill; do
  printf -- '---\nname: %s\ndescription: fixture\n---\n' "$skill" \
    > "$PUBLIC/skills/$skill/SKILL.md"
done

cat > "$PUBLIC/skills/daemon-skill/scripts/run.sh" <<EOF
#!/usr/bin/env bash
cat "$PUBLIC/skills/daemon-skill/references/prompt.txt"
"$PUBLIC/skills/direct-skill/scripts/do.sh"
"$ALIAS/skills/alias-skill/scripts/do.sh"
printf '%s\n' 'https://example.com/skills/url-skill/scripts/no.sh'
printf '%s\n' '/tmp/skills/temp-skill/scripts/no.sh'
EOF
chmod +x "$PUBLIC/skills/daemon-skill/scripts/run.sh"
printf '#!/usr/bin/env bash\n:\n' > "$PUBLIC/skills/direct-skill/scripts/do.sh"
chmod +x "$PUBLIC/skills/direct-skill/scripts/do.sh"
printf '#!/usr/bin/env bash\n:\n' > "$PUBLIC/skills/alias-skill/scripts/do.sh"
chmod +x "$PUBLIC/skills/alias-skill/scripts/do.sh"

cat > "$PUBLIC/skills/daemon-skill/references/prompt.txt" <<'EOF'
Load /target-skill, then read references/nested.md.
EOF
cat > "$PUBLIC/skills/daemon-skill/references/nested.md" <<'EOF'
Read references/third.md for the final check.
EOF
cat > "$PUBLIC/skills/daemon-skill/references/third.md" <<'EOF'
Use /sibling-skill for the final check.
EOF

PLIST="$PLISTS/$PLIST_PREFIX.fixture.plist"
python3 - "$PLIST" \
  "$PUBLIC/skills/daemon-skill/scripts/run.sh" <<'PY'
import plistlib
import sys

path, program = sys.argv[1:]
with open(path, "wb") as handle:
    plistlib.dump(
        {
            "Label": "com.fixture.skills.fixture",
            "ProgramArguments": [program],
        },
        handle,
    )
PY

run_scanner() {
  SKILLS_REPO_ROOT="$PUBLIC" \
  SKILLS_LOCAL_ROOT="$LOCAL" \
  SKILLS_LAUNCH_AGENTS_DIR="$PLISTS" \
  SKILLS_LAUNCHD_PREFIX="$PLIST_PREFIX" \
    "$SCANNER" "$@"
}

OUTPUT="$TMP/dependencies.json"
run_scanner --inventory > "$OUTPUT"
python3 - "$OUTPUT" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
deps = {row["skill"] for row in payload["dependencies"]}
required = {
    "daemon-skill",
    "direct-skill",
    "alias-skill",
    "target-skill",
    "sibling-skill",
}
missing = required - deps
assert not missing, f"missing dependencies: {sorted(missing)}"
assert "url-skill" not in deps
assert "temp-skill" not in deps
inventory = {row["name"]: row for row in payload["skills"]}
assert inventory["target-skill"]["implicit_pin"] is True
assert inventory["replacement-skill"]["implicit_pin"] is False
assert inventory["target-skill"]["root"] == "public"
PY

if SKILLS_REPO_ROOT="$PUBLIC" \
   SKILLS_LOCAL_ROOT="$LOCAL" \
   SKILLS_LAUNCH_AGENTS_DIR="$PLISTS" \
   SKILLS_LAUNCHD_PREFIX="$PLIST_PREFIX" \
   SKILLS_STATE_DIR="$TMP/state" \
     "$ARCHIVER" target-skill >"$TMP/archive.out" 2>"$TMP/archive.err"; then
  echo "FAIL: archive accepted a scheduled dependency" >&2
  exit 1
fi
grep -q "implicit pin" "$TMP/archive.err"

cp "$PLIST" "$TMP/plist.clean"
python3 - "$PLIST" "$PUBLIC/skills/missing-skill/scripts/run.sh" <<'PY'
import plistlib, sys
path, missing = sys.argv[1:]
data = plistlib.load(open(path, "rb"))
data["ProgramArguments"].append(missing)
plistlib.dump(data, open(path, "wb"))
PY
if run_scanner >"$TMP/direct-missing.out" 2>"$TMP/direct-missing.err"; then
  echo "FAIL: scanner accepted a missing managed LaunchAgent path" >&2
  exit 1
fi
grep -Eq "referenced (path is missing|skill does not exist)" "$TMP/direct-missing.err"
mv "$TMP/plist.clean" "$PLIST"

cp "$PUBLIC/skills/daemon-skill/references/nested.md" "$TMP/nested.clean"
echo "Read references/missing.md." \
  >> "$PUBLIC/skills/daemon-skill/references/nested.md"
if run_scanner >"$TMP/relative-missing.out" 2>"$TMP/relative-missing.err"; then
  echo "FAIL: scanner accepted a missing relative durable reference" >&2
  exit 1
fi
grep -q "relative reference is missing" "$TMP/relative-missing.err"
mv "$TMP/nested.clean" "$PUBLIC/skills/daemon-skill/references/nested.md"

EMPTY="$TMP/empty-plists"
mkdir "$EMPTY"
if SKILLS_REPO_ROOT="$PUBLIC" \
   SKILLS_LOCAL_ROOT="$LOCAL" \
   SKILLS_LAUNCH_AGENTS_DIR="$EMPTY" \
   SKILLS_LAUNCHD_PREFIX="$PLIST_PREFIX" \
     "$SCANNER" >"$TMP/empty.out" 2>"$TMP/empty.err"; then
  echo "FAIL: scanner accepted an empty managed LaunchAgent set" >&2
  exit 1
fi
grep -q "no managed LaunchAgents" "$TMP/empty.err"

cp "$PUBLIC/skills/daemon-skill/scripts/run.sh" "$TMP/run.sh.clean"
printf '\ncat "%s/skills/missing-skill/scripts/no.sh"\n' "$PUBLIC" \
  >> "$PUBLIC/skills/daemon-skill/scripts/run.sh"
if run_scanner >"$TMP/missing.out" 2>"$TMP/missing.err"; then
  echo "FAIL: scanner accepted a missing explicit managed path" >&2
  exit 1
fi
grep -Eq "referenced (path is missing|skill does not exist)" "$TMP/missing.err"
mv "$TMP/run.sh.clean" "$PUBLIC/skills/daemon-skill/scripts/run.sh"
chmod +x "$PUBLIC/skills/daemon-skill/scripts/run.sh"

sed 's#/target-skill#/replacement-skill#' \
  "$PUBLIC/skills/daemon-skill/references/prompt.txt" > "$TMP/prompt.retargeted"
mv "$TMP/prompt.retargeted" "$PUBLIC/skills/daemon-skill/references/prompt.txt"
run_scanner --check target-skill >/dev/null
if run_scanner --check replacement-skill >"$TMP/check.out" 2>"$TMP/check.err"; then
  echo "FAIL: retargeted scheduled dependency was not pinned" >&2
  exit 1
fi
grep -q "implicit pin" "$TMP/check.err"

printf 'not a plist\n' > "$PLISTS/$PLIST_PREFIX.broken.plist"
if run_scanner >"$TMP/plist.out" 2>"$TMP/plist.err"; then
  echo "FAIL: scanner accepted a malformed managed plist" >&2
  exit 1
fi
grep -Eq "cannot parse .*broken\\.plist" "$TMP/plist.err"
rm "$PLISTS/$PLIST_PREFIX.broken.plist"

mkdir -p "$LOCAL/target-skill"
printf -- '---\nname: target-skill\ndescription: duplicate\n---\n' \
  > "$LOCAL/target-skill/SKILL.md"
if run_scanner >"$TMP/duplicate.out" 2>"$TMP/duplicate.err"; then
  echo "FAIL: scanner accepted duplicate live skill names" >&2
  exit 1
fi
grep -q "ambiguous live skill name" "$TMP/duplicate.err"

echo "scheduled dependency tests: PASS"
