#!/usr/bin/env sh
# Compatibility wrapper: the portable implementation is
# resume-after-compact.mjs. This wrapper only locates Node, forwards every
# argument, and returns the Node exit status.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NODE_BIN="${SELF_COMPACT_NODE_BIN:-$(command -v node || true)}"
[ -n "$NODE_BIN" ] || {
  echo "resume-after-compact.sh: node is unavailable; compact not verified" >&2
  exit 1
}

exec "$NODE_BIN" "$SCRIPT_DIR/resume-after-compact.mjs" "$@"
