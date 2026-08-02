#!/usr/bin/env bash
# CLI for the shared process/session writer lock.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd="${1:-}"
shift || true
case "$cmd" in
  acquire)
    mode=""
    owner=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --mode) mode="$2"; shift 2 ;;
        --owner) owner="$2"; shift 2 ;;
        *) echo "daemon-lock.sh acquire: unknown argument '$1'" >&2; exit 2 ;;
      esac
    done
    [[ -n "$mode" && -n "$owner" ]] || {
      echo "usage: daemon-lock.sh acquire --mode session --owner <name>" >&2
      exit 2
    }
    [[ "$mode" == "session" ]] || {
      echo "daemon-lock.sh: CLI acquisition supports session leases only" >&2
      exit 2
    }
    "$SCRIPT_DIR/daemon-lock.py" acquire --mode "$mode" --owner "$owner"
    ;;
  assert)
    [[ $# -eq 1 ]] || { echo "usage: daemon-lock.sh assert <token>" >&2; exit 2; }
    "$SCRIPT_DIR/daemon-lock.py" assert "$1"
    ;;
  renew)
    [[ $# -eq 1 ]] || { echo "usage: daemon-lock.sh renew <token>" >&2; exit 2; }
    "$SCRIPT_DIR/daemon-lock.py" renew "$1"
    ;;
  release)
    [[ $# -eq 1 ]] || { echo "usage: daemon-lock.sh release <token>" >&2; exit 2; }
    "$SCRIPT_DIR/daemon-lock.py" release "$1"
    ;;
  *)
    echo "usage: daemon-lock.sh {acquire|assert|renew|release}" >&2
    exit 2
    ;;
esac
