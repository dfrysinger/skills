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
      "────────8444 ────────" \
      "❯ $input" \
      "──" \
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

    if [ "$last" = "C-s" ]; then
      input="$(cat "$FAKE_TMUX_INPUT")"
      if [ -n "$input" ]; then
        printf '%s' "$input" > "$FAKE_TMUX_STASH"
        : > "$FAKE_TMUX_INPUT"
      fi
    elif [ "$last" = "C-u" ]; then
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
              printf '%s\n' \
                '{"type":"session.compaction_complete","timestamp":"2026-08-04T00:00:01Z"}' \
                >> "${FAKE_WORKSPACE%/workspace.yaml}/events.jsonl"
            ) &
            ;;
          proceed)
            printf '%s\n' \
              '{"type":"user.message","data":{"content":"proceed"},"timestamp":"2026-08-04T00:00:02Z"}' \
              >> "${FAKE_WORKSPACE%/workspace.yaml}/events.jsonl"
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
    if [ -n "${FAKE_TMUX_RUN_SHELL_COMMAND:-}" ]; then
      printf '%s\n' "$last" > "$FAKE_TMUX_RUN_SHELL_COMMAND"
    fi
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
: > "$TMP_DIR/queue"

printf '%s' "already queued" > "$TMP_DIR/input"
: > "$TMP_DIR/stash"
output="$(
  PATH="$TMP_DIR:$PATH" \
    TMUX_PANE="%1" \
    FAKE_PANE_CWD="$TMP_DIR/workspace" \
    FAKE_PANE_PID="100" \
    FAKE_TMUX_INPUT="$TMP_DIR/input" \
    FAKE_TMUX_QUEUE="$TMP_DIR/queue" \
    FAKE_TMUX_STASH="$TMP_DIR/stash" \
    FAKE_TMUX_RUN_SHELL_COMMAND="$TMP_DIR/run-shell-command" \
    FAKE_WORKSPACE="$session/workspace.yaml" \
    SELF_COMPACT_SESSION_STATE_DIR="$TMP_DIR/session-state" \
    SELF_COMPACT_POLL_SECONDS=0.1 \
    SELF_COMPACT_MAX_POLLS=100 \
    SELF_COMPACT_RESUME_GRACE_SECONDS=0.1 \
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

grep -qF 'already queued' "$TMP_DIR/stash"
grep -qF '|| true' "$TMP_DIR/run-shell-command"

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
grep -q 'submitted post-compact continuation after event line 1' "$log"

auto="$TMP_DIR/session-state/auto-session"
mkdir -p "$auto/checkpoints" "$auto/files"
cat > "$auto/workspace.yaml" <<EOF
id: auto-session
cwd: $TMP_DIR/workspace
summary_count: 1
EOF
: > "$auto/events.jsonl"
: > "$auto/ready"
: > "$auto/armed"

(
  sleep 0.2
  sed 's/^summary_count: .*/summary_count: 2/' \
    "$auto/workspace.yaml" > "$auto/workspace.yaml.tmp"
  mv "$auto/workspace.yaml.tmp" "$auto/workspace.yaml"
  printf '%s\n' 'SELF_COMPACT_RUN_ID:auto-test' > "$auto/checkpoints/001-test.md"
  printf '%s\n' \
    '{"type":"session.compaction_complete","timestamp":"2026-08-04T00:00:01Z"}' \
    '{"type":"assistant.turn_start","timestamp":"2026-08-04T00:00:02Z"}' \
    >> "$auto/events.jsonl"
) &

auto_output="$(
  PATH="$TMP_DIR:$PATH" \
    FAKE_PANE_CWD="$TMP_DIR/workspace" \
    FAKE_PANE_PID="100" \
    FAKE_TMUX_INPUT="$TMP_DIR/input" \
    FAKE_TMUX_QUEUE="$TMP_DIR/auto-queue" \
    FAKE_TMUX_STASH="$TMP_DIR/auto-stash" \
    FAKE_WORKSPACE="$auto/workspace.yaml" \
    SELF_COMPACT_POLL_SECONDS=0.1 \
    SELF_COMPACT_MAX_POLLS=100 \
    SELF_COMPACT_RESUME_GRACE_SECONDS=0.1 \
    "$SCRIPT_DIR/resume-after-compact.sh" \
    "%1" "$auto/workspace.yaml" 1 0 "$auto/ready" "$auto/armed" \
    "$auto/cancelled" "SELF_COMPACT_RUN_ID:auto-test" "proceed"
)"

case "$auto_output" in
  *"post-compact activity already present"*) ;;
  *)
    echo "watcher did not recognize automatic continuation: $auto_output" >&2
    exit 1
    ;;
esac
[ ! -s "$TMP_DIR/auto-queue" ]

queued="$TMP_DIR/session-state/queued-session"
mkdir -p "$queued/checkpoints" "$queued/files"
cat > "$queued/workspace.yaml" <<EOF
id: queued-session
cwd: $TMP_DIR/workspace
summary_count: 2
EOF
printf '%s\n' \
  '{"type":"session.compaction_complete","timestamp":"2026-08-04T00:00:01Z"}' \
  > "$queued/events.jsonl"
printf '%s\n' 'SELF_COMPACT_RUN_ID:queued-test' > "$queued/checkpoints/001-test.md"
: > "$queued/ready"
: > "$queued/armed"
printf '%s' "automatic continuation" > "$TMP_DIR/input"
: > "$TMP_DIR/queued-stash"

queued_output="$(
  PATH="$TMP_DIR:$PATH" \
    FAKE_PANE_CWD="$TMP_DIR/workspace" \
    FAKE_PANE_PID="100" \
    FAKE_TMUX_INPUT="$TMP_DIR/input" \
    FAKE_TMUX_QUEUE="$TMP_DIR/queued-queue" \
    FAKE_TMUX_STASH="$TMP_DIR/queued-stash" \
    FAKE_WORKSPACE="$queued/workspace.yaml" \
    SELF_COMPACT_POLL_SECONDS=0.1 \
    SELF_COMPACT_MAX_POLLS=100 \
    SELF_COMPACT_RESUME_GRACE_SECONDS=0.1 \
    "$SCRIPT_DIR/resume-after-compact.sh" \
    "%1" "$queued/workspace.yaml" 1 0 "$queued/ready" "$queued/armed" \
    "$queued/cancelled" "SELF_COMPACT_RUN_ID:queued-test" "proceed"
)"

case "$queued_output" in
  *"submitted post-compact continuation"*) ;;
  *)
    echo "watcher did not resume after stashing queued input: $queued_output" >&2
    exit 1
    ;;
esac
grep -qF "automatic continuation" "$TMP_DIR/queued-stash"
grep -qFx "proceed" "$TMP_DIR/queued-queue"

echo "submit-compact test passed"
