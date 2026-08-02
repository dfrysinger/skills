#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNNER="$SCRIPT_DIR/curator-run.py"
ARCHIVER="$REPO_ROOT/skills/skill-manage/scripts/archive-skill.sh"
PINNER="$REPO_ROOT/skills/skill-manage/scripts/pin-skill.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

make_skill() {
  local root="$1" name="$2"
  mkdir -p "$root/$name"
  cat > "$root/$name/SKILL.md" <<EOF
---
name: $name
description: Curator transaction fixture.
---

# $name
EOF
  touch "$root/$name/.agent-created"
}

init_fixture() {
  CASE="$1"
  PUBLIC="$CASE/public"
  LOCAL="$CASE/local"
  STATE="$CASE/state"
  PLISTS="$CASE/plists"
  RUNS="$STATE/curator-runs"
  mkdir -p "$PUBLIC/skills" "$PUBLIC/.claude-plugin" \
    "$PUBLIC/.codex-plugin" "$LOCAL" "$STATE" "$PLISTS"
  git -C "$PUBLIC" init -q
  git -C "$LOCAL" init -q
  for root in "$PUBLIC" "$LOCAL"; do
    git -C "$root" config user.email test@example.com
    git -C "$root" config user.name Test
  done
  echo '{"name":"fixture","version":"0.1.0","skills":[]}' \
    > "$PUBLIC/.claude-plugin/plugin.json"
  echo '{"name":"fixture","metadata":{"version":"0.1.0"},"plugins":[{"name":"fixture","version":"0.1.0"}]}' \
    > "$PUBLIC/.claude-plugin/marketplace.json"
  echo '{"name":"fixture","version":"0.1.0"}' \
    > "$PUBLIC/.codex-plugin/plugin.json"
  echo "public base" > "$PUBLIC/README.md"
  echo "local base" > "$LOCAL/README.md"
  make_skill "$PUBLIC/skills" umbrella
  make_skill "$PUBLIC/skills" old-public
  make_skill "$LOCAL" old-local
  git -C "$PUBLIC" add .
  git -C "$PUBLIC" commit -qm base
  git -C "$LOCAL" add .
  git -C "$LOCAL" commit -qm base
}

run_curator() {
  SKILLS_REPO_ROOT="$PUBLIC" \
  SKILLS_LOCAL_ROOT="$LOCAL" \
  SKILLS_STATE_DIR="$STATE" \
  SKILLS_CURATOR_RUNS_DIR="$RUNS" \
  SKILLS_LAUNCH_AGENTS_DIR="$PLISTS" \
  SKILLS_ALLOW_NO_SCHEDULED_JOBS=1 \
  SKILLS_LOCK_DIR="$STATE/writer-lock.sqlite" \
    "$RUNNER" "$@"
}

archive_skill() {
  SKILLS_REPO_ROOT="$PUBLIC" \
  SKILLS_LOCAL_ROOT="$LOCAL" \
  SKILLS_STATE_DIR="$STATE" \
  SKILLS_CURATOR_RUNS_DIR="$RUNS" \
  SKILLS_LAUNCH_AGENTS_DIR="$PLISTS" \
  SKILLS_ALLOW_NO_SCHEDULED_JOBS=1 \
  SKILLS_LOCK_DIR="$STATE/writer-lock.sqlite" \
  SKILLS_CURATOR_RUN_ID="$1" \
    "$ARCHIVER" "$2" >/dev/null
}

CASE="$TMP/two-root"
init_fixture "$CASE"
echo "public unrelated" > "$PUBLIC/notes.txt"
echo "local unrelated" > "$LOCAL/local-notes.txt"
echo "public staged" >> "$PUBLIC/README.md"
echo "local staged" >> "$LOCAL/README.md"
git -C "$PUBLIC" add README.md
git -C "$LOCAL" add README.md
PUBLIC_DIRTY="$(shasum -a 256 "$PUBLIC/notes.txt")"
LOCAL_DIRTY="$(shasum -a 256 "$LOCAL/local-notes.txt")"
PUBLIC_INDEX="$(git -C "$PUBLIC" diff --cached --binary)"
LOCAL_INDEX="$(git -C "$LOCAL" diff --cached --binary)"
MANIFESTS_BEFORE="$(shasum -a 256 \
  "$PUBLIC/.claude-plugin/plugin.json" \
  "$PUBLIC/.claude-plugin/marketplace.json" \
  "$PUBLIC/.codex-plugin/plugin.json")"
cat > "$CASE/plan.json" <<'JSON'
{
  "operations": [
    {
      "kind": "commit",
      "action": "patch",
      "root": "public",
      "skill": "umbrella",
      "paths": ["skills/umbrella/SKILL.md"]
    },
    {"kind": "archive", "skill": "old-public"},
    {
      "kind": "commit",
      "action": "create",
      "root": "local",
      "skill": "new-local",
      "paths": ["new-local/SKILL.md", "new-local/.agent-created"]
    },
    {"kind": "archive", "skill": "old-local"}
  ]
}
JSON
RUN_ID="$(run_curator begin --plan "$CASE/plan.json" --report "$CASE/report.md")"

if archive_skill "$RUN_ID" old-public 2>/dev/null; then
  fail "out-of-order archive was accepted"
fi
[[ -e "$PUBLIC/skills/old-public" ]] ||
  fail "out-of-order refusal mutated the archive target"
if SKILLS_REPO_ROOT="$PUBLIC" \
   SKILLS_LOCAL_ROOT="$LOCAL" \
   SKILLS_STATE_DIR="$STATE" \
   SKILLS_CURATOR_RUNS_DIR="$RUNS" \
   SKILLS_LAUNCH_AGENTS_DIR="$PLISTS" \
   SKILLS_ALLOW_NO_SCHEDULED_JOBS=1 \
   SKILLS_LOCK_DIR="$STATE/writer-lock.sqlite" \
     "$ARCHIVER" old-local >/dev/null 2>&1; then
  fail "standalone archive bypassed the active curator writer lease"
fi
[[ -e "$LOCAL/old-local" ]] || fail "writer-lease refusal mutated the target"
if SKILLS_REPO_ROOT="$PUBLIC" \
   SKILLS_LOCAL_ROOT="$LOCAL" \
   SKILLS_STATE_DIR="$STATE" \
   SKILLS_LOCK_DIR="$STATE/writer-lock.sqlite" \
     "$PINNER" old-local >/dev/null 2>&1; then
  fail "pin mutation bypassed the active curator writer lease"
fi
[[ ! -e "$LOCAL/old-local/.pinned" ]] ||
  fail "writer-lease refusal created a pin"

OP="$(run_curator intent --run "$RUN_ID" --kind commit --root public \
  --action patch --skill umbrella --paths skills/umbrella/SKILL.md)"
echo "transaction patch" >> "$PUBLIC/skills/umbrella/SKILL.md"
printf '{"session_id":"curator-effect","mode":"dispatch"}\n' >> "$STATE/ledger.jsonl"
cat > "$CASE/message-1.txt" <<'EOF'
skill-curator: patch umbrella
EOF
run_curator commit --run "$RUN_ID" --op "$OP" --message-file "$CASE/message-1.txt" \
  >/dev/null

archive_skill "$RUN_ID" old-public

OP="$(run_curator intent --run "$RUN_ID" --kind commit --root local \
  --action create --skill new-local \
  --paths new-local/SKILL.md new-local/.agent-created)"
make_skill "$LOCAL" new-local
cat > "$CASE/message-2.txt" <<'EOF'
skill-curator: create new-local
EOF
run_curator commit --run "$RUN_ID" --op "$OP" --message-file "$CASE/message-2.txt" \
  >/dev/null

archive_skill "$RUN_ID" old-local
run_curator finish --run "$RUN_ID"
[[ ! -e "$PUBLIC/skills/old-public" ]] || fail "public archive did not apply"
[[ ! -e "$LOCAL/old-local" ]] || fail "local archive did not apply"
[[ -e "$LOCAL/new-local" ]] || fail "local create did not apply"
grep -q "transaction patch" "$PUBLIC/skills/umbrella/SKILL.md" ||
  fail "public patch did not apply"

printf '{"session_id":"unrelated-later","mode":"dispatch"}\n' >> "$STATE/ledger.jsonl"
run_curator rollback --run "$RUN_ID"
[[ -e "$PUBLIC/skills/old-public/SKILL.md" ]] ||
  fail "public archive was not restored"
[[ -e "$LOCAL/old-local/SKILL.md" ]] || fail "local archive was not restored"
[[ ! -e "$LOCAL/new-local" ]] || fail "local create was not reverted"
if grep -q "transaction patch" "$PUBLIC/skills/umbrella/SKILL.md"; then
  fail "public patch was not reverted"
fi
[[ "$(shasum -a 256 "$PUBLIC/notes.txt")" == "$PUBLIC_DIRTY" ]] ||
  fail "public unrelated dirty file changed"
[[ "$(shasum -a 256 "$LOCAL/local-notes.txt")" == "$LOCAL_DIRTY" ]] ||
  fail "local unrelated dirty file changed"
[[ "$(git -C "$PUBLIC" diff --cached --binary)" == "$PUBLIC_INDEX" ]] ||
  fail "public unrelated staged state changed"
[[ "$(git -C "$LOCAL" diff --cached --binary)" == "$LOCAL_INDEX" ]] ||
  fail "local unrelated staged state changed"
MANIFESTS_AFTER="$(shasum -a 256 \
  "$PUBLIC/.claude-plugin/plugin.json" \
  "$PUBLIC/.claude-plugin/marketplace.json" \
  "$PUBLIC/.codex-plugin/plugin.json")"
[[ "$MANIFESTS_AFTER" == "$MANIFESTS_BEFORE" ]] ||
  fail "public manifest bytes changed across rollback"
git -C "$PUBLIC" diff --quiet HEAD -- \
  .claude-plugin/plugin.json \
  .claude-plugin/marketplace.json \
  .codex-plugin/plugin.json ||
  fail "restored public manifests were not committed"
grep -q '"session_id":"unrelated-later"' "$STATE/ledger.jsonl" ||
  fail "later unrelated ledger append was removed"
if grep -q '"session_id":"curator-effect"' "$STATE/ledger.jsonl"; then
  fail "recorded curator ledger effect survived rollback"
fi
[[ ! -e "$STATE/retired/old-public.json" ]] ||
  fail "public retirement record survived rollback"
[[ ! -e "$STATE/tombstones/old-public.json" ]] ||
  fail "public tombstone survived rollback"
echo "PASS: two-root rollback preserves unrelated dirty state and ledger appends"

CASE="$TMP/interrupted"
init_fixture "$CASE"
cat > "$CASE/plan.json" <<'JSON'
{"operations":[{"kind":"commit","action":"create","root":"local","skill":"partial","paths":["partial/SKILL.md","partial/.agent-created"]}]}
JSON
RUN_ID="$(run_curator begin --plan "$CASE/plan.json" --report "$CASE/report.md")"
run_curator intent --run "$RUN_ID" --kind commit --root local \
  --action create --skill partial \
  --paths partial/SKILL.md partial/.agent-created >/dev/null
make_skill "$LOCAL" partial
run_curator rollback --run "$RUN_ID"
if [[ -e "$LOCAL/partial" ]]; then
  find "$LOCAL/partial" -maxdepth 2 -print >&2
  fail "interrupted uncommitted create survived rollback"
fi
echo "PASS: interrupted uncommitted operation is removed"

CASE="$TMP/interrupted-existing"
init_fixture "$CASE"
UMBRELLA_BEFORE="$(shasum -a 256 "$PUBLIC/skills/umbrella/SKILL.md")"
cat > "$CASE/plan.json" <<'JSON'
{"operations":[{"kind":"commit","action":"patch","root":"public","skill":"umbrella","paths":["skills/umbrella/SKILL.md","skills/umbrella/references/new.md"]}]}
JSON
RUN_ID="$(run_curator begin --plan "$CASE/plan.json" --report "$CASE/report.md")"
run_curator intent --run "$RUN_ID" --kind commit --root public \
  --action patch --skill umbrella \
  --paths skills/umbrella/SKILL.md skills/umbrella/references/new.md >/dev/null
echo "interrupted edit" >> "$PUBLIC/skills/umbrella/SKILL.md"
mkdir -p "$PUBLIC/skills/umbrella/references"
echo "new residue" > "$PUBLIC/skills/umbrella/references/new.md"
run_curator rollback --run "$RUN_ID"
[[ "$(shasum -a 256 "$PUBLIC/skills/umbrella/SKILL.md")" == "$UMBRELLA_BEFORE" ]] ||
  fail "existing declared tree was not restored"
[[ ! -e "$PUBLIC/skills/umbrella/references/new.md" ]] ||
  fail "untracked residue survived existing-tree rollback"
echo "PASS: interrupted existing-tree operation removes untracked residue"

CASE="$TMP/interrupted-archive"
init_fixture "$CASE"
make_skill "$PUBLIC/skills" old-local
git -C "$PUBLIC" add skills/old-local
git -C "$PUBLIC" commit -qm "historical same-name skill"
git -C "$PUBLIC" rm -rq skills/old-local
git -C "$PUBLIC" commit -qm "historical same-name deletion"
cat > "$CASE/plan.json" <<'JSON'
{"operations":[{"kind":"archive","skill":"old-local"}]}
JSON
RUN_ID="$(run_curator begin --plan "$CASE/plan.json" --report "$CASE/report.md")"
FAKE_RUNNER="$CASE/fail-complete.sh"
cat > "$FAKE_RUNNER" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "complete" ]]; then
  exit 9
fi
exec "$RUNNER" "\$@"
EOF
chmod +x "$FAKE_RUNNER"
if SKILLS_REPO_ROOT="$PUBLIC" \
   SKILLS_LOCAL_ROOT="$LOCAL" \
   SKILLS_STATE_DIR="$STATE" \
   SKILLS_CURATOR_RUNS_DIR="$RUNS" \
   SKILLS_LAUNCH_AGENTS_DIR="$PLISTS" \
   SKILLS_ALLOW_NO_SCHEDULED_JOBS=1 \
   SKILLS_LOCK_DIR="$STATE/writer-lock.sqlite" \
   SKILLS_CURATOR_RUN_ID="$RUN_ID" \
   SKILLS_CURATOR_RUNNER="$FAKE_RUNNER" \
     "$ARCHIVER" old-local >/dev/null 2>&1; then
  fail "archive completed despite injected completion failure"
fi
[[ ! -e "$LOCAL/old-local" ]] || fail "interrupted archive did not commit"
run_curator rollback --run "$RUN_ID"
[[ -e "$LOCAL/old-local/SKILL.md" ]] ||
  fail "interrupted committed archive was not recovered"
echo "PASS: interrupted committed archive is inferred and restored"

CASE="$TMP/rollback-guards"
init_fixture "$CASE"
cat > "$CASE/plan.json" <<'JSON'
{"operations":[{"kind":"commit","action":"create","root":"local","skill":"guarded","paths":["guarded/SKILL.md","guarded/.agent-created"]}]}
JSON
RUN_ID="$(run_curator begin --plan "$CASE/plan.json" --report "$CASE/report.md")"
OP="$(run_curator intent --run "$RUN_ID" --kind commit --root local \
  --action create --skill guarded \
  --paths guarded/SKILL.md guarded/.agent-created)"
make_skill "$LOCAL" guarded
echo "skill-curator: create guarded" > "$CASE/message.txt"
echo "undeclared" > "$LOCAL/during-operation.txt"
echo "undeclared child" > "$LOCAL/guarded/unrelated.md"
if run_curator commit --run "$RUN_ID" --op "$OP" \
  --message-file "$CASE/message.txt" >/dev/null 2>&1; then
  fail "scoped commit accepted undeclared post-begin dirt"
fi
rm "$LOCAL/during-operation.txt"
rm "$LOCAL/guarded/unrelated.md"
run_curator commit --run "$RUN_ID" --op "$OP" --message-file "$CASE/message.txt" \
  >/dev/null
run_curator finish --run "$RUN_ID"
MANIFEST="$RUNS/$RUN_ID.json"
COMMIT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["operations"][0]["commit"])' "$MANIFEST")"
INITIAL="$(git -C "$LOCAL" rev-parse "$COMMIT^")"

echo "unexpected" > "$LOCAL/intruder.txt"
if run_curator rollback --run "$RUN_ID" >/dev/null 2>&1; then
  fail "rollback accepted unexpected dirty state"
fi
rm "$LOCAL/intruder.txt"

python3 - "$MANIFEST" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
data["operations"][0]["commit"] = "0" * 40
json.dump(data, open(path, "w"), indent=2)
open(path, "a").write("\n")
PY
if run_curator rollback --run "$RUN_ID" >/dev/null 2>&1; then
  fail "rollback accepted a missing recorded commit"
fi
python3 - "$MANIFEST" "$COMMIT" <<'PY'
import json, sys
path, commit = sys.argv[1:]
data = json.load(open(path))
data["operations"][0]["commit"] = commit
json.dump(data, open(path, "w"), indent=2)
open(path, "a").write("\n")
PY

git -C "$LOCAL" reset --hard -q "$INITIAL"
if run_curator rollback --run "$RUN_ID" >/dev/null 2>&1; then
  fail "rollback accepted rewritten history"
fi
git -C "$LOCAL" reset --hard -q "$COMMIT"
run_curator rollback --run "$RUN_ID"
[[ ! -e "$LOCAL/guarded" ]] || fail "guarded create survived repaired rollback"
echo "PASS: dirty, missing-commit, and rewritten-history guards fail closed"

CASE="$TMP/state-guard"
init_fixture "$CASE"
cat > "$CASE/plan.json" <<'JSON'
{"operations":[{"kind":"archive","skill":"old-local"}]}
JSON
RUN_ID="$(run_curator begin --plan "$CASE/plan.json" --report "$CASE/report.md")"
archive_skill "$RUN_ID" old-local
run_curator finish --run "$RUN_ID"
echo '{"tampered":true}' > "$STATE/tombstones/old-local.json"
if run_curator rollback --run "$RUN_ID" >/dev/null 2>&1; then
  fail "rollback accepted a changed tombstone effect"
fi
python3 - "$RUNS/$RUN_ID.json" "$STATE/tombstones/old-local.json" <<'PY'
import base64, json, sys
manifest, target = sys.argv[1:]
data = json.load(open(manifest))
encoded = data["operations"][0]["effects_after"]["tombstone"]["bytes_b64"]
open(target, "wb").write(base64.b64decode(encoded))
PY
run_curator rollback --run "$RUN_ID"
[[ -e "$LOCAL/old-local/SKILL.md" ]] ||
  fail "state-guard archive was not restored after repair"
echo "PASS: changed retirement state blocks rollback"

CASE="$TMP/ambiguous"
init_fixture "$CASE"
cat > "$CASE/plan.json" <<'JSON'
{"operations":[{"kind":"archive","skill":"old-local"}]}
JSON
if SKILLS_REPO_ROOT="$PUBLIC" \
   SKILLS_LOCAL_ROOT="$PUBLIC" \
   SKILLS_STATE_DIR="$STATE" \
   SKILLS_CURATOR_RUNS_DIR="$RUNS" \
   SKILLS_LAUNCH_AGENTS_DIR="$PLISTS" \
   SKILLS_ALLOW_NO_SCHEDULED_JOBS=1 \
   SKILLS_LOCK_DIR="$STATE/writer-lock.sqlite" \
     "$RUNNER" begin --plan "$CASE/plan.json" --report "$CASE/report.md" \
       >/dev/null 2>&1; then
  fail "ambiguous root identity was accepted"
fi
echo "PASS: ambiguous root identity fails closed"

echo "curator transaction tests: PASS"
