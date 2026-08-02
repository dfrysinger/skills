#!/usr/bin/env bash
# Preflight for the effective-weekly dreaming daemon.

set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
COPILOT="${COPILOT_BIN:-$HOME/.local/bin/copilot}"
STATE_DIR="${SKILLS_STATE_DIR:-$HOME/.copilot/skill-state}"
LOCAL_ROOT="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"
HALT_SWITCH="$STATE_DIR/skill-review/disable-daemon"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-daemon.sh
source "$SCRIPT_DIR/lib-daemon.sh"

RESULT="$STATE_DIR/daemon-selftest.out"
mkdir -p "$STATE_DIR"
: > "$RESULT"
fails=0
ok() { echo "PASS  $*" | tee -a "$RESULT"; }
bad() { echo "FAIL  $*" | tee -a "$RESULT"; fails=$((fails + 1)); }
warn() { echo "WARN  $*" | tee -a "$RESULT"; }

echo "== dreaming self-test $(date '+%Y-%m-%dT%H:%M:%S%z') ==" | tee -a "$RESULT"
[[ -x "$COPILOT" ]] && ok "copilot executable" || bad "copilot not executable at $COPILOT"

MARKER='[AUTOREVIEW-DAEMON-SESSION:96efca49-7380-4494-86c4-ab4ab954ee3f]'
PROMPTS=(
  "$REPO/skills/skill-review/references/sweep-prompt.txt"
  "$REPO/skills/memory-curator/references/memory-curate-prompt.txt"
  "$REPO/skills/skill-curator/references/tick-prompt.txt"
)
for prompt in "${PROMPTS[@]}"; do
  if [[ -f "$prompt" && "$(grep -m1 . "$prompt")" == "$MARKER" ]] &&
      grep -q 'DREAM_PASS_RESULT: ok' "$prompt" &&
      grep -q 'DREAM_PASS_RESULT: aborted' "$prompt"; then
    ok "prompt contract: $(basename "$prompt")"
  else
    bad "prompt contract missing: $prompt"
  fi
done

for script in daemon-pass.sh daemon-run.sh daemon-lock.sh daemon-lock.py dreaming-run.sh dreaming-state.py test-dreaming-daemon.sh; do
  [[ -x "$SCRIPT_DIR/$script" ]] && ok "executable: $script" || bad "not executable: $script"
done

if "$SCRIPT_DIR/test-dreaming-daemon.sh" --quick >>"$RESULT" 2>&1; then
  ok "deterministic dreaming checks"
else
  bad "deterministic dreaming checks"
fi

if [[ -d "$LOCAL_ROOT/.git" && -z "$(git -C "$LOCAL_ROOT" remote 2>/dev/null)" ]]; then
  ok "local skills root is a git repo with no remote"
else
  bad "local skills root must be a git repo with no remote"
fi

AUTHLOG="$STATE_DIR/.selftest-copilot.$$"
: > "$AUTHLOG"
if skills_run_copilot_bounded "$AUTHLOG" "SELFTEST_OK" 150 5 -- \
  "$COPILOT" -p "Reply with exactly: SELFTEST_OK" \
  --allow-all-tools --no-custom-instructions --no-color --no-remote \
  --disable-builtin-mcps --log-level error; then
  ok "copilot headless auth"
else
  bad "copilot headless auth"
fi
rm -f "$AUTHLOG"

[[ -e "$HALT_SWITCH" ]] && warn "halt switch is present" || ok "halt switch absent"
echo "== result: $fails failure(s) ==" | tee -a "$RESULT"
exit "$([[ $fails -eq 0 ]] && echo 0 || echo 1)"
