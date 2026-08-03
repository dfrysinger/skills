#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/tmux" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

command="$1"
shift

case "$command" in
  capture-pane)
    input="$(cat "$FAKE_TMUX_INPUT")"
    printf '%s\n' \
      "header" \
      "────────────────" \
      "❯ $input" \
      "────────────────" \
      "footer"
    ;;
  send-keys)
    last=""
    literal=false
    for argument in "$@"; do
      [ "$argument" = "-l" ] && literal=true
      last="$argument"
    done

    if [ "$last" = "C-u" ]; then
      : > "$FAKE_TMUX_INPUT"
    elif [ "$last" = "Enter" ]; then
      input="$(cat "$FAKE_TMUX_INPUT")"
      [ -n "$input" ] && printf '%s\n' "$input" >> "$FAKE_TMUX_QUEUE"
      : > "$FAKE_TMUX_INPUT"
    elif [ "$literal" = true ]; then
      if [ "${FAKE_TMUX_REJECT_CONTINUATION:-false}" = true ] &&
        [ "$last" = "proceed" ]; then
        exit 1
      fi
      printf '%s' "$last" > "$FAKE_TMUX_INPUT"
    else
      echo "unexpected send-keys call: $*" >&2
      exit 1
    fi
    ;;
  *)
    echo "unexpected tmux command: $command" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$TMP_DIR/tmux"

: > "$TMP_DIR/input"
: > "$TMP_DIR/queue"

output="$(
  PATH="$TMP_DIR:$PATH" \
    TMUX_PANE="%1" \
    FAKE_TMUX_INPUT="$TMP_DIR/input" \
    FAKE_TMUX_QUEUE="$TMP_DIR/queue" \
    "$SCRIPT_DIR/submit-compact.sh" \
    "Keep: active baton. Drop: resolved detail."
)"

[ "$output" = "submitted compact and continuation" ]

expected="$TMP_DIR/expected"
printf '%s\n' \
  "/compact Keep: active baton. Drop: resolved detail." \
  "proceed" > "$expected"
cmp "$expected" "$TMP_DIR/queue"

set +e
error="$(
  PATH="$TMP_DIR:$PATH" \
    TMUX_PANE="%1" \
    FAKE_TMUX_INPUT="$TMP_DIR/input" \
    FAKE_TMUX_QUEUE="$TMP_DIR/queue" \
    FAKE_TMUX_REJECT_CONTINUATION=true \
    "$SCRIPT_DIR/submit-compact.sh" \
    "Keep: active baton. Drop: resolved detail." 2>&1
)"
status=$?
set -e

[ "$status" -ne 0 ]
case "$error" in
  *"compact is already queued; do not rerun the helper; send 'proceed' manually."*) ;;
  *)
    echo "missing partial-submission recovery message: $error" >&2
    exit 1
    ;;
esac

echo "submit-compact test passed"
