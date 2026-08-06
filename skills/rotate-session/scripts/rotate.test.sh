#!/usr/bin/env bash

set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rotate.sh"
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/rotate-session-test.XXXXXX")
trap '/bin/rm -rf -- "$ROOT"' EXIT

mkdir -p "$ROOT/bin" "$ROOT/home/.copilot/session-state"

cat >"$ROOT/bin/seq" <<'EOF'
#!/usr/bin/env bash
echo 1
EOF

cat >"$ROOT/bin/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat >"$ROOT/bin/rm" <<'EOF'
#!/usr/bin/env bash
if [ "${FAIL_RECOVERY_RM:-0}" = 1 ]; then
  case "${@: -1}" in
    */copilot-rotate-recovery-*) exit 1 ;;
  esac
fi
exec /bin/rm "$@"
EOF

cat >"$ROOT/bin/tmux" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  capture-pane)
    printf '%s\n' '────────'
    if [ "${MOCK_MODE:-success}" = success ]; then
      printf '❯ %s\n' "$(cat "$MOCK_INPUT" 2>/dev/null || true)"
    else
      printf '❯ \n'
    fi
    printf '%s\n' '────────'
    ;;
  send-keys)
    if [ "${*: -2:1}" = -- ]; then
      printf '%s' "${@: -1}" >"$MOCK_INPUT"
    elif [ "${@: -1}" = Enter ]; then
      : >"$MOCK_INPUT"
      if [ "${MOCK_MODE:-success}" = success ]; then
        mkdir -p "$HOME/.copilot/session-state/$MOCK_NEW"
        printf 'cwd: %s\n' "$PWD" >"$HOME/.copilot/session-state/$MOCK_NEW/workspace.yaml"
        printf '{}\n' >"$HOME/.copilot/session-state/$MOCK_NEW/events.jsonl"
      fi
    fi
    ;;
  *)
    exit 2
    ;;
esac
EOF

chmod +x "$ROOT/bin/"*

wait_for_result() {
  local log="$1"
  local _
  for _ in $(/usr/bin/seq 1 200); do
    grep -q 'RESULT:' "$log" 2>/dev/null && return 0
    /bin/sleep 0.02
  done
  return 1
}

start_case() {
  local old="$1"
  local mode="$2"
  local label="$3"
  local prompt="$4"
  local consume="${5:-yes}"
  local fail_recovery_rm="${6:-0}"
  local state="$ROOT/home/.copilot/session-state/$old"
  local input log io new

  mkdir -p "$state"
  printf 'cwd: %s\n' "$ROOT" >"$state/workspace.yaml"
  input=$(mktemp "$ROOT/copilot-rotate-input-$old.XXXXXX")
  printf '%s' "$prompt" >"$input"
  log="$ROOT/$label.log"
  io="$ROOT/$label.input"
  new="new-$old"

  args=("$old" "$input")
  [ "$consume" = yes ] && args+=(--consume-prompt)

  (
    cd "$ROOT"
    HOME="$ROOT/home" \
      TMPDIR="$ROOT/" \
      PATH="$ROOT/bin:$PATH" \
      TMUX_PANE=%1 \
      ROTATE_LOG="$log" \
      MOCK_MODE="$mode" \
      MOCK_INPUT="$io" \
      MOCK_NEW="$new" \
      FAIL_RECOVERY_RM="$fail_recovery_rm" \
      "$SCRIPT" "${args[@]}" >/dev/null
  )

  if [ "$consume" = yes ]; then
    [ ! -e "$input" ]
  else
    [ -e "$input" ]
  fi

  printf '%s\t%s\n' "$log" "$input"
}

bash -n "$SCRIPT"

IFS=$'\t' read -r success_log _ < <(
  start_case old-success success success 'continue retired session old-success'
)
wait_for_result "$success_log"
grep -q 'recovery snapshot:' "$success_log"
grep -q 'seeded$' "$success_log"
! find "$ROOT" -maxdepth 1 -name 'copilot-rotate-recovery-old-success.*' | grep -q .

IFS=$'\t' read -r fail_a_log _ < <(
  start_case old-a fail-render fail-a 'continue retired session old-a with alpha baton'
)
IFS=$'\t' read -r fail_b_log _ < <(
  start_case old-b fail-render fail-b 'continue retired session old-b with beta baton'
)
wait_for_result "$fail_a_log"
wait_for_result "$fail_b_log"
recovery_a=$(sed -n 's/.*prompt preserved at //p' "$fail_a_log" | tail -1)
recovery_b=$(sed -n 's/.*prompt preserved at //p' "$fail_b_log" | tail -1)
[ -f "$recovery_a" ] && [ -f "$recovery_b" ] && [ "$recovery_a" != "$recovery_b" ]
grep -q 'old-a with alpha baton' "$recovery_a"
! grep -q 'old-b with beta baton' "$recovery_a"
grep -q 'old-b with beta baton' "$recovery_b"
! grep -q 'old-a with alpha baton' "$recovery_b"
[ "$(stat -f '%Lp' "$recovery_a")" = 600 ]

IFS=$'\t' read -r generic_log generic_input < <(
  start_case old-generic fail-render generic 'continue retired session old-generic' no
)
wait_for_result "$generic_log"
[ -f "$generic_input" ]

IFS=$'\t' read -r cleanup_log _ < <(
  start_case old-cleanup success cleanup 'continue retired session old-cleanup' no 1
)
wait_for_result "$cleanup_log"
grep -q 'recovery cleanup failed; prompt preserved at ' "$cleanup_log"
cleanup_recovery=$(sed -n 's/.*prompt preserved at //p' "$cleanup_log" | tail -1)
[ -f "$cleanup_recovery" ]

invalid="$ROOT/copilot-rotate-input-old-invalid.test"
mkdir -p "$ROOT/home/.copilot/session-state/old-invalid"
printf 'wrong session' >"$invalid"
if HOME="$ROOT/home" TMPDIR="$ROOT/" TMUX_PANE=%1 \
  "$SCRIPT" old-invalid "$invalid" --consume-prompt >"$ROOT/invalid.out" 2>&1; then
  exit 1
fi
grep -q 'prompt does not name expected session old-invalid' "$ROOT/invalid.out"
[ -f "$invalid" ]
! find "$ROOT" -maxdepth 1 -name 'copilot-rotate-recovery-old-invalid.*' | grep -q .

echo "rotate-session tests: pass"
