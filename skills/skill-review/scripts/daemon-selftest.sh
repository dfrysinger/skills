#!/usr/bin/env bash
# daemon-selftest.sh — preflight for the skills self-learning daemon.
#
# Validates everything the unattended launchd jobs depend on. Run it both in a
# normal shell AND under launchd context (via launchctl kickstart of the
# selftest agent) to catch environment/auth differences — keychain search lists
# and credential helpers can behave differently for background GUI-session jobs.
#
# Exits 0 only if every REQUIRED check passes. The copilot-auth check makes one
# real (cheap) headless call.

set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="$HOME/code/skills"
COPILOT="$HOME/.local/bin/copilot"
STATE_DIR="$HOME/.copilot/skill-state"
SENTINEL='[AUTOREVIEW-DAEMON-SESSION:96efca49-7380-4494-86c4-ab4ab954ee3f]'
SWEEP_PROMPT="$REPO/skills/skill-review/references/sweep-prompt.txt"
TICK_PROMPT="$REPO/skills/skill-curator/references/tick-prompt.txt"
LOCAL_ROOT="$HOME/.copilot/skills"
HALT_SWITCH="$STATE_DIR/skill-review/disable-daemon"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-daemon.sh
source "$SCRIPT_DIR/lib-daemon.sh"
export GIT_TERMINAL_PROMPT=0   # never hang on a credential prompt during selftest

RESULT="$STATE_DIR/daemon-selftest.out"
mkdir -p "$STATE_DIR"
: > "$RESULT"
fails=0
ok()   { echo "PASS  $*" | tee -a "$RESULT"; }
bad()  { echo "FAIL  $*" | tee -a "$RESULT"; fails=$((fails+1)); }
warn() { echo "WARN  $*" | tee -a "$RESULT"; }

echo "== skills daemon self-test $(date '+%Y-%m-%dT%H:%M:%S%z') ==" | tee -a "$RESULT"
echo "context: uid=$(id -u) shell-tty=$([[ -t 1 ]] && echo yes || echo no)" | tee -a "$RESULT"

# 1. copilot binary
[[ -x "$COPILOT" ]] && ok "copilot executable at $COPILOT" || bad "copilot not executable at $COPILOT"

# 2. prompt files present + sentinel is the literal first non-empty line
for f in "$SWEEP_PROMPT" "$TICK_PROMPT"; do
  if [[ -f "$f" ]]; then
    first="$(grep -m1 . "$f")"
    [[ "$first" == "$SENTINEL" ]] && ok "prompt sentinel ok: $(basename "$f")" \
      || bad "prompt sentinel missing/not-first-line: $(basename "$f")"
  else
    bad "prompt file missing: $f"
  fi
done

# 3. lock dir writable
LT="$STATE_DIR/.selftest-lock.$$"
if mkdir "$LT" 2>/dev/null; then ok "state dir writable (lock test)"; rmdir "$LT"; else bad "cannot create lock dir under $STATE_DIR"; fi

# 4. score-sessions.sh emits SQL
if "$REPO/skills/skill-review/scripts/score-sessions.sh" "2026-01-01T00:00:00" 2>/dev/null | grep -q "is_daemon = 0"; then
  ok "score-sessions.sh emits sentinel-excluding SQL"
else
  bad "score-sessions.sh did not emit expected SQL"
fi

# 5. local skills root is a git repo with NO remote (two-root invariant: the
# daemon mutates only the local root and nothing is ever pushed).
if [[ -d "$LOCAL_ROOT/.git" ]]; then
  if [[ -z "$(git -C "$LOCAL_ROOT" remote 2>/dev/null)" ]]; then
    ok "local skills root is a local git repo with no remote ($LOCAL_ROOT)"
  else
    bad "local skills root has a remote configured — must be local-only: $(git -C "$LOCAL_ROOT" remote -v | head -1)"
  fi
else
  bad "local skills root is not a git repo: $LOCAL_ROOT (run: git -C \"$LOCAL_ROOT\" init)"
fi

# 6. copilot headless auth — one cheap real call via the SAME bounded runner the
# daemon uses, so this also verifies the launchd teardown-hang handling. The
# process won't self-exit under launchd; the runner waits for the reply marker,
# then terminates. Success = marker present in the log.
AUTHLOG="$STATE_DIR/.selftest-copilot.$$"
: > "$AUTHLOG"
if skills_run_copilot_bounded "$AUTHLOG" "SELFTEST_OK" 150 5 -- \
  "$COPILOT" -p "Reply with exactly: SELFTEST_OK" \
  --allow-all-tools --no-custom-instructions --no-color --no-remote \
  --disable-builtin-mcps --disable-mcp-server slack --disable-mcp-server workiq \
  --log-level error; then
  ok "copilot headless auth (bounded run completed)"
else
  bad "copilot headless auth failed (got: $(tr -d '\n' < "$AUTHLOG" | cut -c1-80))"
fi
rm -f "$AUTHLOG"

# 7. halt switch advisory
[[ -e "$HALT_SWITCH" ]] && warn "halt switch is PRESENT ($HALT_SWITCH) — daemon runs will no-op until removed" || ok "halt switch absent (daemon enabled)"

echo "== result: $fails failure(s) ==" | tee -a "$RESULT"
exit "$([[ $fails -eq 0 ]] && echo 0 || echo 1)"
