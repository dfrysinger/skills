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
  display-message)
    last=""
    for argument in "$@"; do
      last="$argument"
    done
    case "$last" in
      '#{pane_current_path}') printf '%s\n' "$FAKE_PANE_CWD" ;;
      '#{pane_pid}') printf '%s\n' "$FAKE_PANE_PID" ;;
      *) echo "unexpected display format: $last" >&2; exit 1 ;;
    esac
    ;;
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
      if [ -n "$input" ]; then
        printf '%s\n' "$input" >> "$FAKE_TMUX_QUEUE"
        : > "$FAKE_TMUX_INPUT"
        case "$input" in
          /compact\ *)
            (
              sleep 0.3
              marker="$(printf '%s' "$input" | grep -o 'SELF_COMPACT_RUN_ID:[^ .]*')"
              sed 's/^summary_count: .*/summary_count: 2/' \
                "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.tmp"
              mv "$FAKE_WORKSPACE.tmp" "$FAKE_WORKSPACE"
              mkdir -p "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints"
              printf '%s\n' "$marker" > \
                "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/001-test.md"
            ) &
            ;;
        esac
      fi
    elif [ "$literal" = true ]; then
      printf '%s' "$last" > "$FAKE_TMUX_INPUT"
    else
      echo "unexpected send-keys call: $*" >&2
      exit 1
    fi
    ;;
  run-shell)
    last=""
    for argument in "$@"; do
      last="$argument"
    done
    /bin/bash -c "$last" &
    ;;
  *)
    echo "unexpected tmux command: $command" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$TMP_DIR/tmux"

cat > "$TMP_DIR/ps" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

pid=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-p" ]; then
    pid="$2"
    break
  fi
  shift
done

case "$pid" in
  200|201) echo 100 ;;
  100) echo 1 ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$TMP_DIR/ps"

session="$TMP_DIR/session-state/test-session"
mkdir -p "$session/files"
cat > "$session/workspace.yaml" <<EOF
id: test-session
cwd: $TMP_DIR/workspace
summary_count: 1
updated_at: 2026-08-04T00:00:00Z
EOF
: > "$session/events.jsonl"
: > "$session/inuse.200.lock"
: > "$session/inuse.201.lock"
: > "$TMP_DIR/input"
: > "$TMP_DIR/queue"

output="$(
  PATH="$TMP_DIR:$PATH" \
    TMUX_PANE="%1" \
    FAKE_PANE_CWD="$TMP_DIR/workspace" \
    FAKE_PANE_PID="100" \
    FAKE_TMUX_INPUT="$TMP_DIR/input" \
    FAKE_TMUX_QUEUE="$TMP_DIR/queue" \
    FAKE_WORKSPACE="$session/workspace.yaml" \
    SELF_COMPACT_SESSION_STATE_DIR="$TMP_DIR/session-state" \
    SELF_COMPACT_POLL_SECONDS=0.1 \
    SELF_COMPACT_MAX_POLLS=100 \
    "$SCRIPT_DIR/submit-compact.sh" \
    "Keep: active baton. Drop: resolved detail."
)"

case "$output" in
  *"submitted compact; post-compact continuation watcher armed"*) ;;
  *)
    echo "unexpected helper output: $output" >&2
    exit 1
    ;;
esac

for _ in $(seq 1 100); do
  [ "$(wc -l < "$TMP_DIR/queue" | tr -d ' ')" -ge 2 ] && break
  sleep 0.1
done

expected="$TMP_DIR/expected"
printf '%s\n' \
  "$(head -1 "$TMP_DIR/queue")" \
  "proceed" > "$expected"
cmp "$expected" "$TMP_DIR/queue"

log="$(find "$session/files" -type f -name 'self-compact-*.log' -print -quit)"
for _ in $(seq 1 50); do
  grep -q 'submitted post-compact continuation after summary_count advanced to 2' "$log" &&
    break
  sleep 0.1
done
grep -q 'submitted post-compact continuation after summary_count advanced to 2' "$log"

echo "submit-compact test passed"
