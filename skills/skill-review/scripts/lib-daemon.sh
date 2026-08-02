#!/usr/bin/env bash
# lib-daemon.sh — shared helpers for the skills self-learning launchd daemon.
# Sourced by daemon-run.sh and daemon-selftest.sh.
#
# Provides two things the unattended launchd jobs need but a normal interactive
# shell does not:
#
#  A. Non-interactive GitHub token auth (skills_setup_git_auth). Under a
#     background launchd GUI-session context the default git credential helper
#     (osxkeychain) prompts for keychain access and HANGS with no TTY — a plain
#     `git push` never returns. We export GH_TOKEN + an inline credential helper
#     via GIT_CONFIG_* so EVERY child git inherits it (including the git pushes
#     the headless `copilot` sweep makes). Nothing is persisted to git config and
#     the token is never written to logs. Token sources, first valid wins:
#       1. `gh auth token` — authoritative (correct account/push rights).
#       2. explicit login-keychain read (`security -w`, base64-decoded) — the
#          reads the token directly; survives the restricted launchd keychain
#          search list where (1) can fail. Fallback only.
#
#  B. A completion-aware bounded copilot runner (skills_run_copilot_bounded).
#     Under launchd the headless `copilot` process completes its work and prints
#     its end-of-session summary footer, then FAILS TO EXIT (sits at 0% CPU
#     indefinitely) — independent of MCP/remote flags. We watch the log for a
#     completion marker, allow a short flush grace, then TERM/KILL. Success is
#     judged by the marker, not the (watchdog-forced) exit code.

# Echo a usable GitHub token to stdout (empty if none). Never logs the token.
skills_derive_github_token() {
  local host="${1:-github.com}" tok raw
  tok="$(gh auth token -h "$host" 2>/dev/null || true)"
  if [[ -z "$tok" ]]; then
    raw="$(/usr/bin/security find-generic-password -s "gh:${host}" -a "$USER" -w \
          "$HOME/Library/Keychains/login.keychain-db" 2>/dev/null || true)"
    if [[ -n "$raw" ]]; then
      tok="$(printf '%s' "${raw#go-keyring-base64:}" | base64 -D 2>/dev/null || true)"
    fi
  fi
  printf '%s' "$tok"
}

# Export GH_TOKEN + an inline credential helper so all child git processes
# authenticate over HTTPS without the hanging osxkeychain helper. Returns
# non-zero (and exports nothing) if no token could be derived.
skills_setup_git_auth() {
  local host="${1:-github.com}" tok
  tok="$(skills_derive_github_token "$host")"
  [[ -n "$tok" ]] || return 1
  export GH_TOKEN="$tok"
  export GIT_TERMINAL_PROMPT=0
  # Belt-and-suspenders: make sure no git tracing is on that could echo the
  # credential exchange (and thus the token) into a log.
  unset GIT_TRACE GIT_TRACE_CURL GIT_CURL_VERBOSE GIT_TRACE_PACKET 2>/dev/null || true
  export GIT_CONFIG_COUNT=2
  export GIT_CONFIG_KEY_0="credential.helper";  export GIT_CONFIG_VALUE_0=""
  export GIT_CONFIG_KEY_1="credential.helper"
  export GIT_CONFIG_VALUE_1='!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$GH_TOKEN"; }; f'
  return 0
}

skills_process_identity() {
  local pid="$1"
  /bin/ps -o lstart= -p "$pid" 2>/dev/null | /usr/bin/awk '{$1=$1; print}'
}

skills_lock_tool() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  printf '%s\n' "$script_dir/daemon-lock.py"
}

skills_lock_acquire() {
  local mode="$1" owner="$2"
  if [[ "$mode" == "process" ]]; then
    "$(skills_lock_tool)" acquire --mode process --owner "$owner" \
      --pid "$$" --process-identity "$(skills_process_identity "$$")"
  else
    "$(skills_lock_tool)" acquire --mode "$mode" --owner "$owner"
  fi
}

skills_lock_assert() {
  "$(skills_lock_tool)" assert "$1" --pid "$$" \
    --process-identity "$(skills_process_identity "$$" || true)"
}

skills_lock_renew() {
  "$(skills_lock_tool)" renew "$1" --pid "$$" \
    --process-identity "$(skills_process_identity "$$" || true)"
}

skills_lock_release() {
  "$(skills_lock_tool)" release "$1"
}

# Run copilot headlessly but DON'T trust it to exit (see header note B). Watch
# LOGFILE for DONE_RE; once seen, allow GRACE_SECS for final flushing then
# terminate the whole process GROUP (copilot spawns a --server child and git
# children — killing only the parent can orphan them). ABS_MAX_SECS is an
# absolute backstop. Returns 0 iff DONE_RE appeared in LOGFILE (work completed),
# regardless of how the process was reaped. LOGFILE must be FRESH per run so a
# stale footer can't cause a false-early completion.
#
#   skills_run_copilot_bounded LOGFILE DONE_RE ABS_MAX_SECS GRACE_SECS -- COPILOT_BIN ARGS...
skills_run_copilot_bounded() {
  local log="$1" done_re="$2" abs_max="$3" grace="$4"; shift 4
  [[ "${1:-}" == "--" ]] && shift
  # Monitor mode so the backgrounded job leads its own process group (pgid==pid),
  # enabling a whole-tree kill via the negative pid. stdin from /dev/null so a
  # stray read can never block the run.
  set -m 2>/dev/null || true
  "$@" </dev/null >>"$log" 2>&1 &
  local cpid=$! waited=0 done_at=-1
  set +m 2>/dev/null || true
  while kill -0 "$cpid" 2>/dev/null; do
    if (( done_at < 0 )) && grep -qE "$done_re" "$log" 2>/dev/null; then
      done_at=$waited
    fi
    if (( (done_at >= 0 && waited - done_at >= grace) || waited >= abs_max )); then
      kill -TERM "-$cpid" 2>/dev/null || kill -TERM "$cpid" 2>/dev/null
      sleep 5
      kill -KILL "-$cpid" 2>/dev/null || kill -KILL "$cpid" 2>/dev/null
      break
    fi
    sleep 3; waited=$((waited+3))
  done
  wait "$cpid" 2>/dev/null || true
  grep -qE "$done_re" "$log" 2>/dev/null
}
