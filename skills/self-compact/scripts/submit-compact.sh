#!/usr/bin/env sh
# Compatibility wrapper: the portable implementation is submit-compact.mjs.
# This wrapper only locates Node, forwards every argument, and returns the
# Node exit status.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NODE_BIN="${SELF_COMPACT_NODE_BIN:-$(command -v node || true)}"
[ -n "$NODE_BIN" ] || {
  echo "submit-compact.sh: node is unavailable; compact not submitted" >&2
  exit 1
}

exec "$NODE_BIN" "$SCRIPT_DIR/submit-compact.mjs" "$@"
