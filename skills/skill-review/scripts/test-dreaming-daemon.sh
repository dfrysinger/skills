#!/usr/bin/env bash
# Deterministic checks for dreaming lock, cadence, ordering, reports, and migration.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/dreaming-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
NOW=2000000000
WEEK=604800
passes=0

pass() { echo "PASS  $*"; passes=$((passes + 1)); }
fail() { echo "FAIL  $*" >&2; exit 1; }
assert_eq() { [[ "$1" == "$2" ]] || fail "$3 (expected '$2', got '$1')"; }

FAKE_PASS="$TMP/fake-pass.sh"
cat > "$FAKE_PASS" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
name=""
log=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) name="$2"; shift 2 ;;
    --log) log="$2"; shift 2 ;;
    --prompt) shift 2 ;;
    *) exit 2 ;;
  esac
done
echo "$name" >> "$ORDER_FILE"
echo "DREAM_PASS_RESULT: ok fake=$name" > "$log"
if [[ "${FAKE_HALT_AFTER:-}" == "$name" ]]; then
  mkdir -p "$SKILLS_STATE_DIR/skill-review"
  touch "$SKILLS_STATE_DIR/skill-review/disable-daemon"
fi
[[ "${FAKE_FAIL_PASS:-}" != "$name" ]]
SH
chmod +x "$FAKE_PASS"

new_case() {
  local name="$1"
  CASE="$TMP/$name"
  mkdir -p "$CASE/state" "$CASE/logs"
  export SKILLS_STATE_DIR="$CASE/state"
  export DREAMING_STATE_DIR="$CASE/state/dreaming"
  export SKILLS_LOCK_DIR="$CASE/state/daemon.lock"
  export SKILLS_REPO_ROOT="$REPO"
  export DREAMING_PASS_RUNNER="$FAKE_PASS"
  export DREAMING_LEGACY_CURATOR_STATE="$CASE/no-curator.json"
  export DREAMING_LEGACY_MEMORY_STATE="$CASE/no-memory.json"
  export DREAMING_NOW_EPOCH="$NOW"
  export SKILLS_NOW_EPOCH="$NOW"
  export ORDER_FILE="$CASE/order"
  : > "$ORDER_FILE"
  unset FAKE_FAIL_PASS FAKE_HALT_AFTER DREAMING_FORCE_DUE
}

make_process_lock() {
  local pid="$1" identity="$2" renewed="$3"
  "$SCRIPT_DIR/daemon-lock.py" seed --mode process --owner test-owner \
    --token old-token --started "$renewed" --renewed "$renewed" \
    --pid "$pid" --process-identity "$identity"
}

new_case live-owner
identity="$(/bin/ps -o lstart= -p $$ | /usr/bin/awk '{$1=$1; print}')"
make_process_lock "$$" "$identity" "$((NOW - 10000))"
if "$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner contender >/dev/null 2>&1; then
  fail "live owner was displaced"
fi
pass "live process owner is never displaced"

new_case reused-pid
make_process_lock "$$" "wrong identity" "$((NOW - 10000))"
token="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner replacement)"
"$SCRIPT_DIR/daemon-lock.sh" release "$token"
pass "reused PID does not preserve stale ownership"

new_case young-dead
make_process_lock 999999 "dead" "$((NOW - 10))"
if "$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner contender >/dev/null 2>&1; then
  fail "young dead lock was reclaimed"
fi
pass "young dead owner fails closed"

new_case stale-dead
make_process_lock 999999 "dead" "$((NOW - 10000))"
token="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner replacement)"
"$SCRIPT_DIR/daemon-lock.sh" release "$token"
pass "stale dead owner is reclaimed"

new_case malformed
echo "not a sqlite database" > "$SKILLS_LOCK_DIR"
if "$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner contender >/dev/null 2>&1; then
  fail "malformed lock was reclaimed"
fi
pass "malformed lock fails closed"

new_case legacy-lock
mkdir -p "$SKILLS_LOCK_DIR"
printf '%s\n' 999999 > "$SKILLS_LOCK_DIR/pid"
printf '%s\n' "$((NOW - 10000))" > "$SKILLS_LOCK_DIR/start"
token="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner migrated)"
[[ -f "$SKILLS_LOCK_DIR" ]] || fail "legacy lock was not migrated to sqlite"
find "$(dirname "$SKILLS_LOCK_DIR")" -maxdepth 1 -type d -name 'daemon.lock.legacy-*' | grep -q . ||
  fail "legacy lock archive missing"
"$SCRIPT_DIR/daemon-lock.sh" release "$token"
pass "stale legacy lock is archived and migrated"

new_case legacy-reused-pid
mkdir -p "$SKILLS_LOCK_DIR"
printf '%s\n' "$$" > "$SKILLS_LOCK_DIR/pid"
printf '%s\n' "$((NOW - 10000))" > "$SKILLS_LOCK_DIR/renewed"
printf '%s\n' "wrong process identity" > "$SKILLS_LOCK_DIR/process_identity"
token="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner migrated)"
"$SCRIPT_DIR/daemon-lock.sh" release "$token"
pass "legacy PID reuse does not preserve stale ownership"

new_case active-lease
"$SCRIPT_DIR/dreaming-state.py" seed --bucket 100 --epoch "$NOW"
token="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner dispatch)"
"$SCRIPT_DIR/dreaming-run.sh"
reason="$("$SCRIPT_DIR/dreaming-state.py" latest | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["reason"])')"
assert_eq "$reason" "lock-contention" "active dispatch lease outcome"
assert_eq "$(wc -l < "$ORDER_FILE" | tr -d ' ')" "0" "active lease launched a pass"
assert_eq "$(/usr/bin/python3 - "$DREAMING_STATE_DIR/cadence.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["last_success_bucket"])
PY
)" "100" "contention overwrote cadence"
"$SCRIPT_DIR/daemon-lock.sh" release "$token"
pass "active dispatch lease blocks the orchestrator without overwriting cadence"

new_case expired-lease
export SKILLS_NOW_EPOCH="$((NOW - 10000))"
token="$("$SCRIPT_DIR/daemon-lock.sh" acquire --mode session --owner old-dispatch)"
export SKILLS_NOW_EPOCH="$NOW"
export DREAMING_FORCE_DUE=1
"$SCRIPT_DIR/dreaming-run.sh"
if "$SCRIPT_DIR/daemon-lock.sh" renew "$token" >/dev/null 2>&1; then
  fail "reclaimed dispatch token renewed"
fi
assert_eq "$(paste -sd, "$ORDER_FILE")" "skills-consolidate,skills-roll,skills-prune" "expired lease order"
pass "expired lease is reclaimed and fenced"

new_case ordered-success
export DREAMING_FORCE_DUE=1
"$SCRIPT_DIR/dreaming-run.sh"
assert_eq "$(paste -sd, "$ORDER_FILE")" "skills-consolidate,skills-roll,skills-prune" "successful order"
assert_eq "$(wc -l < "$DREAMING_STATE_DIR/ledger.jsonl" | tr -d ' ')" "1" "success ledger count"
[[ -f "$DREAMING_LEGACY_MEMORY_STATE" ]] || fail "fresh memory state was not initialized"
pass "successful pipeline is ordered and ledgered once"

new_case daily-consolidate
current_bucket="$("$SCRIPT_DIR/dreaming-state.py" bucket)"
"$SCRIPT_DIR/dreaming-state.py" seed --bucket "$current_bucket" --epoch "$NOW"
"$SCRIPT_DIR/dreaming-run.sh"
assert_eq "$(paste -sd, "$ORDER_FILE")" "skills-consolidate" "daily consolidate order"
latest="$("$SCRIPT_DIR/dreaming-state.py" latest)"
assert_eq "$(printf '%s' "$latest" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')" "ok" "daily consolidate status"
assert_eq "$(printf '%s' "$latest" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["reason"])')" "consolidate-only" "daily consolidate reason"
assert_eq "$(printf '%s' "$latest" | /usr/bin/python3 -c 'import json,sys; print(",".join(item["status"] for item in json.load(sys.stdin)["passes"]))')" "ok,not_scheduled,not_scheduled" "daily pass statuses"
assert_eq "$(printf '%s' "$latest" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["cadence_committed"])')" "True" "daily result was not finalized"
assert_eq "$(/usr/bin/python3 - "$DREAMING_STATE_DIR/cadence.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["last_success_bucket"])
PY
)" "$current_bucket" "daily consolidate changed weekly cadence"
pass "consolidate runs daily while roll and prune remain weekly"

new_case single-pass-parent-lock
PROMPT="$CASE/prompt.txt"
echo prompt > "$PROMPT"
"$SCRIPT_DIR/daemon-run.sh" --prompt "$PROMPT" --name compatibility
assert_eq "$(paste -sd, "$ORDER_FILE")" "compatibility" "single-pass wrapper"
pass "single-pass compatibility wrapper delegates under its parent lock"

new_case roll-failure
export DREAMING_FORCE_DUE=1
export FAKE_FAIL_PASS=skills-roll
if "$SCRIPT_DIR/dreaming-run.sh"; then
  fail "roll failure returned success"
fi
assert_eq "$(paste -sd, "$ORDER_FILE")" "skills-consolidate,skills-roll" "fail-fast order"
status="$("$SCRIPT_DIR/dreaming-state.py" latest | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
assert_eq "$status" "aborted" "failed run status"
pass "roll failure prevents prune"

new_case halt-between
export DREAMING_FORCE_DUE=1
export FAKE_HALT_AFTER=skills-consolidate
if "$SCRIPT_DIR/dreaming-run.sh"; then
  fail "mid-run halt returned success"
fi
assert_eq "$(paste -sd, "$ORDER_FILE")" "skills-consolidate" "halt fail-fast order"
pass "halt between passes prevents downstream work"

new_case stable-buckets
"$SCRIPT_DIR/dreaming-state.py" seed --bucket 10 --epoch "$((10 * WEEK))"
export DREAMING_NOW_EPOCH="$((11 * WEEK + 60))"
"$SCRIPT_DIR/dreaming-state.py" due || fail "next weekly bucket was not due"
"$SCRIPT_DIR/dreaming-state.py" record --run-id bucket-run --status ok --reason completed \
  --started-at 2000-01-01T00:00:00+00:00 --start-epoch "$DREAMING_NOW_EPOCH"
"$SCRIPT_DIR/dreaming-state.py" commit-success --run-id bucket-run --completed-epoch "$((11 * WEEK + 3600))"
export DREAMING_NOW_EPOCH="$((11 * WEEK + WEEK - 1))"
if "$SCRIPT_DIR/dreaming-state.py" due; then fail "same bucket became due"; fi
export DREAMING_NOW_EPOCH="$((12 * WEEK + 1))"
"$SCRIPT_DIR/dreaming-state.py" due || fail "following bucket was not due"
pass "weekly cadence is bucket-anchored"

new_case boundary-bucket
"$SCRIPT_DIR/dreaming-state.py" seed --bucket 30 --epoch "$((30 * WEEK))"
"$SCRIPT_DIR/dreaming-state.py" record --run-id boundary-run --status ok --reason completed \
  --started-at 2000-01-01T00:00:00+00:00 --start-epoch "$((31 * WEEK - 10))"
"$SCRIPT_DIR/dreaming-state.py" commit-success --run-id boundary-run --completed-epoch "$((31 * WEEK + 10))"
assert_eq "$(/usr/bin/python3 - "$DREAMING_STATE_DIR/cadence.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["last_success_bucket"])
PY
)" "30" "boundary-crossing cadence bucket"
pass "completion after a boundary commits the start bucket"

new_case persistence-repair
"$SCRIPT_DIR/dreaming-state.py" seed --bucket 20 --epoch "$((20 * WEEK))"
"$SCRIPT_DIR/dreaming-state.py" record --run-id repair-run --status ok --reason completed \
  --started-at 2000-01-01T00:00:00+00:00 --start-epoch "$NOW"
"$SCRIPT_DIR/dreaming-state.py" seed --bucket 21 --epoch "$NOW" --run-id repair-run
"$SCRIPT_DIR/dreaming-state.py" repair
committed="$(/usr/bin/python3 - "$DREAMING_STATE_DIR/runs/repair-run.json" <<'PY'
import json,sys
print(str(json.load(open(sys.argv[1]))["cadence_committed"]).lower())
PY
)"
assert_eq "$committed" "true" "repair commit marker"
assert_eq "$(wc -l < "$DREAMING_STATE_DIR/ledger.jsonl" | tr -d ' ')" "1" "repair ledger count"
"$SCRIPT_DIR/dreaming-state.py" repair
assert_eq "$(wc -l < "$DREAMING_STATE_DIR/ledger.jsonl" | tr -d ' ')" "1" "repair dedup count"
pass "persistence repair is idempotent"

new_case terminal-cadence
"$SCRIPT_DIR/dreaming-state.py" seed --bucket 40 --epoch "$((40 * WEEK))"
"$SCRIPT_DIR/dreaming-state.py" record --run-id skipped-run --status skipped \
  --reason cadence-not-due --started-at 2000-01-01T00:00:00+00:00 --start-epoch "$NOW"
assert_eq "$(/usr/bin/python3 - "$DREAMING_STATE_DIR/runs/skipped-run.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
print(f"{r['last_success_bucket_before']}:{r['last_success_bucket_after']}")
PY
)" "40:40" "non-success cadence before/after"
pass "non-success records preserve explicit cadence after-state"

new_case malformed-state
mkdir -p "$DREAMING_STATE_DIR"
echo malformed > "$DREAMING_STATE_DIR/cadence.json"
export DREAMING_FORCE_DUE=1
if "$SCRIPT_DIR/dreaming-run.sh" >/dev/null 2>&1; then
  fail "malformed cadence state returned success"
fi
assert_eq "$(wc -l < "$ORDER_FILE" | tr -d ' ')" "0" "malformed state launched passes"
latest="$("$SCRIPT_DIR/dreaming-state.py" latest)"
assert_eq "$(printf '%s' "$latest" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')" "aborted" "state failure status"
assert_eq "$(wc -l < "$DREAMING_STATE_DIR/ledger.jsonl" | tr -d ' ')" "1" "state failure ledger count"
pass "state failures abort before mutation and remain observable"

new_case invalid-cadence-type
mkdir -p "$DREAMING_STATE_DIR"
echo '{"last_success_bucket":"abc","last_success_at":null}' > "$DREAMING_STATE_DIR/cadence.json"
if "$SCRIPT_DIR/dreaming-run.sh" >/dev/null 2>&1; then
  fail "invalid cadence type returned success"
fi
reason="$("$SCRIPT_DIR/dreaming-state.py" latest | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["reason"])')"
assert_eq "$reason" "cadence-eval-failed" "invalid cadence type outcome"
pass "invalid cadence values abort instead of becoming healthy skips"

new_case nonobject-cadence
mkdir -p "$DREAMING_STATE_DIR"
echo '[]' > "$DREAMING_STATE_DIR/cadence.json"
if "$SCRIPT_DIR/dreaming-run.sh" >/dev/null 2>&1; then
  fail "non-object cadence returned success"
fi
latest="$("$SCRIPT_DIR/dreaming-state.py" latest)"
assert_eq "$(printf '%s' "$latest" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["reason"])')" "state-init-failed" "non-object cadence outcome"
assert_eq "$(wc -l < "$DREAMING_STATE_DIR/ledger.jsonl" | tr -d ' ')" "1" "non-object cadence ledger count"
pass "non-object cadence remains observable as an aborted tick"

new_case public-baseline
PUBLIC="$CASE/public"
mkdir -p "$PUBLIC"
git -C "$PUBLIC" init -q
git -C "$PUBLIC" config user.email test@example.com
git -C "$PUBLIC" config user.name Test
echo base > "$PUBLIC/file"
printf '.DS_Store\n__pycache__/\n' > "$PUBLIC/.gitignore"
git -C "$PUBLIC" add -- file .gitignore
git -C "$PUBLIC" commit -qm base
echo human >> "$PUBLIC/file"
SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" snapshot >/dev/null
SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" check >/dev/null
echo daemon-injected >> "$PUBLIC/file"
if SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" check >/dev/null 2>&1; then
  fail "public baseline missed dirty-file content mutation"
fi
git -C "$PUBLIC" restore -- file
echo human >> "$PUBLIC/file"
SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" snapshot >/dev/null
echo ignored > "$PUBLIC/.DS_Store"
SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" check >/dev/null
OUT1="$CASE/outside-one"
OUT2="$CASE/outside-two"
mkdir -p "$OUT1" "$OUT2"
ln -s "$OUT1" "$PUBLIC/linkdir"
SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" snapshot >/dev/null
ln -sfn "$OUT2" "$PUBLIC/linkdir"
if SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" check >/dev/null 2>&1; then
  fail "public baseline missed directory symlink retarget"
fi
rm -f "$PUBLIC/linkdir"
SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" snapshot >/dev/null
echo daemon > "$PUBLIC/other"
if SKILLS_REPO_ROOT="$PUBLIC" "$SCRIPT_DIR/verify-repo-unchanged.sh" check >/dev/null 2>&1; then
  fail "public baseline missed a new change"
fi
pass "public guard preserves pre-existing dirt and catches new changes"

new_case installer-migration
DEST="$CASE/LaunchAgents"
mkdir -p "$DEST"
FAKE_LAUNCHCTL="$CASE/launchctl"
cat > "$FAKE_LAUNCHCTL" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "$LAUNCHCTL_LOG"
exit 0
SH
chmod +x "$FAKE_LAUNCHCTL"
export LAUNCHCTL_LOG="$CASE/launchctl.log"
for kind in sweep curator memory selftest watchdog; do
  echo "<plist><dict><key>Label</key><string>com.${USER}.skills.$kind</string></dict></plist>" \
    > "$DEST/com.${USER}.skills.$kind.plist"
done
SKILLS_LAUNCH_AGENTS_DIR="$DEST" LAUNCHCTL_BIN="$FAKE_LAUNCHCTL" \
  "$SCRIPT_DIR/daemon-install.sh" install >/dev/null
for kind in dreaming selftest watchdog; do
  [[ -f "$DEST/com.${USER}.skills.$kind.plist" ]] || fail "installer missed $kind"
done
for kind in sweep curator memory; do
  [[ ! -f "$DEST/com.${USER}.skills.$kind.plist" ]] || fail "installer retained legacy $kind"
done
backup="$(<"$SKILLS_STATE_DIR/dreaming/latest-migration-backup")"
assert_eq "$(find "$backup" -name '*.plist' | wc -l | tr -d ' ')" "5" "migration backup count"
SKILLS_LAUNCH_AGENTS_DIR="$DEST" LAUNCHCTL_BIN="$FAKE_LAUNCHCTL" \
  "$SCRIPT_DIR/daemon-install.sh" install >/dev/null
assert_eq "$(<"$SKILLS_STATE_DIR/dreaming/latest-migration-backup")" "$backup" "legacy rollback pointer changed on reinstall"
"$SCRIPT_DIR/daemon-lock.py" acquire --mode session --owner rollback-test > "$CASE/rollback-token"
"$SCRIPT_DIR/daemon-lock.py" release "$(<"$CASE/rollback-token")"
SKILLS_LAUNCH_AGENTS_DIR="$DEST" LAUNCHCTL_BIN="$FAKE_LAUNCHCTL" \
  "$SCRIPT_DIR/daemon-install.sh" rollback "$backup" >/dev/null
for kind in sweep curator memory; do
  [[ -f "$DEST/com.${USER}.skills.$kind.plist" ]] || fail "rollback missed $kind"
done
for kind in selftest watchdog; do
  [[ -f "$DEST/com.${USER}.skills.$kind.plist" ]] || fail "rollback missed prior $kind"
done
[[ ! -f "$DEST/com.${USER}.skills.dreaming.plist" ]] || fail "rollback retained dreaming"
[[ ! -e "$SKILLS_STATE_DIR/daemon.lock" ]] || fail "rollback retained SQLite lock at legacy path"
pass "installer migrates and restores exact legacy plists"

new_case watchdog
mkdir -p "$SKILLS_STATE_DIR/daemon-logs" "$DREAMING_STATE_DIR/runs"
echo healthy > "$SKILLS_STATE_DIR/daemon-logs/20200101T000000Z-1-dreaming.log"
"$SCRIPT_DIR/dreaming-state.py" seed --bucket "$((NOW / WEEK))" --epoch "$NOW"
"$SCRIPT_DIR/dreaming-state.py" record --run-id watchdog-run --status skipped \
  --reason cadence-not-due --started-at 2000-01-01T00:00:00+00:00 --start-epoch "$NOW"
touch -t "$(date -r "$NOW" +%Y%m%d%H%M.%S)" \
  "$SKILLS_STATE_DIR/daemon-logs/20200101T000000Z-1-dreaming.log"
touch -t "$(date -r "$NOW" +%Y%m%d%H%M.%S)" \
  "$DREAMING_STATE_DIR/runs/watchdog-run.json"
"$SCRIPT_DIR/daemon-watchdog.sh" >/dev/null
"$SCRIPT_DIR/dreaming-state.py" seed --bucket "$((NOW / WEEK - 3))" --epoch "$((NOW - 3 * WEEK))"
if "$SCRIPT_DIR/daemon-watchdog.sh" >/dev/null 2>&1; then
  fail "watchdog accepted overdue cadence"
fi
pass "watchdog distinguishes healthy skips from overdue success"

echo "PASS  $passes deterministic dreaming checks"
