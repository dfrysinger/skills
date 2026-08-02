#!/usr/bin/env bash
# Deterministic M2 checks for source/sibling evaluation and stale gates.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/skill-evaluation-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
passes=0

pass() { echo "PASS  $*"; passes=$((passes + 1)); }
fail() { echo "FAIL  $*" >&2; exit 1; }

export SKILLS_STATE_DIR="$TMP/state"
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
  mkdir -p "$root/$name"
  cat > "$root/$name/SKILL.md" <<EOF
---
name: $name
description: Use when a fixture asks for the exact source or sibling outcome.
---

# $name

Return RIGHT for the source task. Return SAFE for the sibling task.
EOF
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
    "summary": "Evaluation fixture"
  }],
  "routing": {"destination": "skill", "reason": "Reusable fixture"},
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
    "task_id": "source:fixture-0001",
    "prompt": "Produce the source outcome.",
    "required_regex": [{"id": "right", "pattern": "\\bRIGHT\\b"}],
    "forbidden_regex": [{"id": "harm", "pattern": "\\bHARM\\b"}],
    "friction_regex": [{"id": "redundant", "pattern": "\\bREDUNDANT\\b"}]
  },
  "sibling": {
    "task_id": "sibling:fixture-0002",
    "prompt": "Produce the sibling outcome.",
    "required_regex": [{"id": "safe", "pattern": "\\bSAFE\\b"}],
    "forbidden_regex": [{"id": "bad", "pattern": "\\bBAD\\b"}],
    "friction_regex": []
  }
}
JSON
}

write_log() {
  local path="$1" answer="$2" skill="${3:-}"
  : > "$path"
  if [[ -n "$skill" ]]; then
    printf '{"type":"tool.execution_start","data":{"toolName":"skill","arguments":{"skill":"%s"}}}\n' \
      "$skill" >> "$path"
  fi
  python3 - "$path" "$answer" <<'PY'
import json, sys
path, answer = sys.argv[1:3]
with open(path, "a") as handle:
    handle.write(json.dumps({"type": "assistant.message", "data": {"content": answer, "model": "gpt-5.4"}}) + "\n")
    handle.write(json.dumps({"type": "result", "exitCode": 0}) + "\n")
PY
}

make_run() {
  local skill_dir="$1" sibling_answer="${2:-SAFE}" load_source="${3:-yes}"
  local source_baseline="${4:-REDUNDANT}"
  local run_dir="$TMP/run-$(basename "$skill_dir")-$(date +%s%N)"
  local plugin_dir="$TMP/plugin-$(basename "$skill_dir")-$(date +%s%N)"
  mkdir -p "$run_dir"
  "$SCRIPT_DIR/skill-evaluation.py" prepare "$skill_dir" \
    --model gpt-5.4 --run-dir "$run_dir" --plugin-dir "$plugin_dir" >/dev/null
  write_log "$run_dir/source-baseline.jsonl" "$source_baseline"
  if [[ "$load_source" == "yes" ]]; then
    write_log "$run_dir/source-candidate.jsonl" "RIGHT" "$(basename "$skill_dir")"
  else
    write_log "$run_dir/source-candidate.jsonl" "RIGHT"
  fi
  write_log "$run_dir/sibling-baseline.jsonl" "SAFE"
  write_log "$run_dir/sibling-candidate.jsonl" "$sibling_answer" "$(basename "$skill_dir")"
  "$SCRIPT_DIR/skill-evaluation.py" finalize --run-dir "$run_dir"
}

ROOT="$TMP/skills"
make_skill "$ROOT" helpful-skill
result="$(make_run "$ROOT/helpful-skill")"
[[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$result")" == "pass" ]] ||
  fail "helpful candidate did not pass"
"$SCRIPT_DIR/skill-evaluation.py" gate "$ROOT/helpful-skill" >/dev/null
grep -q '"status": "pass"' "$ROOT/helpful-skill/.agent-created.json" ||
  fail "evidence envelope did not mirror evaluation"
pass "helpful source improvement with preserved sibling passes"

echo "Changed runtime behavior." >> "$ROOT/helpful-skill/SKILL.md"
if "$SCRIPT_DIR/skill-evaluation.py" gate "$ROOT/helpful-skill" >/dev/null 2>&1; then
  fail "stale candidate receipt passed"
fi
pass "candidate edits invalidate the gate"

make_skill "$ROOT" overfit-skill
result="$(make_run "$ROOT/overfit-skill" "BAD")"
[[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$result")" == "regression" ]] ||
  fail "overfitted candidate was not rejected"
if "$SCRIPT_DIR/skill-evaluation.py" gate "$ROOT/overfit-skill" >/dev/null 2>&1; then
  fail "regression receipt passed the gate"
fi
pass "sibling regression rejects an overfitted skill"

make_skill "$ROOT" unloaded-skill
result="$(make_run "$ROOT/unloaded-skill" "SAFE" "no")"
[[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$result")" == "inconclusive" ]] ||
  fail "unloaded candidate did not become inconclusive"
pass "candidate run must actually load the skill"

make_skill "$ROOT" marginal-skill
result="$(make_run "$ROOT/marginal-skill" "SAFE" "yes" "RIGHT REDUNDANT")"
[[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$result")" == "inconclusive" ]] ||
  fail "single-sample friction delta was treated as a pass"
pass "friction-only improvement remains inconclusive"

make_skill "$ROOT" symlink-skill
ln -s /tmp "$ROOT/symlink-skill/references"
if "$SCRIPT_DIR/skill-evaluation.py" prepare "$ROOT/symlink-skill" \
  --model gpt-5.4 --run-dir "$TMP/symlink-run" \
  --plugin-dir "$TMP/symlink-plugin" >/dev/null 2>&1; then
  fail "symlinked runtime input passed"
fi
pass "runtime inventory rejects symlinks"

make_skill "$ROOT" duplicate-case
python3 - "$ROOT/duplicate-case/.skill-evaluation-cases.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["sibling"]["task_id"] = d["source"]["task_id"]
json.dump(d, open(p, "w"))
PY
if "$SCRIPT_DIR/skill-evaluation.py" prepare "$ROOT/duplicate-case" \
  --model gpt-5.4 --run-dir "$TMP/duplicate-run" \
  --plugin-dir "$TMP/duplicate-plugin" >/dev/null 2>&1; then
  fail "duplicate source/sibling identity passed"
fi
pass "source and sibling tasks must be distinct"

make_skill "$ROOT" waiver-skill
mkdir -p "$ROOT/waiver-skill/scripts"
cat > "$ROOT/waiver-skill/scripts/helper.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$ROOT/waiver-skill/scripts/test-helper.sh" <<'SH'
#!/usr/bin/env bash
bash scripts/helper.sh
SH
chmod +x "$ROOT/waiver-skill/scripts/"*.sh
if "$SCRIPT_DIR/skill-evaluation.py" waive "$ROOT/waiver-skill" \
  --base-receipt "$TMP/missing-pass-receipt.json" --waiver-class deterministic-helper \
  --reason "No passing evaluation exists" --test-script scripts/test-helper.sh >/dev/null 2>&1; then
  fail "unevaluated skill received a waiver"
fi
pass "waiver requires an anchored passing evaluation"

git_root="$TMP/helper-root"
make_skill "$git_root" helper-skill
mkdir -p "$git_root/helper-skill/scripts"
cat > "$git_root/helper-skill/scripts/helper.sh" <<'SH'
#!/usr/bin/env bash
exit 1
SH
cat > "$git_root/helper-skill/scripts/test-helper.sh" <<'SH'
#!/usr/bin/env bash
set -e
bash scripts/helper.sh
sha="$(shasum -a 256 scripts/helper.sh | awk '{print $1}')"
printf '{"status":"pass","verified_files":{"scripts/helper.sh":"%s"}}\n' "$sha"
SH
chmod +x "$git_root/helper-skill/scripts/helper.sh" \
  "$git_root/helper-skill/scripts/test-helper.sh"
base_result="$(make_run "$git_root/helper-skill")"
base_receipt="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["receipt"])' <<<"$base_result")"
cat > "$git_root/helper-skill/scripts/helper.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$git_root/helper-skill/scripts/helper.sh"
result="$("$SCRIPT_DIR/skill-evaluation.py" waive "$git_root/helper-skill" \
  --base-receipt "$base_receipt" --waiver-class deterministic-helper \
  --reason "Exact helper behavior is covered by its executable check" \
  --test-script scripts/test-helper.sh)"
[[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$result")" == "waived" ]] ||
  fail "deterministic helper waiver failed"
"$SCRIPT_DIR/skill-evaluation.py" gate "$git_root/helper-skill" >/dev/null
pass "narrow tested helper change may be waived"

make_skill "$ROOT" skill-md-waiver
mkdir -p "$ROOT/skill-md-waiver/scripts"
cat > "$ROOT/skill-md-waiver/scripts/test-helper.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$ROOT/skill-md-waiver/scripts/test-helper.sh"
base_result="$(make_run "$ROOT/skill-md-waiver")"
base_receipt="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["receipt"])' <<<"$base_result")"
echo "Behavior rewrite." >> "$ROOT/skill-md-waiver/SKILL.md"
if "$SCRIPT_DIR/skill-evaluation.py" waive "$ROOT/skill-md-waiver" \
  --base-receipt "$base_receipt" --waiver-class deterministic-helper \
  --reason "Not actually a helper" --test-script scripts/test-helper.sh >/dev/null 2>&1; then
  fail "SKILL.md rewrite received a waiver"
fi
pass "SKILL.md behavior changes cannot be waived"

ARCHIVE_ROOT="$TMP/archive-root"
mkdir -p "$ARCHIVE_ROOT"
git -C "$ARCHIVE_ROOT" init -q
git -C "$ARCHIVE_ROOT" config user.email test@example.com
git -C "$ARCHIVE_ROOT" config user.name Test
make_skill "$ARCHIVE_ROOT" source-skill
make_skill "$ARCHIVE_ROOT" umbrella-skill
git -C "$ARCHIVE_ROOT" add .
git -C "$ARCHIVE_ROOT" commit -qm base
if SKILLS_LOCAL_ROOT="$ARCHIVE_ROOT" SKILLS_REPO_ROOT="$TMP/no-public" \
  "$SCRIPT_DIR/../../skill-manage/scripts/archive-skill.sh" source-skill \
    --absorbed-into umbrella-skill >/dev/null 2>&1; then
  fail "consolidation archive bypassed the evaluation gate"
fi
make_run "$ARCHIVE_ROOT/umbrella-skill" >/dev/null
SKILLS_LOCAL_ROOT="$ARCHIVE_ROOT" SKILLS_REPO_ROOT="$TMP/no-public" \
  SKILLS_COAUTHOR_TRAILER="Reviewed-by: fixture" \
  "$SCRIPT_DIR/../../skill-manage/scripts/archive-skill.sh" source-skill \
    --absorbed-into umbrella-skill >/dev/null
[[ ! -e "$ARCHIVE_ROOT/source-skill" ]] || fail "evaluated consolidation did not archive source"
pass "consolidation archive enforces the destination evaluation gate"

PUBLIC_ROOT="$TMP/cross-public"
LOCAL_ROOT="$TMP/cross-local"
mkdir -p "$PUBLIC_ROOT/skills" "$PUBLIC_ROOT/.claude-plugin" "$PUBLIC_ROOT/.codex-plugin" "$LOCAL_ROOT"
git -C "$PUBLIC_ROOT" init -q
git -C "$LOCAL_ROOT" init -q
for root in "$PUBLIC_ROOT" "$LOCAL_ROOT"; do
  git -C "$root" config user.email test@example.com
  git -C "$root" config user.name Test
done
echo '{"name":"fixture","version":"0.1.0","skills":["./skills/public-source"]}' > "$PUBLIC_ROOT/.claude-plugin/plugin.json"
echo '{"name":"fixture","metadata":{"version":"0.1.0"},"plugins":[{"name":"fixture","version":"0.1.0"}]}' > "$PUBLIC_ROOT/.claude-plugin/marketplace.json"
echo '{"name":"fixture","version":"0.1.0"}' > "$PUBLIC_ROOT/.codex-plugin/plugin.json"
make_skill "$PUBLIC_ROOT/skills" public-source
make_skill "$LOCAL_ROOT" local-umbrella
git -C "$PUBLIC_ROOT" add . && git -C "$PUBLIC_ROOT" commit -qm base
git -C "$LOCAL_ROOT" add . && git -C "$LOCAL_ROOT" commit -qm base
make_run "$LOCAL_ROOT/local-umbrella" >/dev/null
if SKILLS_REPO_ROOT="$PUBLIC_ROOT" SKILLS_LOCAL_ROOT="$LOCAL_ROOT" \
  "$SCRIPT_DIR/../../skill-manage/scripts/archive-skill.sh" public-source \
    --absorbed-into local-umbrella >/dev/null 2>&1; then
  fail "public source accepted a local-only replacement"
fi
pass "consolidation replacement must remain in the source root"

echo "PASS  $passes deterministic skill-evaluation checks"
