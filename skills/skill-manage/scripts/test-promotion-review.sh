#!/usr/bin/env bash
# Deterministic checks for the promotion public-safety inventory.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/promotion-review-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
passes=0

pass() { echo "PASS  $*"; passes=$((passes + 1)); }
fail() { echo "FAIL  $*" >&2; exit 1; }

FAKE_COPILOT="$TMP/copilot"
cat > "$FAKE_COPILOT" <<'SH'
#!/usr/bin/env bash
[[ "${1:-}" == "--version" ]] && { echo "copilot fixture 1.0"; exit 0; }
exit 1
SH
chmod +x "$FAKE_COPILOT"
export COPILOT_BIN="$FAKE_COPILOT"

make_skill() {
  local root="$1" name="$2"
  mkdir -p "$root/$name/references"
  cat > "$root/$name/SKILL.md" <<EOF
---
name: $name
description: Promotion fixture. Use when testing reviewed inventories.
---

# $name

Safe procedure.
EOF
  echo "Safe reference." > "$root/$name/references/example.md"
  touch "$root/$name/.agent-created"
  cat > "$root/$name/.agent-created.json" <<EOF
{
  "schema_version": 2,
  "skill": "$name",
  "created_by": "skill-review",
  "source_session_id": "fixture-session",
  "source_mode": "dispatch",
  "review_prompt_version": "skill-review-2",
  "created_at": "2026-01-01T00:00:00+00:00",
  "evidence": [{
    "task_key": "task:11111111-1111-1111-1111-111111111111",
    "session_id": "fixture-session",
    "observed_at": "2026-01-01T00:00:00+00:00",
    "independence": "verified",
    "evidence_kind": "successful-procedure",
    "summary": "Promotion fixture"
  }],
  "routing": {"destination": "skill", "reason": "Promotion fixture"},
  "claims": [],
  "evaluation": {
    "status": "not_evaluated",
    "evaluated_at": null,
    "candidate_id": null,
    "model": null,
    "source_case": null,
    "sibling_case": null,
    "waiver_class": null,
    "waiver_reason": null
  }
}
EOF
  cat > "$root/$name/.skill-evaluation-cases.json" <<'JSON'
{
  "schema_version": 1,
  "source": {
    "task_id": "source:promotion-0001",
    "prompt": "Produce the source result.",
    "required_regex": [{"id": "right", "pattern": "\\bRIGHT\\b"}],
    "forbidden_regex": [],
    "friction_regex": []
  },
  "sibling": {
    "task_id": "sibling:promotion-0002",
    "prompt": "Produce the sibling result.",
    "required_regex": [{"id": "safe", "pattern": "\\bSAFE\\b"}],
    "forbidden_regex": [],
    "friction_regex": []
  }
}
JSON
}

approve_evaluation() {
  local skill="$1"
  local run="$TMP/eval-$(basename "$skill")"
  local plugin="$TMP/eval-plugin-$(basename "$skill")"
  rm -rf "$run"
  mkdir -p "$run"
  SKILLS_STATE_DIR="$TMP/state" \
    "$SCRIPT_DIR/../../skill-review/scripts/skill-evaluation.py" prepare "$skill" \
      --model gpt-5.4 --run-dir "$run" --plugin-dir "$plugin" >/dev/null
  python3 - "$run" "$(basename "$skill")" <<'PY'
import json, pathlib, sys
run, skill = pathlib.Path(sys.argv[1]), sys.argv[2]
def write(name, answer, load=False):
    events = []
    if load:
        events.append({"type": "tool.execution_start", "data": {"toolName": "skill", "arguments": {"skill": skill}}})
    events += [
        {"type": "assistant.message", "data": {"content": answer, "model": "gpt-5.4"}},
        {"type": "result", "exitCode": 0},
    ]
    (run / name).write_text("".join(json.dumps(e) + "\n" for e in events))
write("source-baseline.jsonl", "not yet")
write("source-candidate.jsonl", "RIGHT", True)
write("sibling-baseline.jsonl", "SAFE")
write("sibling-candidate.jsonl", "SAFE", True)
PY
  SKILLS_STATE_DIR="$TMP/state" \
    "$SCRIPT_DIR/../../skill-review/scripts/skill-evaluation.py" finalize \
      --run-dir "$run" >/dev/null
}

LOCAL="$TMP/local"
PUBLIC="$TMP/public"
mkdir -p "$LOCAL" "$PUBLIC/skills" "$PUBLIC/.claude-plugin" "$PUBLIC/.codex-plugin"
git -C "$LOCAL" init -q
git -C "$PUBLIC" init -q
for root in "$LOCAL" "$PUBLIC"; do
  git -C "$root" config user.email test@example.com
  git -C "$root" config user.name Test
done
echo '{"name":"fixture","version":"0.1.0","skills":[]}' > "$PUBLIC/.claude-plugin/plugin.json"
echo '{"name":"fixture","metadata":{"version":"0.1.0"},"plugins":[{"name":"fixture","version":"0.1.0"}]}' \
  > "$PUBLIC/.claude-plugin/marketplace.json"
echo '{"name":"fixture","version":"0.1.0"}' > "$PUBLIC/.codex-plugin/plugin.json"
git -C "$PUBLIC" add .claude-plugin/plugin.json .claude-plugin/marketplace.json .codex-plugin/plugin.json
git -C "$PUBLIC" commit -qm base

make_skill "$LOCAL" private-skill
echo "PRIVATE_SENTINEL" >> "$LOCAL/private-skill/references/example.md"
if "$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/private-skill" \
  --reviewer claude --reviewer gpt >/dev/null 2>&1; then
  fail "private support-file sentinel was approved"
fi
pass "private support-file sentinel blocks approval"

make_skill "$LOCAL" nested-sidecar
echo "PRIVATE_SENTINEL" > "$LOCAL/nested-sidecar/references/.promotion-reviewed.json"
if "$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/nested-sidecar" \
  --reviewer claude --reviewer gpt >/dev/null 2>&1; then
  fail "nested reserved promotion sidecar was approved"
fi
pass "nested reserved sidecars fail closed"

make_skill "$LOCAL" safe-skill
if "$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/safe-skill" \
  --reviewer same --reviewer same >/dev/null 2>&1; then
  fail "single reviewer identity was approved"
fi
"$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/safe-skill" \
  --reviewer claude --reviewer gpt >/dev/null
"$SCRIPT_DIR/promotion-review.py" verify "$LOCAL/safe-skill" >/dev/null
echo "changed after review" >> "$LOCAL/safe-skill/references/example.md"
if "$SCRIPT_DIR/promotion-review.py" verify "$LOCAL/safe-skill" >/dev/null 2>&1; then
  fail "stale inventory passed"
fi
pass "promotion inventory requires two reviewers and exact hashes"

git -C "$LOCAL" add safe-skill
git -C "$LOCAL" commit -qm "add safe skill"
"$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/safe-skill" \
  --reviewer claude --reviewer gpt >/dev/null
approve_evaluation "$LOCAL/safe-skill"
git -C "$LOCAL" add safe-skill/.promotion-reviewed.json
git -C "$LOCAL" commit -qm "approve safe skill"
SKILLS_LOCAL_ROOT="$LOCAL" SKILLS_REPO_ROOT="$PUBLIC" SKILLS_STATE_DIR="$TMP/state" \
  SKILLS_COAUTHOR_TRAILER="Reviewed-by: fixture" \
  "$SCRIPT_DIR/promote-skill.sh" safe-skill >/dev/null
[[ -f "$PUBLIC/skills/safe-skill/SKILL.md" ]] || fail "promoted skill missing"
if find "$PUBLIC/skills/safe-skill" -name '.agent-created*' -print -quit | grep -q .; then
  fail "public skill retained agent provenance"
fi
[[ ! -f "$PUBLIC/skills/safe-skill/.promotion-reviewed.json" ]] ||
  fail "public skill retained private review manifest"
grep -q '"./skills/safe-skill"' "$PUBLIC/.claude-plugin/plugin.json" ||
  fail "promoted skill was not registered"
versions="$(python3 - "$PUBLIC" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
plugin = json.load(open(root / ".claude-plugin/plugin.json"))["version"]
market = json.load(open(root / ".claude-plugin/marketplace.json"))["metadata"]["version"]
codex = json.load(open(root / ".codex-plugin/plugin.json"))["version"]
print(f"{plugin}:{market}:{codex}")
PY
)"
[[ "$versions" == "0.2.0:0.2.0:0.2.0" ]] ||
  fail "promotion did not keep manifest versions aligned: $versions"
pass "promotion strips provenance and the local review manifest"

make_skill "$LOCAL" registry-failure-skill
git -C "$LOCAL" add registry-failure-skill
git -C "$LOCAL" commit -qm "add registry failure skill"
"$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/registry-failure-skill" \
  --reviewer claude --reviewer gpt >/dev/null
approve_evaluation "$LOCAL/registry-failure-skill"
git -C "$LOCAL" add registry-failure-skill/.promotion-reviewed.json
git -C "$LOCAL" commit -qm "approve registry failure skill"
echo 'NOT JSON' > "$PUBLIC/.codex-plugin/plugin.json"
before_manifests="$(shasum -a 256 \
  "$PUBLIC/.claude-plugin/plugin.json" \
  "$PUBLIC/.claude-plugin/marketplace.json" \
  "$PUBLIC/.codex-plugin/plugin.json")"
if SKILLS_LOCAL_ROOT="$LOCAL" SKILLS_REPO_ROOT="$PUBLIC" SKILLS_STATE_DIR="$TMP/state" \
  SKILLS_COAUTHOR_TRAILER="Reviewed-by: fixture" \
  "$SCRIPT_DIR/promote-skill.sh" registry-failure-skill >/dev/null 2>&1; then
  fail "malformed registry manifest returned success"
fi
after_manifests="$(shasum -a 256 \
  "$PUBLIC/.claude-plugin/plugin.json" \
  "$PUBLIC/.claude-plugin/marketplace.json" \
  "$PUBLIC/.codex-plugin/plugin.json")"
[[ "$after_manifests" == "$before_manifests" ]] ||
  fail "registry failure changed public manifests"
[[ -f "$LOCAL/registry-failure-skill/.agent-created.json" ]] ||
  fail "registry failure did not restore local provenance"
[[ ! -e "$PUBLIC/skills/registry-failure-skill" ]] ||
  fail "registry failure left the skill in the public tree"
git -C "$PUBLIC" restore -- .codex-plugin/plugin.json
pass "registry failure restores every public manifest"

make_skill "$LOCAL" rollback-skill
git -C "$LOCAL" add rollback-skill
git -C "$LOCAL" commit -qm "add rollback skill"
"$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/rollback-skill" \
  --reviewer claude --reviewer gpt >/dev/null
approve_evaluation "$LOCAL/rollback-skill"
git -C "$LOCAL" add rollback-skill/.promotion-reviewed.json
git -C "$LOCAL" commit -qm "approve rollback skill"
cat > "$PUBLIC/.git/hooks/pre-commit" <<'SH'
#!/usr/bin/env bash
exit 1
SH
chmod +x "$PUBLIC/.git/hooks/pre-commit"
if SKILLS_LOCAL_ROOT="$LOCAL" SKILLS_REPO_ROOT="$PUBLIC" SKILLS_STATE_DIR="$TMP/state" \
  SKILLS_COAUTHOR_TRAILER="Reviewed-by: fixture" \
  "$SCRIPT_DIR/promote-skill.sh" rollback-skill >/dev/null 2>&1; then
  fail "forced public commit failure returned success"
fi
[[ -f "$LOCAL/rollback-skill/.agent-created" ]] ||
  fail "failed promotion lost authority marker"
[[ -f "$LOCAL/rollback-skill/.agent-created.json" ]] ||
  fail "failed promotion lost evidence envelope"
[[ -f "$LOCAL/rollback-skill/.promotion-reviewed.json" ]] ||
  fail "failed promotion lost review manifest"
[[ -f "$LOCAL/rollback-skill/.skill-evaluation-cases.json" ]] ||
  fail "failed promotion lost evaluation cases"
[[ ! -e "$PUBLIC/skills/rollback-skill" ]] ||
  fail "failed promotion left the skill in the public tree"
pass "failed promotion restores local provenance"

echo "PASS  $passes deterministic promotion checks"
