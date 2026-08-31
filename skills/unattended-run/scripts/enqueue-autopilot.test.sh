#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/enqueue-autopilot.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/unattended-run-wrapper-test.XXXXXX")"
trap '/bin/rm -rf -- "$ROOT"' EXIT

mkdir -p "$ROOT/bin"
cat >"$ROOT/bin/node" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$MOCK_ARGS"
exit "$MOCK_EXIT_CODE"
EOF
chmod +x "$ROOT/bin/node"

bash -n "$SCRIPT"
set +e
PATH="$ROOT/bin:$PATH" MOCK_ARGS="$ROOT/args" MOCK_EXIT_CODE=37 \
  "$SCRIPT" --target-session "session with spaces" "objective path.txt"
status=$?
set -e

[[ "$status" -eq 37 ]]
mapfile -t args <"$ROOT/args"
[[ "${#args[@]}" -eq 4 ]]
[[ "${args[0]}" == "$SCRIPT_DIR/enqueue-autopilot.mjs" ]]
[[ "${args[1]}" == "--target-session" ]]
[[ "${args[2]}" == "session with spaces" ]]
[[ "${args[3]}" == "objective path.txt" ]]

echo "unattended-run enqueue wrapper parity: pass"
