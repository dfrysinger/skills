#!/usr/bin/env bash
# check-subdir.sh — validate a supporting-file path before /skill-manage writes it.
#
# Enforces all three write-file preconditions in one call: the destination is an
# allowed subdir, the path stays inside the skill directory (no `..` traversal,
# no symlink escape), and an existing file is within the size cap.
#
# Usage:
#   check-subdir.sh <skill-dir> <relative-path>
# Exits 0 and prints the resolved absolute path when the destination is legal.

set -euo pipefail

MAX_BYTES=$((1024 * 1024))
ALLOWED=(references templates scripts assets)

if [[ $# -ne 2 ]]; then
  echo "usage: $(basename "$0") <skill-dir> <relative-path>" >&2
  exit 2
fi

SKILL_DIR="$1"
REL="$2"

if [[ ! -d "$SKILL_DIR" ]]; then
  echo "REFUSED: skill dir does not exist: $SKILL_DIR" >&2
  exit 1
fi
SKILL_ABS="$(cd "$SKILL_DIR" && pwd -P)"

if [[ "$REL" = /* ]]; then
  echo "REFUSED: path must be relative to the skill dir: $REL" >&2
  exit 1
fi

# Reject `..` lexically. Resolving the path cannot catch it on its own: when the
# traversal sits in a segment that does not exist yet, there is nothing on disk
# to resolve and the escape goes unnoticed.
IFS='/' read -r -a PARTS <<< "$REL"
for part in "${PARTS[@]}"; do
  if [[ "$part" == ".." ]]; then
    echo "REFUSED: '$REL' contains a '..' traversal" >&2
    exit 1
  fi
done

SUBDIR="${REL%%/*}"
if [[ "$SUBDIR" == "$REL" ]]; then
  echo "REFUSED: '$REL' sits at the skill root; supporting files go under one of: ${ALLOWED[*]}" >&2
  exit 1
fi

ok=0
for a in "${ALLOWED[@]}"; do
  [[ "$SUBDIR" == "$a" ]] && ok=1
done
if [[ "$ok" -ne 1 ]]; then
  echo "REFUSED: '$SUBDIR/' is not an allowed subdir; use one of: ${ALLOWED[*]}" >&2
  exit 1
fi

# Resolve against the deepest existing ancestor so a not-yet-created file is
# still checked for traversal and symlink escape.
DEST="$SKILL_ABS/$REL"
PARENT="$(dirname "$DEST")"
probe="$PARENT"
while [[ ! -d "$probe" && "$probe" != "/" ]]; do
  probe="$(dirname "$probe")"
done
PROBE_ABS="$(cd "$probe" && pwd -P)"
if [[ "$PROBE_ABS" != "$SKILL_ABS" && "$PROBE_ABS" != "$SKILL_ABS"/* ]]; then
  echo "REFUSED: '$REL' resolves outside the skill dir ($PROBE_ABS)" >&2
  exit 1
fi

if [[ -e "$DEST" ]]; then
  if [[ -L "$DEST" ]]; then
    echo "REFUSED: '$REL' is a symlink" >&2
    exit 1
  fi
  SIZE=$(wc -c < "$DEST" | tr -d ' ')
  if [[ "$SIZE" -gt "$MAX_BYTES" ]]; then
    echo "REFUSED: '$REL' is ${SIZE} bytes, over the 1 MiB cap" >&2
    exit 1
  fi
fi

echo "$DEST"
