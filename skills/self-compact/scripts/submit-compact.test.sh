#!/usr/bin/env sh
# Wrapper parity: the shell entry points must only locate Node, forward every
# argument, and return the Node exit status. The behavioral contract lives in
# submit-compact.test.mjs and runs on every platform.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK_DIR="$SCRIPT_DIR/.wrapper-parity.$$"
trap 'rm -rf "$WORK_DIR"' EXIT
mkdir -p "$WORK_DIR"

fail() {
  echo "submit-compact wrapper test: $*" >&2
  exit 1
}

cat > "$WORK_DIR/node" <<'EOF'
#!/usr/bin/env sh
printf '%s\n' "$@" > "$WRAPPER_CAPTURE"
exit 17
EOF
chmod +x "$WORK_DIR/node"

for wrapper in submit-compact resume-after-compact; do
  WRAPPER_CAPTURE="$WORK_DIR/$wrapper.args"
  export WRAPPER_CAPTURE
  status=0
  SELF_COMPACT_NODE_BIN="$WORK_DIR/node" \
    "$SCRIPT_DIR/$wrapper.sh" --tool-call-id "call one" second || status=$?
  [ "$status" -eq 17 ] ||
    fail "$wrapper.sh did not forward the Node exit status (got $status)"
  expected="$SCRIPT_DIR/$wrapper.mjs
--tool-call-id
call one
second"
  [ "$(cat "$WRAPPER_CAPTURE")" = "$expected" ] ||
    fail "$wrapper.sh did not forward its arguments verbatim"
done

mkdir -p "$WORK_DIR/empty"
status=0
env -u SELF_COMPACT_NODE_BIN PATH="$WORK_DIR/empty" \
  "$SCRIPT_DIR/submit-compact.sh" --tool-call-id x >/dev/null 2>&1 ||
  status=$?
[ "$status" -ne 0 ] || fail "submit-compact.sh succeeded without Node"

echo "submit-compact wrapper parity tests passed"
