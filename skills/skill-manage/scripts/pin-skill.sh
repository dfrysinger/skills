#!/usr/bin/env bash
# pin-skill.sh — touch a .pinned marker in a skill directory so the curator
# never auto-archives it. Use --unpin to reverse.
#
# Mirrors Hermes Agent's pin semantics: pin guards deletion/archive only;
# patch/edit/write-file remain allowed (the user explicitly chose to preserve
# the skill, not to freeze it).
#
# Usage:
#   pin-skill.sh <name>
#   pin-skill.sh <name> --unpin

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $(basename "$0") <name> [--unpin]" >&2
  exit 2
fi

NAME="$1"
ACTION="${2:-pin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR=$("$SCRIPT_DIR/find-skill.sh" "$NAME") || exit 1
MARKER="$SKILL_DIR/.pinned"

case "$ACTION" in
  pin)
    if [[ -f "$MARKER" ]]; then
      echo "already pinned: $MARKER"
      exit 0
    fi
    printf 'pinned-at: %s\nreason: pinned by user via /skill-manage pin\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MARKER"
    echo "pinned: $MARKER"
    ;;
  --unpin)
    if [[ ! -f "$MARKER" ]]; then
      echo "not pinned: $MARKER absent"
      exit 0
    fi
    rm "$MARKER"
    echo "unpinned: $MARKER removed"
    ;;
  *)
    echo "unknown action: $ACTION (use --unpin to unpin)" >&2
    exit 2
    ;;
esac
