#!/usr/bin/env bash
# Deterministic M1 checks for routing records and schema-v2 evidence.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/evidence-envelope-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
passes=0

pass() { echo "PASS  $*"; passes=$((passes + 1)); }
fail() { echo "FAIL  $*" >&2; exit 1; }
assert_eq() { [[ "$1" == "$2" ]] || fail "$3 (expected '$2', got '$1')"; }

export SKILLS_REPO_ROOT="$TMP/public"
export SKILLS_LOCAL_ROOT="$TMP/local"
export SKILLS_STATE_DIR="$TMP/state"
mkdir -p "$SKILLS_REPO_ROOT/skills" "$SKILLS_LOCAL_ROOT" "$SKILLS_STATE_DIR"

make_skill() {
  local name="$1"
  mkdir -p "$SKILLS_LOCAL_ROOT/$name"
  cat > "$SKILLS_LOCAL_ROOT/$name/SKILL.md" <<EOF
---
name: $name
description: Test skill. Use when running evidence fixtures.
---

# $name

Fixture.
EOF
}

json_get() {
  python3 -c "import json; print($1)" < "$2"
}

make_skill sample
SKILLS_LOCK_HELD_BY_PARENT=1 "$SCRIPT_DIR/mark-agent-created.sh" \
  sample session-one dispatch \
  --task-key task:11111111-1111-1111-1111-111111111111 \
  --independence verified \
  --summary "Reusable procedure from fixture one" \
  --routing-reason "Fixture procedure is reusable" >/dev/null
[[ -f "$SKILLS_LOCAL_ROOT/sample/.agent-created" ]] || fail "authority marker missing"
"$SCRIPT_DIR/evidence-envelope.py" validate \
  "$SKILLS_LOCAL_ROOT/sample/.agent-created.json" >/dev/null
assert_eq "$(json_get 'json.load(open(0))["schema_version"]' "$SKILLS_LOCAL_ROOT/sample/.agent-created.json")" \
  "2" "new schema version"
pass "new provenance writes schema v2 before the marker"

"$SCRIPT_DIR/evidence-envelope.py" upsert "$SKILLS_LOCAL_ROOT/sample/.agent-created.json" \
  --skill sample --session-id session-two --source-mode dispatch \
  --task-key task:11111111-1111-1111-1111-111111111111 \
  --independence verified --evidence-kind independent-recurrence \
  --summary "Continuation of fixture one" --destination skill \
  --reason "Same task continued" >/dev/null
assert_eq "$(json_get 'len(json.load(open(0))["evidence"])' "$SKILLS_LOCAL_ROOT/sample/.agent-created.json")" \
  "1" "same-task dedup"
pass "handoff task key deduplicates across sessions"

"$SCRIPT_DIR/evidence-envelope.py" upsert "$SKILLS_LOCAL_ROOT/sample/.agent-created.json" \
  --skill sample --session-id session-three --source-mode dispatch \
  --task-key task:22222222-2222-2222-2222-222222222222 \
  --independence verified --evidence-kind independent-recurrence \
  --summary "Independent same-day fixture" --destination skill \
  --reason "Independent task repeated the procedure" >/dev/null
assert_eq "$(json_get 'len(json.load(open(0))["evidence"])' "$SKILLS_LOCAL_ROOT/sample/.agent-created.json")" \
  "2" "distinct task append"
assert_eq "$("$SCRIPT_DIR/evidence-envelope.py" validate "$SKILLS_LOCAL_ROOT/sample/.agent-created.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["verified_task_count"])')" \
  "2" "verified task count"
pass "distinct same-day tasks count independently"

"$SCRIPT_DIR/evidence-envelope.py" upsert "$SKILLS_LOCAL_ROOT/sample/.agent-created.json" \
  --skill sample --session-id session-four --source-mode sweep \
  --task-key task:33333333-3333-3333-3333-333333333333 \
  --independence unverified --evidence-kind successful-procedure \
  --summary "Historical task with unknown lineage" --destination skill \
  --reason "Historical recurrence is not independently verified" >/dev/null
assert_eq "$("$SCRIPT_DIR/evidence-envelope.py" validate "$SKILLS_LOCAL_ROOT/sample/.agent-created.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["verified_task_count"])')" \
  "2" "unverified task strength"
pass "unverified sweep evidence does not inflate strength"

"$SCRIPT_DIR/append-skill-evidence.sh" sample session-five dispatch \
  --task-key task:77777777-7777-7777-7777-777777777777 \
  --summary "Patch evidence fixture" \
  --routing-reason "Existing agent-created skill absorbed the procedure" >/dev/null
assert_eq "$(json_get 'len(json.load(open(0))["evidence"])' "$SKILLS_LOCAL_ROOT/sample/.agent-created.json")" \
  "4" "patch evidence append"
pass "agent-created patch appends evidence"

make_skill handmade
if SKILLS_LOCK_HELD_BY_PARENT=1 "$SCRIPT_DIR/append-skill-evidence.sh" \
  handmade session-six dispatch \
  --task-key task:88888888-8888-8888-8888-888888888888 \
  --summary "Hand-made patch" --routing-reason "Must remain hand-made" \
  >/dev/null 2>&1; then
  fail "hand-made skill accepted evidence authority"
fi
pass "hand-made patches cannot gain agent authority"

make_skill legacy
cat > "$SKILLS_LOCAL_ROOT/legacy/.agent-created.json" <<'JSON'
{
  "skill": "legacy",
  "created_by": "skill-review",
  "source_session_id": "legacy-session",
  "source_mode": "sweep",
  "review_prompt_version": "skill-review-1",
  "created_at": "2026-01-01T00:00:00+00:00",
  "future_field": {"preserve": true}
}
JSON
"$SCRIPT_DIR/evidence-envelope.py" upsert "$SKILLS_LOCAL_ROOT/legacy/.agent-created.json" \
  --skill legacy --session-id current-session --source-mode dispatch \
  --task-key task:44444444-4444-4444-4444-444444444444 \
  --independence verified --evidence-kind failure-recovery \
  --summary "New evidence appended to legacy provenance" --destination skill \
  --reason "Legacy skill solved another task" >/dev/null
assert_eq "$(json_get 'json.load(open(0))["source_session_id"]' "$SKILLS_LOCAL_ROOT/legacy/.agent-created.json")" \
  "legacy-session" "v1 source mirror"
assert_eq "$(json_get 'json.load(open(0))["review_prompt_version"]' "$SKILLS_LOCAL_ROOT/legacy/.agent-created.json")" \
  "skill-review-1" "v1 prompt version"
assert_eq "$(json_get 'json.load(open(0))["future_field"]["preserve"]' "$SKILLS_LOCAL_ROOT/legacy/.agent-created.json")" \
  "True" "unknown field preservation"
pass "schema v1 migrates lazily without losing reader fields"

cp "$SKILLS_LOCAL_ROOT/sample/.agent-created.json" "$TMP/malformed.json"
python3 - "$TMP/malformed.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["routing"]["destination"] = "invented"
json.dump(d, open(p, "w"))
PY
if "$SCRIPT_DIR/evidence-envelope.py" validate "$TMP/malformed.json" >/dev/null 2>&1; then
  fail "invalid destination passed validation"
fi
echo '{' > "$TMP/broken.json"
if "$SCRIPT_DIR/evidence-envelope.py" validate "$TMP/broken.json" >/dev/null 2>&1; then
  fail "malformed JSON passed validation"
fi
pass "invalid routing and malformed JSON fail closed"

LEDGER_PAYLOAD='{"session_id":"route-session","mode":"dispatch","routed":[{"destination":"discard","reason":"Transient observation","task_key":"task:55555555-5555-5555-5555-555555555555"}]}'
"$SCRIPT_DIR/review-ledger.sh" append "$LEDGER_PAYLOAD" >/dev/null
assert_eq "$("$SCRIPT_DIR/review-ledger.sh" list 1 | python3 -c 'import json,sys; print(json.load(sys.stdin)["routed"][0]["destination"])')" \
  "discard" "routed ledger destination"
if "$SCRIPT_DIR/review-ledger.sh" append \
  '{"session_id":"bad-route","mode":"dispatch","routed":[{"destination":"other","reason":"x","task_key":"task:badbadbad"}]}' \
  >/dev/null 2>&1; then
  fail "invalid ledger route passed"
fi
pass "ledger records and validates non-artifact routes"

make_skill interrupted
cat > "$SKILLS_LOCAL_ROOT/interrupted/.agent-created.json" <<'JSON'
{
  "schema_version": 2,
  "skill": "interrupted",
  "created_by": "skill-review",
  "source_session_id": "resume-session",
  "source_mode": "dispatch",
  "review_prompt_version": "skill-review-2",
  "created_at": "2026-01-01T00:00:00+00:00",
  "evidence": [{
    "task_key": "task:66666666-6666-6666-6666-666666666666",
    "session_id": "resume-session",
    "observed_at": "2026-01-01T00:00:00+00:00",
    "independence": "verified",
    "evidence_kind": "successful-procedure",
    "summary": "Resumable envelope"
  }],
  "routing": {"destination": "skill", "reason": "Resumable fixture"},
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
JSON
SKILLS_LOCK_HELD_BY_PARENT=1 "$SCRIPT_DIR/mark-agent-created.sh" \
  interrupted resume-session dispatch \
  --task-key task:66666666-6666-6666-6666-666666666666 \
  --summary "Resumable envelope" --routing-reason "Resumable fixture" >/dev/null
[[ -f "$SKILLS_LOCAL_ROOT/interrupted/.agent-created" ]] || fail "resumed marker missing"
pass "valid envelope without marker resumes safely"

make_skill marker-only
touch "$SKILLS_LOCAL_ROOT/marker-only/.agent-created"
if SKILLS_LOCK_HELD_BY_PARENT=1 "$SCRIPT_DIR/mark-agent-created.sh" \
  marker-only marker-session dispatch >/dev/null 2>&1; then
  fail "marker-only state was silently re-authorized"
fi
SKILLS_LOCK_HELD_BY_PARENT=1 "$SCRIPT_DIR/mark-agent-created.sh" \
  marker-only marker-session dispatch \
  --repair-marker-only \
  --task-key task:99999999-9999-9999-9999-999999999999 \
  --independence verified \
  --evidence-kind owner-correction \
  --summary "Explicit marker-only repair fixture" \
  --routing-reason "Owner supplied complete repair evidence" >/dev/null
"$SCRIPT_DIR/evidence-envelope.py" validate \
  "$SKILLS_LOCAL_ROOT/marker-only/.agent-created.json" >/dev/null
pass "marker-only provenance requires explicit repair evidence"

make_skill implicit-task
SKILLS_LOCK_HELD_BY_PARENT=1 "$SCRIPT_DIR/mark-agent-created.sh" \
  implicit-task implicit-session dispatch >/dev/null
assert_eq "$("$SCRIPT_DIR/evidence-envelope.py" validate "$SKILLS_LOCAL_ROOT/implicit-task/.agent-created.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["verified_task_count"])')" \
  "0" "implicit task certainty"
pass "auto-minted task keys remain unverified"

make_skill forced-certainty
SKILLS_LOCK_HELD_BY_PARENT=1 "$SCRIPT_DIR/mark-agent-created.sh" \
  forced-certainty forced-session dispatch --independence verified >/dev/null
assert_eq "$("$SCRIPT_DIR/evidence-envelope.py" validate "$SKILLS_LOCAL_ROOT/forced-certainty/.agent-created.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["verified_task_count"])')" \
  "0" "forced implicit task certainty"
pass "explicit certainty cannot bless an auto-minted task key"

CONCURRENT="$TMP/concurrent.json"
"$SCRIPT_DIR/evidence-envelope.py" upsert "$CONCURRENT" \
  --skill concurrent --session-id concurrent-one --source-mode dispatch \
  --task-key task:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa \
  --independence verified --evidence-kind successful-procedure \
  --summary "Concurrent fixture one" --destination skill \
  --reason "First concurrent task" >/dev/null
"$SCRIPT_DIR/evidence-envelope.py" upsert "$CONCURRENT" \
  --skill concurrent --session-id concurrent-two --source-mode dispatch \
  --task-key task:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb \
  --independence verified --evidence-kind independent-recurrence \
  --summary "Concurrent fixture two" --destination skill \
  --reason "Second concurrent task" >/dev/null &
pid_one=$!
"$SCRIPT_DIR/evidence-envelope.py" upsert "$CONCURRENT" \
  --skill concurrent --session-id concurrent-three --source-mode dispatch \
  --task-key task:cccccccc-cccc-cccc-cccc-cccccccccccc \
  --independence verified --evidence-kind independent-recurrence \
  --summary "Concurrent fixture three" --destination skill \
  --reason "Third concurrent task" >/dev/null &
pid_two=$!
wait "$pid_one" "$pid_two"
assert_eq "$(json_get 'len(json.load(open(0))["evidence"])' "$CONCURRENT")" \
  "3" "concurrent evidence count"
pass "concurrent distinct upserts retain every task"

echo "PASS  $passes deterministic evidence-envelope checks"
