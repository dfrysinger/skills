#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TEST_ROOT="$SCRIPT_DIR/.submit-compact-test.$$"
FAKE_BIN="$TEST_ROOT/bin"
FAKE_BACKGROUND_PIDS="$TEST_ROOT/background-pids"
REAL_TMUX_BIN="$(command -v tmux 2>/dev/null || true)"
REAL_TMUX_SOCKET=""
cleanup_test() {
  local pid
  if [ -n "$REAL_TMUX_SOCKET" ] && [ -n "$REAL_TMUX_BIN" ]; then
    "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" kill-server >/dev/null 2>&1 || true
    rm -f "$REAL_TMUX_SOCKET"
  fi
  if [ -r "$FAKE_BACKGROUND_PIDS" ]; then
    while IFS= read -r pid; do
      case "$pid" in
        ''|*[!0-9]*) continue ;;
      esac
      kill -0 "$pid" >/dev/null 2>&1 || continue
      kill "$pid" >/dev/null 2>&1 || true
    done < "$FAKE_BACKGROUND_PIDS"
  fi
  rm -rf "$TEST_ROOT"
}
trap cleanup_test EXIT
mkdir -p "$FAKE_BIN"
: > "$FAKE_BACKGROUND_PIDS"
export FAKE_BACKGROUND_PIDS

fail() {
  echo "submit-compact test: $*" >&2
  exit 1
}

assert_file_equals() {
  local expected="$1"
  local path="$2"
  [ "$(cat "$path")" = "$expected" ] ||
    fail "expected $path to contain [$expected], got [$(cat "$path")]"
}

assert_count() {
  local expected="$1"
  local pattern="$2"
  local path="$3"
  local actual
  actual="$(grep -cE "$pattern" "$path" 2>/dev/null || true)"
  [ "$actual" -eq "$expected" ] ||
    fail "expected $expected matches for [$pattern] in $path, got $actual"
}

assert_at_most() {
  local maximum="$1"
  local pattern="$2"
  local path="$3"
  local actual
  actual="$(grep -cE "$pattern" "$path" 2>/dev/null || true)"
  [ "$actual" -le "$maximum" ] ||
    fail "expected at most $maximum matches for [$pattern] in $path, got $actual"
}

wait_for_pattern() {
  local pattern="$1"
  local path="$2"
  for _ in $(seq 1 200); do
    grep -qE "$pattern" "$path" 2>/dev/null && return 0
    sleep 0.02
  done
  fail "timed out waiting for [$pattern] in $path"
}

prompt_hex() {
  (
    source "$SCRIPT_DIR/input-recovery.sh"
    sc_prompt_hex
  )
}

literal_hex() {
  (
    source "$SCRIPT_DIR/input-recovery.sh"
    sc_literal_hex "$1"
  )
}

prompt_matches() {
  local expected="$1"
  local rows_hex
  rows_hex="$(prompt_hex)" || return 1
  (
    source "$SCRIPT_DIR/input-recovery.sh"
    [ "$rows_hex" = "$(sc_literal_hex "$expected")" ]
  )
}

cat > "$FAKE_BIN/tmux" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

action() {
  printf '%s\n' "$*" >> "$FAKE_TMUX_ACTIONS"
}

append_event() {
  printf '%s\n' "$1" >> "${FAKE_WORKSPACE%/workspace.yaml}/events.jsonl"
}

increment_file() {
  local path="$1"
  local value=0
  [ -s "$path" ] && value="$(cat "$path")"
  value=$((value + 1))
  printf '%s' "$value" > "$path"
  printf '%s\n' "$value"
}

effective_window_size() {
  if [ -s "$FAKE_WINDOW_SIZE_CONFIGURED" ]; then
    cat "$FAKE_WINDOW_SIZE_CONFIGURED"
  else
    cat "$FAKE_WINDOW_SIZE_GLOBAL"
  fi
}

render_readable_input() {
  local input="$1"
  local columns="${FAKE_CAPTURE_SPLIT_COLUMNS:-}"
  local chunk limit padding="${FAKE_CAPTURE_RIGHT_PADDING:-}"
  local prefix="❯ " remaining="$input"

  if [ -n "${FAKE_CAPTURE_SPLIT_TYPE_COUNT:-}" ] &&
    [ "$(cat "$FAKE_TYPE_COUNT")" != "$FAKE_CAPTURE_SPLIT_TYPE_COUNT" ]; then
    columns=""
  fi

  if [ "${FAKE_CAPTURE_TRANSIENT_RIGHT_PADDING:-0}" = 1 ]; then
    capture_number="$(cat "$FAKE_CAPTURE_COUNT")"
    if [ $((capture_number % 2)) -eq 0 ]; then
      padding=""
    else
      padding="     "
    fi
  fi

  if [ -z "$columns" ]; then
    printf '%s\n' "❯ $input$padding"
  else
    case "$columns" in
      ''|*[!0-9]*) echo "invalid fake split columns: $columns" >&2; exit 1 ;;
    esac
    [ "$columns" -gt 4 ] || {
      echo "fake split columns too narrow: $columns" >&2
      exit 1
    }
    limit=$((columns - 2))
    while :; do
      chunk="${remaining:0:limit}"
      remaining="${remaining:limit}"
      if [[ "$remaining" == " "* ]]; then
        remaining="${remaining:1}"
      fi
      printf '%s%s%s\n' \
        "$prefix" "$chunk" "$padding"
      [ -n "$remaining" ] || break
      prefix="  "
    done
  fi

  if [ -s "$FAKE_CU_LINE_LOCAL_STATE" ]; then
    printf '  %s\n' "$padding"
  fi
}

command="${1:?tmux command is required}"
shift

case "$command" in
  display-message)
    last=""
    print_format=false
    for argument in "$@"; do
      [ "$argument" = "-p" ] && print_format=true
      last="$argument"
    done
    if [ "$print_format" = true ]; then
      case "$last" in
        '#{pane_current_path}') printf '%s\n' "$FAKE_PANE_CWD" ;;
        '#{pane_pid}') printf '%s\n' "$FAKE_PANE_PID" ;;
        '#{session_name}') printf '%s\n' "$FAKE_SESSION_NAME" ;;
        '#{pane_width}')
          read -r width _ < "$FAKE_GEOMETRY"
          printf '%s\n' "$width"
          ;;
        '#{cursor_x}|#{cursor_y}|#{pane_height}')
          input="$(cat "$FAKE_TMUX_INPUT")"
          if [ -s "$FAKE_CURSOR" ]; then
            printf '%s|40\n' "$(cat "$FAKE_CURSOR")"
          elif [ -s "$FAKE_CU_LINE_LOCAL_STATE" ]; then
            printf '2|11|40\n'
          elif [ -z "$input" ]; then
            printf '2|10|40\n'
          else
            printf '%s|10|40\n' "$((2 + ${#input}))"
          fi
          ;;
        '#{session_name}|#{window_index}|#{window_width}|#{window_height}|#{window_linked}')
          read -r width height < "$FAKE_GEOMETRY"
          printf '%s|0|%s|%s|%s\n' \
            "$FAKE_SESSION_NAME" "$width" "$height" "${FAKE_WINDOW_LINKED:-0}"
          ;;
        *) echo "unexpected display format: $last" >&2; exit 1 ;;
      esac
    else
      action "NOTICE:$last"
      if [ "${FAKE_ACTIVITY_ON_NOTICE:-0}" = 1 ]; then
        append_event '{"type":"user.message","content":"user won"}'
      fi
    fi
    ;;
  list-clients)
    printf 'client-a|%s\nclient-b|%s\nother-client|other-session\n' \
      "$FAKE_SESSION_NAME" "$FAKE_SESSION_NAME"
    ;;
  refresh-client)
    target=""
    while [ $# -gt 0 ]; do
      if [ "$1" = "-t" ]; then
        target="$2"
        shift 2
      else
        shift
      fi
    done
    action "REFRESH:$target"
    ;;
  show-options)
    if printf '%s\n' "$*" | grep -q -- ' -A '; then
      action "SHOW:effective:$(effective_window_size)"
      effective_window_size
    elif [ -s "$FAKE_WINDOW_SIZE_CONFIGURED" ]; then
      action "SHOW:configured:$(cat "$FAKE_WINDOW_SIZE_CONFIGURED")"
      cat "$FAKE_WINDOW_SIZE_CONFIGURED"
    else
      action "SHOW:configured:inherited"
    fi
    ;;
  set-option)
    unset_option=false
    value=""
    for argument in "$@"; do
      case "$argument" in
        -*u*) unset_option=true ;;
        latest|smallest|largest|manual) value="$argument" ;;
      esac
    done
    if [ "$unset_option" = true ]; then
      action "SET:window-size:inherited"
      : > "$FAKE_WINDOW_SIZE_CONFIGURED"
    else
      [ -n "$value" ] || {
        echo "missing window-size value" >&2
        exit 1
      }
      action "SET:window-size:$value"
      printf '%s' "$value" > "$FAKE_WINDOW_SIZE_CONFIGURED"
    fi
    ;;
  resize-window)
    width=""
    height=""
    target=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -x) width="$2"; shift 2 ;;
        -y) height="$2"; shift 2 ;;
        -t) target="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    action "RESIZE:$target:${width}x${height}"
    original_width="${FAKE_ORIGINAL_GEOMETRY%x*}"
    original_height="${FAKE_ORIGINAL_GEOMETRY#*x}"
    if [ "$width" = "$original_width" ] && [ "$height" = "$original_height" ] &&
      [ "${FAKE_FAIL_FIRST_RESTORE:-0}" = 1 ] &&
      [ ! -e "$FAKE_CASE/restore-failed" ]; then
      : > "$FAKE_CASE/restore-failed"
      exit 1
    fi
    printf '%s %s\n' "$width" "$height" > "$FAKE_GEOMETRY"
    printf '%s' manual > "$FAKE_WINDOW_SIZE_CONFIGURED"
    if [ "$width" -lt "$original_width" ] &&
      [ "${FAKE_REPAIR_ON_RESIZE:-0}" = 1 ]; then
      printf '%s' readable > "$FAKE_CAPTURE_MODE"
    fi
    ;;
  capture-pane)
    start_line=""
    end_line=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -S) start_line="$2"; shift 2 ;;
        -E) end_line="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    action "CAPTURE:${start_line}:${end_line}"
    increment_file "$FAKE_CAPTURE_COUNT" >/dev/null
    mode="$(cat "$FAKE_CAPTURE_MODE")"
    case "$mode" in
      unreadable)
        printf '%s\n' \
          "header" \
          "corrupt rendering overlay" \
          "footer"
        ;;
      unstable)
        capture_number="$(cat "$FAKE_CAPTURE_COUNT")"
        if [ $((capture_number % 2)) -eq 0 ]; then
          printf '%s\n' "header" "❯ unstable" "────────────────" "footer"
        else
          printf '%s\n' "header" "corrupt rendering overlay" "footer"
        fi
        ;;
      readable)
        input="$(cat "$FAKE_TMUX_INPUT")"
        if [ -s "$FAKE_RENDER_AFTER_CAPTURE" ]; then
          visible_after="$(cat "$FAKE_RENDER_AFTER_CAPTURE")"
          capture_number="$(cat "$FAKE_CAPTURE_COUNT")"
          if [ "$capture_number" -le "$visible_after" ]; then
            input=""
          elif [ -s "$FAKE_RENDER_OVERRIDE" ]; then
            input="$(cat "$FAKE_RENDER_OVERRIDE")"
          fi
        fi
        footer="footer"
        [ -s "$FAKE_TMUX_STASH" ] && footer="footer stashed"
        printf '%s\n' "header"
        [ -s "$FAKE_TRANSCRIPT" ] && cat "$FAKE_TRANSCRIPT"
        render_readable_input "$input"
        printf '%s\n' "──" "────────────────" "$footer"
        if [ "$(cat "$FAKE_MENU")" = 1 ]; then
          printf '%s\n' \
            "  ↑/↓ navigate · Enter select" \
            "  Esc close"
        fi
        true
        ;;
      *)
        echo "unexpected capture mode: $mode" >&2
        exit 1
        ;;
    esac
    ;;
  send-keys)
    last=""
    literal=false
    for argument in "$@"; do
      [ "$argument" = "-l" ] && literal=true
      last="$argument"
    done
    case "$last" in
      C-s)
        action "KEY:C-s"
        if [ "${FAKE_CS_NOOP:-0}" != 1 ]; then
          input="$(cat "$FAKE_TMUX_INPUT")"
          if [ -n "$input" ]; then
            printf '%s' "$input" > "$FAKE_TMUX_STASH"
            : > "$FAKE_TMUX_INPUT"
          elif [ -s "$FAKE_TMUX_STASH" ]; then
            cat "$FAKE_TMUX_STASH" > "$FAKE_TMUX_INPUT"
            : > "$FAKE_TMUX_STASH"
          fi
        fi
        ;;
      C-u)
        count="$(increment_file "$FAKE_CU_COUNT")"
        action "KEY:C-u:$count"
        : > "$FAKE_RENDER_AFTER_CAPTURE"
        : > "$FAKE_RENDER_OVERRIDE"
        input="$(cat "$FAKE_TMUX_INPUT")"
        if [ "${FAKE_CU_LINE_LOCAL:-0}" = 1 ]; then
          if [ -s "$FAKE_CU_LINE_LOCAL_STATE" ]; then
            :
          elif [[ "$input" == *$'\n'* ]]; then
            printf '%s' "${input%$'\n'*}" > "$FAKE_TMUX_INPUT"
            printf '%s' 1 > "$FAKE_CU_LINE_LOCAL_STATE"
          else
            : > "$FAKE_TMUX_INPUT"
          fi
        else
          : > "$FAKE_TMUX_INPUT"
        fi
        if [ "${FAKE_REPAIR_ON_CU:-0}" -eq "$count" ] &&
          [ "${FAKE_REPAIR_ON_CU:-0}" -gt 0 ]; then
          printf '%s' readable > "$FAKE_CAPTURE_MODE"
        fi
        if [ "${FAKE_ACTIVITY_ON_CU:-0}" -eq "$count" ] &&
          [ "${FAKE_ACTIVITY_ON_CU:-0}" -gt 0 ]; then
          append_event '{"type":"assistant.turn_start"}'
          append_event '{"type":"assistant.turn_end"}'
        fi
        ;;
      Escape)
        count="$(increment_file "$FAKE_ESC_COUNT")"
        action "KEY:Escape:$count"
        if [ "${FAKE_REPAIR_ON_ESC:-0}" -eq "$count" ] &&
          [ "${FAKE_REPAIR_ON_ESC:-0}" -gt 0 ]; then
          printf '%s' readable > "$FAKE_CAPTURE_MODE"
        fi
        if [ "${FAKE_ESC_CLOSE_AFTER:-1}" -le "$count" ]; then
          printf '%s' 0 > "$FAKE_MENU"
        fi
        if [ "${FAKE_ACTIVITY_ON_ESC:-0}" -eq "$count" ] &&
          [ "${FAKE_ACTIVITY_ON_ESC:-0}" -gt 0 ]; then
          append_event '{"type":"assistant.turn_start"}'
          append_event '{"type":"assistant.turn_end"}'
        fi
        ;;
      Enter)
        input="$(cat "$FAKE_TMUX_INPUT")"
        action "KEY:Enter:$input"
        : > "$FAKE_RENDER_AFTER_CAPTURE"
        : > "$FAKE_RENDER_OVERRIDE"
        case "$input" in
          /compact\ *)
            printf '%s\n' "$input" >> "$FAKE_TMUX_QUEUE"
            marker="$(
              printf '%s' "$input" |
                grep -Eo 'SCM:[0-9a-f]{8}-[0-9a-f]{5}'
            )"
            case "${FAKE_COMPACT_MODE:-success}" in
              success)
                : > "$FAKE_TMUX_INPUT"
                (
                  sleep "${FAKE_TURN_END_DELAY:-0.02}"
                  append_event '{"type":"assistant.turn_end"}'
                  sleep "${FAKE_START_DELAY:-0.02}"
                  append_event '{"type":"session.compaction_start"}'
                  if [ -s "$FAKE_TMUX_STASH" ]; then
                    cat "$FAKE_TMUX_STASH" > "$FAKE_TMUX_INPUT"
                    : > "$FAKE_TMUX_STASH"
                  fi
                  [ -n "${FAKE_POST_COMPACT_MODE:-}" ] &&
                    printf '%s' "$FAKE_POST_COMPACT_MODE" > "$FAKE_CAPTURE_MODE"
                  sed 's/^summary_count: .*/summary_count: 2/' \
                    "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.next"
                  mv "$FAKE_WORKSPACE.next" "$FAKE_WORKSPACE"
                  mkdir -p "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints"
                  printf '%s\n' "$marker" > \
                    "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/001-test.md"
                  append_event '{"type":"session.compaction_complete","success":true}'
                ) &
                printf '%s\n' "$!" >> "$FAKE_BACKGROUND_PIDS"
                ;;
              start-before-end)
                : > "$FAKE_TMUX_INPUT"
                (
                  sleep 0.02
                  append_event '{"type":"session.compaction_start"}'
                  sleep 0.05
                  append_event '{"type":"assistant.turn_end"}'
                  sed 's/^summary_count: .*/summary_count: 2/' \
                    "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.next"
                  mv "$FAKE_WORKSPACE.next" "$FAKE_WORKSPACE"
                  mkdir -p "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints"
                  printf '%s\n' "$marker" > \
                    "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/001-test.md"
                  append_event '{"type":"session.compaction_complete","success":true}'
                ) &
                printf '%s\n' "$!" >> "$FAKE_BACKGROUND_PIDS"
                ;;
              no-start-keep)
                append_event '{"type":"assistant.turn_end"}'
                ;;
              no-start-new-draft)
                printf '%s' "new user draft" > "$FAKE_TMUX_INPUT"
                append_event '{"type":"assistant.turn_end"}'
                ;;
              no-start-unreadable)
                printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
                append_event '{"type":"assistant.turn_end"}'
                ;;
              failed)
                : > "$FAKE_TMUX_INPUT"
                append_event '{"type":"session.compaction_start"}'
                append_event \
                  '{"type":"session.compaction_complete","success":false,"error":"Nothing to compact"}'
                ;;
              *)
                echo "unexpected compact mode: $FAKE_COMPACT_MODE" >&2
                exit 1
                ;;
            esac
            ;;
          *)
            if [ -n "$input" ]; then
              printf '%s\n' "$input" >> "$FAKE_TMUX_QUEUE"
              : > "$FAKE_TMUX_INPUT"
              if [ "${FAKE_CONTINUATION_MODE:-success}" = success ]; then
                escaped="$(printf '%s' "$input" | sed 's/\\/\\\\/g; s/"/\\"/g')"
                append_event \
                  "{\"type\":\"user.message\",\"content\":\"$escaped\"}"
                if [ -s "$FAKE_TMUX_STASH" ]; then
                  cat "$FAKE_TMUX_STASH" > "$FAKE_TMUX_INPUT"
                  : > "$FAKE_TMUX_STASH"
                fi
              fi
            fi
            ;;
        esac
        ;;
      *)
        if [ "$literal" = true ]; then
          count="$(increment_file "$FAKE_TYPE_COUNT")"
          action "TYPE:$last"
          current="$(cat "$FAKE_TMUX_INPUT")"
          if [ -s "$FAKE_CU_LINE_LOCAL_STATE" ]; then
            printf '%s\n%s' "$current" "$last" > "$FAKE_TMUX_INPUT"
            : > "$FAKE_CU_LINE_LOCAL_STATE"
          else
            printf '%s%s' "$current" "$last" > "$FAKE_TMUX_INPUT"
          fi
          if [ -n "${FAKE_APPEND_ON_TYPE:-}" ] &&
            { [ -z "${FAKE_APPEND_ON_TYPE_COUNT:-}" ] ||
              [ "${FAKE_APPEND_ON_TYPE_COUNT}" -eq "$count" ]; } &&
            [ "$last" = "${FAKE_APPEND_ON_TYPE_COMMAND:-$last}" ]; then
            printf '%s' "$FAKE_APPEND_ON_TYPE" >> "$FAKE_TMUX_INPUT"
          fi
          if [ "${FAKE_MENU_ON_TYPE_COUNT:-0}" -eq "$count" ]; then
            printf '%s' 1 > "$FAKE_MENU"
          fi
          if [ -n "${FAKE_ACTIVITY_ON_TYPE:-}" ] &&
            [ "$last" = "$FAKE_ACTIVITY_ON_TYPE" ]; then
            append_event '{"type":"assistant.turn_start"}'
            append_event '{"type":"assistant.turn_end"}'
          fi
          if [ "${FAKE_RENDER_DELAY_TYPE_COUNT:-0}" = all ] ||
            [ "${FAKE_RENDER_DELAY_TYPE_COUNT:-0}" -eq "$count" ]; then
            case "${FAKE_RENDER_DELAY_CAPTURES:-0}" in
              ''|*[!0-9]*)
                echo "invalid fake render delay captures" >&2
                exit 1
                ;;
            esac
            current_capture="$(cat "$FAKE_CAPTURE_COUNT")"
            printf '%s' \
              "$((current_capture + FAKE_RENDER_DELAY_CAPTURES))" \
              > "$FAKE_RENDER_AFTER_CAPTURE"
            printf '%s' "${FAKE_RENDER_WRONG_VALUE:-}" \
              > "$FAKE_RENDER_OVERRIDE"
          fi
        else
          echo "unexpected send-keys call: $*" >&2
          exit 1
        fi
        ;;
    esac
    ;;
  run-shell)
    last=""
    for argument in "$@"; do
      last="$argument"
    done
    printf '%s\n' "$last" > "$FAKE_RUN_SHELL_COMMAND"
    (
      unset LANG LC_ALL LC_CTYPE LC_COLLATE LC_MESSAGES LC_MONETARY
      unset LC_NUMERIC LC_TIME
      printf 'LANG=%s\nLC_ALL=%s\n' \
        "${LANG-unset}" "${LC_ALL-unset}" > "$FAKE_RUN_SHELL_ENV"
      exec /bin/bash -c "$last"
    ) &
    printf '%s\n' "$!" >> "$FAKE_BACKGROUND_PIDS"
    ;;
  *)
    echo "unexpected tmux command: $command" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$FAKE_BIN/tmux"

cat > "$FAKE_BIN/perl" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

if [ -n "${FAKE_EPOCH_MILLISECONDS_FILE:-}" ]; then
  call=0
  [ -s "$FAKE_EPOCH_CALL_COUNT" ] &&
    call="$(cat "$FAKE_EPOCH_CALL_COUNT")"
  call=$((call + 1))
  printf '%s' "$call" > "$FAKE_EPOCH_CALL_COUNT"
  value="$(sed -n "${call}p" "$FAKE_EPOCH_MILLISECONDS_FILE")"
  [ -n "$value" ] ||
    value="$(tail -1 "$FAKE_EPOCH_MILLISECONDS_FILE")"
  if [ "${FAKE_EPOCH_APPEND_EVENTS_AT_CALL:-0}" -eq "$call" ]; then
    printf '%s\n' \
      '{"type":"session.compaction_start"}' \
      '{"type":"session.compaction_complete","success":true}' \
      '{"type":"assistant.turn_start"}' >> "$FAKE_EPOCH_EVENTS"
  fi
  printf '%s\n' "$value"
  exit 0
fi

exec /usr/bin/perl "$@"
EOF
chmod +x "$FAKE_BIN/perl"

cat > "$FAKE_BIN/ps" <<'EOF'
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
chmod +x "$FAKE_BIN/ps"

setup_case() {
  local name="$1"
  FAKE_CASE="$TEST_ROOT/$name"
  mkdir -p "$FAKE_CASE/session/files" "$FAKE_CASE/workspace"
  FAKE_WORKSPACE="$FAKE_CASE/session/workspace.yaml"
  FAKE_TMUX_INPUT="$FAKE_CASE/input"
  FAKE_TMUX_STASH="$FAKE_CASE/stash"
  FAKE_TMUX_QUEUE="$FAKE_CASE/queue"
  FAKE_TMUX_ACTIONS="$FAKE_CASE/actions"
  FAKE_CAPTURE_MODE="$FAKE_CASE/capture-mode"
  FAKE_CAPTURE_COUNT="$FAKE_CASE/capture-count"
  FAKE_RENDER_AFTER_CAPTURE="$FAKE_CASE/render-after-capture"
  FAKE_RENDER_OVERRIDE="$FAKE_CASE/render-override"
  FAKE_CU_COUNT="$FAKE_CASE/cu-count"
  FAKE_CU_LINE_LOCAL_STATE="$FAKE_CASE/cu-line-local-state"
  FAKE_ESC_COUNT="$FAKE_CASE/esc-count"
  FAKE_TYPE_COUNT="$FAKE_CASE/type-count"
  FAKE_MENU="$FAKE_CASE/menu"
  FAKE_TRANSCRIPT="$FAKE_CASE/transcript"
  FAKE_CURSOR="$FAKE_CASE/cursor"
  FAKE_GEOMETRY="$FAKE_CASE/geometry"
  FAKE_WINDOW_SIZE_CONFIGURED="$FAKE_CASE/window-size-configured"
  FAKE_WINDOW_SIZE_GLOBAL="$FAKE_CASE/window-size-global"
  FAKE_RUN_SHELL_COMMAND="$FAKE_CASE/run-shell-command"
  FAKE_RUN_SHELL_ENV="$FAKE_CASE/run-shell-env"
  FAKE_EPOCH_CALL_COUNT="$FAKE_CASE/epoch-call-count"
  FAKE_PANE_CWD="$FAKE_CASE/workspace"
  FAKE_PANE_PID=100
  FAKE_SESSION_NAME="test-session"
  FAKE_ORIGINAL_GEOMETRY="120x40"

  cat > "$FAKE_WORKSPACE" <<EOF
id: $name
cwd: $FAKE_PANE_CWD
summary_count: 1
EOF
  : > "$FAKE_CASE/session/events.jsonl"
  : > "$FAKE_CASE/session/inuse.200.lock"
  : > "$FAKE_TMUX_INPUT"
  : > "$FAKE_TMUX_STASH"
  : > "$FAKE_TMUX_QUEUE"
  : > "$FAKE_TMUX_ACTIONS"
  : > "$FAKE_CAPTURE_COUNT"
  : > "$FAKE_RENDER_AFTER_CAPTURE"
  : > "$FAKE_RENDER_OVERRIDE"
  : > "$FAKE_CU_COUNT"
  : > "$FAKE_CU_LINE_LOCAL_STATE"
  : > "$FAKE_ESC_COUNT"
  : > "$FAKE_TYPE_COUNT"
  : > "$FAKE_EPOCH_CALL_COUNT"
  : > "$FAKE_CURSOR"
  : > "$FAKE_TRANSCRIPT"
  printf '%s' readable > "$FAKE_CAPTURE_MODE"
  printf '%s' 0 > "$FAKE_MENU"
  printf '%s\n' "120 40" > "$FAKE_GEOMETRY"
  : > "$FAKE_WINDOW_SIZE_CONFIGURED"
  printf '%s' latest > "$FAKE_WINDOW_SIZE_GLOBAL"

  unset FAKE_REPAIR_ON_RESIZE FAKE_FAIL_FIRST_RESTORE FAKE_REPAIR_ON_CU
  unset FAKE_CU_LINE_LOCAL FAKE_CS_NOOP FAKE_CAPTURE_RIGHT_PADDING
  unset FAKE_CAPTURE_SPLIT_COLUMNS FAKE_CAPTURE_SPLIT_TYPE_COUNT
  unset FAKE_CAPTURE_TRANSIENT_RIGHT_PADDING
  unset FAKE_REPAIR_ON_ESC FAKE_ESC_CLOSE_AFTER FAKE_ACTIVITY_ON_CU
  unset FAKE_ACTIVITY_ON_TYPE FAKE_COMPACT_MODE FAKE_CONTINUATION_MODE
  unset FAKE_TURN_END_DELAY FAKE_START_DELAY FAKE_POST_COMPACT_MODE
  unset FAKE_ACTIVITY_ON_ESC FAKE_APPEND_ON_TYPE FAKE_APPEND_ON_TYPE_COMMAND
  unset FAKE_APPEND_ON_TYPE_COUNT FAKE_MENU_ON_TYPE_COUNT
  unset FAKE_ACTIVITY_ON_NOTICE
  unset FAKE_RENDER_DELAY_TYPE_COUNT FAKE_RENDER_DELAY_CAPTURES
  unset FAKE_RENDER_WRONG_VALUE
  unset FAKE_WINDOW_LINKED FAKE_EPOCH_MILLISECONDS_FILE
  unset FAKE_EPOCH_APPEND_EVENTS_AT_CALL FAKE_EPOCH_EVENTS

  export PATH="$FAKE_BIN:$PATH"
  export FAKE_CASE FAKE_WORKSPACE FAKE_TMUX_INPUT FAKE_TMUX_STASH
  export FAKE_TMUX_QUEUE FAKE_TMUX_ACTIONS FAKE_CAPTURE_MODE
  export FAKE_CAPTURE_COUNT FAKE_RENDER_AFTER_CAPTURE FAKE_RENDER_OVERRIDE
  export FAKE_CU_COUNT FAKE_ESC_COUNT FAKE_TYPE_COUNT
  export FAKE_CU_LINE_LOCAL_STATE
  export FAKE_MENU FAKE_TRANSCRIPT
  export FAKE_CURSOR FAKE_GEOMETRY FAKE_RUN_SHELL_COMMAND
  export FAKE_RUN_SHELL_ENV
  export FAKE_PANE_CWD FAKE_PANE_PID FAKE_SESSION_NAME FAKE_ORIGINAL_GEOMETRY
  export FAKE_WINDOW_SIZE_CONFIGURED FAKE_WINDOW_SIZE_GLOBAL
  export FAKE_EPOCH_CALL_COUNT
}

activity_exists() {
  grep -Eq '"type":"(user.message|assistant.turn_start)"' \
    "${FAKE_WORKSPACE%/workspace.yaml}/events.jsonl"
}

run_helper() {
  local command="$1"
  (
    # shellcheck source=skills/self-compact/scripts/input-recovery.sh
    source "$SCRIPT_DIR/input-recovery.sh"
    sc_input_init "$FAKE_BIN/tmux" "%1"
    SELF_COMPACT_CAPTURE_DELAY_SECONDS="${SELF_COMPACT_CAPTURE_DELAY_SECONDS:-0.001}" \
      SELF_COMPACT_RESIZE_HOLD_SECONDS="${SELF_COMPACT_RESIZE_HOLD_SECONDS:-0.001}" \
      SELF_COMPACT_RENDER_WAIT_SECONDS="${SELF_COMPACT_RENDER_WAIT_SECONDS:-0.03}" \
      SELF_COMPACT_RENDER_POLL_SECONDS="${SELF_COMPACT_RENDER_POLL_SECONDS:-0.001}" \
      sc_prepare_verified_command "$command" activity_exists
  )
}

run_submit_command() {
  TMUX_PANE="%1" \
    SELF_COMPACT_SESSION_STATE_DIR="$FAKE_CASE" \
    SELF_COMPACT_WORKSPACE="$FAKE_WORKSPACE" \
    SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
    SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
    SELF_COMPACT_RENDER_WAIT_SECONDS="${SELF_COMPACT_RENDER_WAIT_SECONDS:-0.05}" \
    SELF_COMPACT_RENDER_POLL_SECONDS="${SELF_COMPACT_RENDER_POLL_SECONDS:-0.001}" \
    SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.05 \
    SELF_COMPACT_NOTICE_MILLISECONDS=20 \
    SELF_COMPACT_POLL_SECONDS=0.02 \
    SELF_COMPACT_MAX_POLLS=250 \
    SELF_COMPACT_START_GRACE_SECONDS=0.3 \
    SELF_COMPACT_RESUME_GRACE_SECONDS=0.01 \
    SELF_COMPACT_CONTINUATION_CONFIRM_DELAY_SECONDS=0.01 \
    SELF_COMPACT_CONTINUATION_CONFIRM_POLLS=100 \
    "$SCRIPT_DIR/submit-compact.sh" "$@"
}

run_submit() {
  local continuation="${1:-}"
  local steer="Keep: active baton. Drop: resolved detail."
  if [ -n "$continuation" ]; then
    run_submit_command --continuation "$continuation" "$steer"
  else
    run_submit_command "$steer"
  fi
}

wait_for_watcher_log() {
  local pattern="$1"
  local log=""
  for _ in $(seq 1 200); do
    log="$(find "$FAKE_CASE/session/files" -name 'self-compact-*.log' -print -quit)"
    [ -n "$log" ] && grep -qE "$pattern" "$log" 2>/dev/null && {
      printf '%s\n' "$log"
      return 0
    }
    sleep 0.02
  done
  fail "timed out waiting for watcher log pattern [$pattern]"
}

# Exact ownership accepts one captured prompt row only.
cat > "$FAKE_BIN/scrubbed-tmux" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:?tmux command is required}" in
  display-message)
    last=""
    for argument in "$@"; do
      last="$argument"
    done
    case "$last" in
      '#{pane_width}') printf '%s\n' 120 ;;
      *) printf '%s\n' '9|10|40' ;;
    esac
    ;;
  capture-pane)
    printf '%s\n' \
      "header" "❯ proceed" "────────────────" "footer"
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$FAKE_BIN/scrubbed-tmux"
scrubbed_locale_result="$(
  env -i HOME="$HOME" PATH=/usr/bin:/bin /bin/bash -c '
    source "$1"
    sc_input_init "$2" "%1"
    sample="$(sc_capture_sample)"
    [ "$sample" = "readable|70726f63656564|0|9|10|0" ]
    sc_load_state_record "$sample"
    sc_state_is_exact "$(sc_literal_hex proceed)"
    [ -n "$LC_ALL" ] && [ "$LC_ALL" = "$LANG" ]
    printf "%s|%s\n" "$LC_ALL" "$SC_STATE_TEXT_HEX"
  ' bash "$SCRIPT_DIR/input-recovery.sh" "$FAKE_BIN/scrubbed-tmux"
)" || fail "real helper rejected proceed under env -i HOME/PATH"
case "$scrubbed_locale_result" in
  *"|70726f63656564") ;;
  *) fail "unexpected scrubbed-locale helper result: $scrubbed_locale_result" ;;
esac

(
  source "$SCRIPT_DIR/input-recovery.sh"
  for rejected_locale in C POSIX definitely-not-a-locale; do
    if sc_locale_supports_parser "$rejected_locale"; then
      fail "non-UTF-8 locale unexpectedly passed: $rejected_locale"
    fi
  done
  export SELF_COMPACT_LOCALE=C
  sc_input_init "$FAKE_BIN/scrubbed-tmux" "%1"
  [ "$SC_INPUT_LOCALE" != C ] &&
    [ "$SC_INPUT_LOCALE" != POSIX ] &&
    sc_locale_supports_parser "$SC_INPUT_LOCALE"
) || fail "real locale fallback did not advance past C"

printf '%s\n' \
  "header" "❯ /compact exact    " "────────────────" "footer" |
  prompt_matches "/compact exact" ||
  fail "one exact prompt row was rejected"

if printf '%s\n' \
  "header" "❯ /compact keep    " "  this    " \
  "────────────────" "footer" |
  prompt_matches "/compact keep this"; then
  fail "expected-space logical newline compared equal"
fi
if printf '%s\n' \
  "header" "❯ /compact kee    " "  p this    " \
  "────────────────" "footer" |
  prompt_matches "/compact keep this"; then
  fail "mid-token logical newline compared equal"
fi
if printf '%s\n' \
  "header" "❯ /compact exact    " "      " \
  "────────────────" "footer" |
  prompt_matches "/compact exact"; then
  fail "blank second captured row compared equal"
fi

printf '%s\n' \
  "header" "❯ /compact draft.        " "────────────────" "footer" |
  prompt_matches "/compact draft." ||
  fail "transient captured right padding rejected the exact command"

expected="/compact keep"
for altered in \
  "/compactkeep" \
  "/compact  keep" \
  "/compact kee p" \
  $'/compact\tkeep'; do
  if printf '%s\n' \
    "header" "❯ $altered    " "────────────────" "footer" |
    prompt_matches "$expected"; then
    fail "altered whitespace compared equal: [$altered]"
  fi
done
if printf '%s\n' \
  "header" "❯ /compact keepthis" "────────────────" "footer" |
  prompt_matches "/compact keep this"; then
  fail "removed internal space compared equal"
fi
for residual in \
  "draft /compact keep" \
  "/compact keep draft"; do
  if printf '%s\n' \
    "header" "❯ $residual" "────────────────" "footer" |
    prompt_matches "/compact keep"; then
    fail "residual prefix or suffix compared equal: [$residual]"
  fi
done
if printf '%s\n' \
  "header" "❯ /compact keep  " "────────────────" "footer" |
  prompt_matches "/compact keep  "; then
  fail "expected trailing bytes were incorrectly normalized"
fi
printf '%s\n' \
  "header" $'❯ /compact keep\t' "────────────────" "footer" |
  prompt_matches $'/compact keep\t' ||
  fail "captured trailing tab was mistaken for terminal space padding"
multiline_hex="$(
  printf '%s\n' \
    "header" "❯ prior unknown line" "  current line" \
    "────────────────" "footer" |
    prompt_hex
)"
[ -n "$multiline_hex" ] && [[ "$multiline_hex" == *0a* ]] ||
  fail "explicit multiline input lost its structural row boundary"
if (
  source "$SCRIPT_DIR/input-recovery.sh"
  sc_load_state_record "readable|$multiline_hex|0|2|10|0"
  sc_state_is_empty
); then
  fail "explicit multiline input was mislabeled empty"
fi
if printf '%s\n' \
  "header" "❯ prior unknown line" "  current line" \
  "────────────────" "footer" |
  prompt_matches "/compact current line"; then
  fail "explicit multiline residual compared equal"
fi

# Refresh plus a one-column pulse recovers an unreadable prompt without
# changing input, geometry, or inherited window-size state.
setup_case geometry-refresh
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
export FAKE_REPAIR_ON_RESIZE=1
(
  source "$SCRIPT_DIR/input-recovery.sh"
  sc_input_init "$FAKE_BIN/tmux" "%1"
  sc_capture_state
  [ "$SC_STATE_STATUS" = readable ]
)
assert_file_equals "120 40" "$FAKE_GEOMETRY"
assert_file_equals "" "$FAKE_WINDOW_SIZE_CONFIGURED"
assert_count 2 '^REFRESH:client-' "$FAKE_TMUX_ACTIONS"
grep -q 'RESIZE:test-session:0:119x40' "$FAKE_TMUX_ACTIONS"
grep -q 'RESIZE:test-session:0:120x40' "$FAKE_TMUX_ACTIONS"
grep -q '^SET:window-size:inherited$' "$FAKE_TMUX_ACTIONS"
grep -q '^CAPTURE:16:39$' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:|^TYPE:' "$FAKE_TMUX_ACTIONS"

# A configured window-size value is restored instead of being left manual.
setup_case geometry-configured-state
printf '%s' smallest > "$FAKE_WINDOW_SIZE_CONFIGURED"
(
  source "$SCRIPT_DIR/input-recovery.sh"
  sc_input_init "$FAKE_BIN/tmux" "%1"
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 sc_resize_pulse
)
assert_file_equals "120 40" "$FAKE_GEOMETRY"
assert_file_equals "smallest" "$FAKE_WINDOW_SIZE_CONFIGURED"
grep -q '^SET:window-size:smallest$' "$FAKE_TMUX_ACTIONS"

# A window linked into another session is never pulsed.
setup_case geometry-linked-window
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
export FAKE_WINDOW_LINKED=1
status=0
(
  source "$SCRIPT_DIR/input-recovery.sh"
  sc_input_init "$FAKE_BIN/tmux" "%1"
  SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 sc_capture_state
  [ "$SC_STATE_STATUS" = unknown ]
) || status=$?
[ "$status" -eq 0 ] || fail "linked unreadable window was not left unknown"
assert_count 0 '^RESIZE:' "$FAKE_TMUX_ACTIONS"
assert_file_equals "" "$FAKE_WINDOW_SIZE_CONFIGURED"

# Changing captures are unknown rather than empty.
setup_case unstable-capture
printf '%s' unstable > "$FAKE_CAPTURE_MODE"
status=0
(
  source "$SCRIPT_DIR/input-recovery.sh"
  sc_input_init "$FAKE_BIN/tmux" "%1"
  SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
    SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
    sc_capture_state
  [ "$SC_STATE_STATUS" = unknown ] &&
    [ "$SC_STATE_TEXT_HEX" = unknown ]
) || status=$?
[ "$status" -eq 0 ] || fail "changing captures were not classified unknown"

# The EXIT trap retries restoration when the normal restore command fails.
setup_case geometry-trap
export FAKE_FAIL_FIRST_RESTORE=1
if (
  source "$SCRIPT_DIR/input-recovery.sh"
  sc_input_init "$FAKE_BIN/tmux" "%1"
  sc_resize_pulse
); then
  fail "resize pulse unexpectedly succeeded after a forced restore failure"
fi
assert_file_equals "120 40" "$FAKE_GEOMETRY"
assert_file_equals "" "$FAKE_WINDOW_SIZE_CONFIGURED"
assert_count 2 '^RESIZE:test-session:0:120x40$' "$FAKE_TMUX_ACTIONS"

# Empty, visible-draft, and hidden-draft Ctrl-S classifications are exact.
setup_case invalid-locale
invalid_locale_bin="$FAKE_CASE/invalid-locale-bin"
mkdir -p "$invalid_locale_bin"
cat > "$invalid_locale_bin/awk" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$invalid_locale_bin/awk"
if (
  export PATH="$invalid_locale_bin:$PATH"
  export SELF_COMPACT_LOCALE=definitely-invalid
  source "$SCRIPT_DIR/input-recovery.sh"
  SC_STATE_STATUS=readable
  SC_STATE_TEXT_HEX=70726f63656564
  sc_input_init "$FAKE_BIN/tmux" "%1"
); then
  fail "invalid locale unexpectedly initialized the input helper"
fi
(
  export PATH="$invalid_locale_bin:$PATH"
  export SELF_COMPACT_LOCALE=definitely-invalid
  source "$SCRIPT_DIR/input-recovery.sh"
  SC_STATE_STATUS=readable
  SC_STATE_TEXT_HEX=70726f63656564
  sc_input_init "$FAKE_BIN/tmux" "%1" || true
  [ "$SC_STATE_STATUS" = unknown ] &&
    [ "$SC_STATE_TEXT_HEX" = unknown ]
) || fail "locale initialization failure did not leave input state unknown"
status=0
(
  export PATH="$invalid_locale_bin:$PATH"
  export SELF_COMPACT_LOCALE=definitely-invalid
  run_submit
) > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -ne 0 ] || fail "invalid locale unexpectedly submitted compact"
grep -q 'could not verify a UTF-8 locale; compact not submitted' \
  "$FAKE_CASE/submit.err"
assert_count 0 '^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

: > "$FAKE_CASE/ready"
: > "$FAKE_CASE/armed"
status=0
(
  export PATH="$invalid_locale_bin:$PATH"
  export SELF_COMPACT_LOCALE=definitely-invalid
  "$SCRIPT_DIR/resume-after-compact.sh" \
    "%1" "$FAKE_WORKSPACE" 1 0 "$FAKE_CASE/ready" "$FAKE_CASE/armed" \
    "$FAKE_CASE/cancelled" "SCM:00000000-00001" "proceed" \
    "$FAKE_BIN/tmux" "/compact invalid-locale"
) > "$FAKE_CASE/watcher.out" 2> "$FAKE_CASE/watcher.err" || status=$?
[ "$status" -ne 0 ] || fail "invalid-locale watcher unexpectedly continued"
grep -q 'continuation watcher could not verify a UTF-8 locale' \
  "$FAKE_CASE/watcher.err"
assert_count 0 '^NOTICE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case empty-input
run_helper "/compact empty"
assert_count 1 '^KEY:C-s$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:/compact empty$' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:C-u|^KEY:Escape' "$FAKE_TMUX_ACTIONS"

setup_case captured-right-padding
export FAKE_CAPTURE_RIGHT_PADDING="    "
run_helper "/compact exact"
assert_file_equals "/compact exact" "$FAKE_TMUX_INPUT"
assert_count 0 '^KEY:C-u|^KEY:Escape' "$FAKE_TMUX_ACTIONS"

setup_case transient-right-padding
export FAKE_CAPTURE_TRANSIENT_RIGHT_PADDING=1
run_helper "/compact stable despite transient padding"
assert_file_equals "/compact stable despite transient padding" "$FAKE_TMUX_INPUT"
assert_count 1 '^TYPE:/compact stable despite transient padding$' \
  "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:C-u|^KEY:Escape' "$FAKE_TMUX_ACTIONS"

setup_case second-row-cleanup-rejected
split_cleanup_command="/compact Keep this helper command for cleanup."
printf '%s' "$split_cleanup_command" > "$FAKE_TMUX_INPUT"
export FAKE_CAPTURE_SPLIT_COLUMNS=24
export FAKE_CAPTURE_RIGHT_PADDING="     "
(
  source "$SCRIPT_DIR/input-recovery.sh"
  sc_input_init "$FAKE_BIN/tmux" "%1"
  SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
    sc_cleanup_exact_command "$(sc_literal_hex "$split_cleanup_command")"
)
assert_file_equals "$split_cleanup_command" "$FAKE_TMUX_INPUT"
assert_count 0 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"

for boundary_case in expected-space mid-token; do
  setup_case "logical-newline-$boundary_case"
  if [ "$boundary_case" = expected-space ]; then
    export FAKE_CAPTURE_SPLIT_COLUMNS=15
  else
    export FAKE_CAPTURE_SPLIT_COLUMNS=14
  fi
  status=0
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
    run_helper "/compact keep this" || status=$?
  [ "$status" -ne 0 ] ||
    fail "$boundary_case logical newline authorized the command"
  assert_count 0 '^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
done

setup_case visible-draft
printf '%s' "unique visible draft" > "$FAKE_TMUX_INPUT"
run_helper "/compact visible"
assert_file_equals "unique visible draft" "$FAKE_TMUX_STASH"
assert_count 1 '^KEY:C-s$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:/compact visible$' "$FAKE_TMUX_ACTIONS"

setup_case transcript-menu-prose
printf '%s\n' \
  "Earlier output says press esc to cancel the tool." \
  "Another paragraph says select an option before continuing." \
  > "$FAKE_TRANSCRIPT"
printf '%s' "draft with menu words in transcript" > "$FAKE_TMUX_INPUT"
run_helper "/compact transcript"
assert_file_equals "draft with menu words in transcript" "$FAKE_TMUX_STASH"
assert_count 0 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:/compact transcript$' "$FAKE_TMUX_ACTIONS"

setup_case hidden-draft
printf '%s' "unique hidden draft" > "$FAKE_TMUX_STASH"
run_helper "/compact hidden"
assert_file_equals "unique hidden draft" "$FAKE_TMUX_STASH"
assert_count 2 '^KEY:C-s$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:/compact hidden$' "$FAKE_TMUX_ACTIONS"

# Unreadable is unknown. After the visible grace period, Ctrl-U is first and
# no Esc is sent when that key repairs the editor and the command is exact.
setup_case unreadable-ctrl-u
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
printf '%s' "unknown draft" > "$FAKE_TMUX_INPUT"
export FAKE_REPAIR_ON_CU=1
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.05 \
  run_helper "/compact repaired"
grep -q '^NOTICE:self-compact: input changed or unreadable; will clear it in 10 seconds' \
  "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Escape' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:/compact repaired$' "$FAKE_TMUX_ACTIONS"
first_clear="$(grep -n '^KEY:C-u:' "$FAKE_TMUX_ACTIONS" | head -1 | cut -d: -f1)"
first_type="$(grep -n '^TYPE:' "$FAKE_TMUX_ACTIONS" | head -1 | cut -d: -f1)"
[ "$first_clear" -lt "$first_type" ] || fail "unknown text was typed over before Ctrl-U"

# Esc is conditional, sent once by default, and sent a second time only while
# a visible menu remains. Recovery stays within all numeric bounds.
setup_case conditional-esc
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
printf '%s' "draft before menu" > "$FAKE_TMUX_INPUT"
printf '%s' 1 > "$FAKE_MENU"
export FAKE_REPAIR_ON_CU=1
export FAKE_ESC_CLOSE_AFTER=1
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
  run_helper "/compact menu"
assert_count 3 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 2 '^TYPE:/compact menu$' "$FAKE_TMUX_ACTIONS"

setup_case second-esc
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
printf '%s' "draft before persistent menu" > "$FAKE_TMUX_INPUT"
printf '%s' 1 > "$FAKE_MENU"
export FAKE_REPAIR_ON_CU=1
export FAKE_ESC_CLOSE_AFTER=2
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
  run_helper "/compact two-esc"
assert_count 2 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_at_most 4 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_at_most 2 '^TYPE:' "$FAKE_TMUX_ACTIONS"
assert_at_most 2 '^KEY:C-s$' "$FAKE_TMUX_ACTIONS"

# A readable normal-path command modified by an unsubmitted user draft enters
# the same visible grace policy and preserves the draft when activity starts.
setup_case normal-path-concurrent-draft
export FAKE_APPEND_ON_TYPE=" user draft"
export FAKE_APPEND_ON_TYPE_COMMAND="/compact guarded"
export FAKE_ACTIVITY_ON_NOTICE=1
status=0
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
  run_helper "/compact guarded" || status=$?
[ "$status" -eq 10 ] ||
  fail "normal-path concurrent draft returned $status instead of 10"
assert_file_equals "/compact guarded user draft" "$FAKE_TMUX_INPUT"
assert_count 1 '^TYPE:/compact guarded$' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:C-u:|^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
grep -q '^NOTICE:self-compact: input changed or unreadable; will clear it in 10 seconds' \
  "$FAKE_TMUX_ACTIONS"

# A renderer that remains stably empty for several captures and then shows the
# wrong command still exhausts the render window before bounded recovery fails
# closed.
setup_case delayed-wrong-render
export FAKE_RENDER_DELAY_TYPE_COUNT=all
export FAKE_RENDER_DELAY_CAPTURES=3
export FAKE_RENDER_WRONG_VALUE="/compact delayed but wrong"
status=0
SELF_COMPACT_RENDER_WAIT_SECONDS=2 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
  run_helper "/compact expected after delay" || status=$?
[ "$status" -ne 0 ] || fail "delayed wrong rendering unexpectedly succeeded"
assert_count 2 '^TYPE:/compact expected after delay$' "$FAKE_TMUX_ACTIONS"
assert_count 4 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_at_most 2 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
assert_count 1 \
  '^NOTICE:self-compact: input changed or unreadable; will clear it in 10 seconds' \
  "$FAKE_TMUX_ACTIONS"
grep -q '^NOTICE:self-compact: input recovery failed; command was not submitted' \
  "$FAKE_TMUX_ACTIONS"

# A readable normal path that exposes a menu after typing #1 must complete the
# Ctrl-U/Escape/menu-dismiss/Ctrl-U sequence before typing #2 and submitting it.
setup_case normal-path-menu
export FAKE_APPEND_ON_TYPE=" menu draft"
export FAKE_APPEND_ON_TYPE_COUNT=1
export FAKE_MENU_ON_TYPE_COUNT=1
export FAKE_ESC_CLOSE_AFTER=2
SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 run_submit
assert_count 3 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 2 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 2 '^TYPE:' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
first_typed="$(grep '^TYPE:' "$FAKE_TMUX_ACTIONS" | sed -n '1s/^TYPE://p')"
second_typed="$(grep '^TYPE:' "$FAKE_TMUX_ACTIONS" | sed -n '2s/^TYPE://p')"
[ "$first_typed" = "$second_typed" ] ||
  fail "normal-path menu retry changed the command"
first_type_line="$(grep -n '^TYPE:' "$FAKE_TMUX_ACTIONS" | sed -n '1s/:.*//p')"
first_clear_line="$(grep -n '^KEY:C-u:' "$FAKE_TMUX_ACTIONS" | sed -n '1s/:.*//p')"
second_clear_line="$(grep -n '^KEY:C-u:' "$FAKE_TMUX_ACTIONS" | sed -n '2s/:.*//p')"
first_escape_line="$(grep -n '^KEY:Escape:' "$FAKE_TMUX_ACTIONS" | sed -n '1s/:.*//p')"
second_escape_line="$(grep -n '^KEY:Escape:' "$FAKE_TMUX_ACTIONS" | sed -n '2s/:.*//p')"
third_clear_line="$(grep -n '^KEY:C-u:' "$FAKE_TMUX_ACTIONS" | sed -n '3s/:.*//p')"
second_type_line="$(grep -n '^TYPE:' "$FAKE_TMUX_ACTIONS" | sed -n '2s/:.*//p')"
enter_line="$(grep -n '^KEY:Enter:' "$FAKE_TMUX_ACTIONS" | sed -n '1s/:.*//p')"
[ "$first_type_line" -lt "$first_clear_line" ] &&
  [ "$first_clear_line" -lt "$second_clear_line" ] &&
  [ "$second_clear_line" -lt "$first_escape_line" ] &&
  [ "$first_escape_line" -lt "$second_escape_line" ] &&
  [ "$second_escape_line" -lt "$third_clear_line" ] &&
  [ "$third_clear_line" -lt "$second_type_line" ] &&
  [ "$second_type_line" -lt "$enter_line" ] ||
  fail "normal-path menu retry used the wrong recovery order"
assert_file_equals "$second_typed" "$FAKE_TMUX_QUEUE"
grep -Fqx "KEY:Enter:$second_typed" "$FAKE_TMUX_ACTIONS" ||
  fail "normal-path menu did not submit the second exact typing"
assert_file_equals 0 "$FAKE_MENU"

# Activity recorded by the first Escape blocks every later destructive key.
setup_case activity-after-escape
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
printf '%s' "draft before escape activity" > "$FAKE_TMUX_INPUT"
printf '%s' 1 > "$FAKE_MENU"
export FAKE_REPAIR_ON_CU=1
export FAKE_ACTIVITY_ON_ESC=1
status=0
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
  run_helper "/compact escape-race" || status=$?
[ "$status" -eq 10 ] ||
  fail "Escape activity returned $status instead of 10"
assert_count 2 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"

# Persistent unreadability cancels after bounded cleanup and never reaches
# Enter. The helper-authored final attempt is cleared where possible.
setup_case persistent-unreadable
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
printf '%s' "unreadable draft" > "$FAKE_TMUX_INPUT"
status=0
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
  run_helper "/compact never-visible" || status=$?
[ "$status" -ne 0 ] || fail "persistent unreadability unexpectedly succeeded"
assert_count 4 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_at_most 2 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_at_most 2 '^TYPE:' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:C-s$' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
assert_file_equals "" "$FAKE_TMUX_INPUT"
grep -q '^NOTICE:self-compact: input recovery failed; command was not submitted' \
  "$FAKE_TMUX_ACTIONS"

# Copilot Ctrl-U is line-local. A prior logical line that survives every
# bounded clear remains visible, is never submitted, and forces failure closed.
setup_case multiline-residual
printf '%s' $'prior unknown line\ncurrent line' > "$FAKE_TMUX_INPUT"
export FAKE_CS_NOOP=1
export FAKE_CU_LINE_LOCAL=1
status=0
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 \
  run_helper "/compact multiline" || status=$?
[ "$status" -ne 0 ] || fail "multiline residual unexpectedly succeeded"
assert_file_equals "prior unknown line" "$FAKE_TMUX_INPUT"
assert_count 4 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_at_most 2 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_at_most 2 '^TYPE:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
assert_file_equals "" "$FAKE_TMUX_QUEUE"
grep -q '^NOTICE:self-compact: input recovery failed; command was not submitted' \
  "$FAKE_TMUX_ACTIONS"

# A user submission during the grace period cancels before any destructive key,
# Esc, or helper typing.
setup_case grace-activity
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
printf '%s' "draft submitted during grace" > "$FAKE_TMUX_INPUT"
(
  sleep 0.03
  printf '%s\n' '{"type":"user.message","content":"user won"}' \
    >> "$FAKE_CASE/session/events.jsonl"
) &
printf '%s\n' "$!" >> "$FAKE_BACKGROUND_PIDS"
status=0
SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
  SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
  SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.1 \
  run_helper "/compact cancelled" || status=$?
[ "$status" -eq 10 ] || fail "grace activity returned $status instead of 10"
assert_count 0 '^KEY:C-u:|^KEY:Escape:|^TYPE:' "$FAKE_TMUX_ACTIONS"

# A full compact waits for the submitting turn end, accepts a start within the
# 15-second-relative deadline, preserves the draft, and submits each command
# with one exact Enter.
setup_case delayed-start
printf '%s' "already queued" > "$FAKE_TMUX_INPUT"
export FAKE_COMPACT_MODE=success
export FAKE_TURN_END_DELAY=0.45
export FAKE_START_DELAY=0.1
output="$(run_submit)"
case "$output" in
  *"submitted compact; post-compact continuation watcher armed"*) ;;
  *) fail "unexpected submit output: $output" ;;
esac
grep -qF '|| true' "$FAKE_RUN_SHELL_COMMAND"
log="$(wait_for_watcher_log 'submitted post-compact continuation')"
assert_file_equals $'LANG=unset\nLC_ALL=unset' "$FAKE_RUN_SHELL_ENV"
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:proceed$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:proceed$' "$FAKE_TMUX_ACTIONS"
assert_file_equals "already queued" "$FAKE_TMUX_INPUT"
grep -q 'marked compact advanced summary_count to 2' "$log"

# A delayed compact render is polled read-only until the exact marked command
# appears. It does not spend another typing, recovery key, or warning.
setup_case delayed-compact-render
export FAKE_RENDER_DELAY_TYPE_COUNT=1
export FAKE_RENDER_DELAY_CAPTURES=3
SELF_COMPACT_RENDER_WAIT_SECONDS=5 run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^TYPE:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 0 \
  '^NOTICE:self-compact: input changed or unreadable; will clear it in 10 seconds' \
  "$FAKE_TMUX_ACTIONS"

# The continuation uses the same delayed-render polling and reaches one exact
# Enter without warning or editor recovery.
setup_case delayed-continuation-render
export FAKE_RENDER_DELAY_TYPE_COUNT=2
export FAKE_RENDER_DELAY_CAPTURES=3
SELF_COMPACT_RENDER_WAIT_SECONDS=5 run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^TYPE:proceed$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:proceed$' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 0 \
  '^NOTICE:self-compact: input changed or unreadable; will clear it in 10 seconds' \
  "$FAKE_TMUX_ACTIONS"

# The fixed marker and instruction leave exactly 31 steer columns in a
# 68-column pane after the four-column editor margin.
setup_case exact-one-row-68
printf '%s\n' "68 40" > "$FAKE_GEOMETRY"
max_steer="$(printf '%031d' 0 | tr '0' s)"
run_submit_command "$max_steer" >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^TYPE:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:proceed$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:proceed$' "$FAKE_TMUX_ACTIONS"
one_row_command="$(grep '^TYPE:/compact ' "$FAKE_TMUX_ACTIONS" | sed 's/^TYPE://')"
[ "${#one_row_command}" -eq 64 ] ||
  fail "68-column command used ${#one_row_command} safe columns instead of 64"
grep -Fqx "KEY:Enter:$one_row_command" "$FAKE_TMUX_ACTIONS" ||
  fail "exact one-row compact did not receive its single Enter"
checkpoint="$FAKE_CASE/session/checkpoints/001-test.md"
grep -Eq '^SCM:[0-9a-f]{8}-[0-9a-f]{5}$' "$checkpoint" ||
  fail "concise SCM marker was not retained in the checkpoint"

# One extra steer column fails before watcher launch, run files, or Ctrl-S.
setup_case long-steer-preflight
printf '%s\n' "68 40" > "$FAKE_GEOMETRY"
too_long_steer="$(printf '%032d' 0 | tr '0' s)"
status=0
run_submit_command "$too_long_steer" \
  > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -ne 0 ] || fail "overlong steer unexpectedly passed preflight"
grep -q 'marked compact command is 65 columns, but this pane safely allows 64' \
  "$FAKE_CASE/submit.err"
[ ! -s "$FAKE_RUN_SHELL_COMMAND" ] ||
  fail "overlong steer launched a watcher"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
if find "$FAKE_CASE/session/files" -name 'self-compact-*' -print -quit |
  grep -q .; then
  fail "overlong steer created run files"
fi

# An overlong continuation fails at the same preflight boundary.
setup_case long-continuation-preflight
printf '%s\n' "68 40" > "$FAKE_GEOMETRY"
too_long_continuation="$(printf '%065d' 0 | tr '0' c)"
status=0
run_submit_command --continuation "$too_long_continuation" x \
  > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -ne 0 ] ||
  fail "overlong continuation unexpectedly passed preflight"
grep -q 'continuation is 65 columns, but this pane safely allows 64' \
  "$FAKE_CASE/submit.err"
[ ! -s "$FAKE_RUN_SHELL_COMMAND" ] ||
  fail "overlong continuation launched a watcher"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

# Printable ASCII is a fail-closed prerequisite for both commands.
setup_case non-ascii-steer
status=0
run_submit_command "café" \
  > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -ne 0 ] || fail "non-ASCII steer unexpectedly passed"
grep -q 'steer must contain only printable ASCII' "$FAKE_CASE/submit.err"
[ ! -s "$FAKE_RUN_SHELL_COMMAND" ] || fail "non-ASCII steer launched a watcher"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case non-ascii-continuation
status=0
run_submit_command --continuation "procéed" x \
  > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -ne 0 ] || fail "non-ASCII continuation unexpectedly passed"
grep -q 'continuation must contain only printable ASCII' "$FAKE_CASE/submit.err"
[ ! -s "$FAKE_RUN_SHELL_COMMAND" ] ||
  fail "non-ASCII continuation launched a watcher"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

# A compaction start before assistant.turn_end is also accepted.
setup_case start-before-end
printf '%s' "hidden lifecycle draft" > "$FAKE_TMUX_STASH"
export FAKE_COMPACT_MODE=start-before-end
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:proceed$' "$FAKE_TMUX_ACTIONS"
assert_file_equals "hidden lifecycle draft" "$FAKE_TMUX_INPUT"

# A start arriving when the epoch deadline is observed is accepted by the
# mandatory final event read rather than being lost after the final interval.
setup_case near-deadline-start
mkdir -p "$FAKE_CASE/session/checkpoints"
sed 's/^summary_count: .*/summary_count: 2/' \
  "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.next"
mv "$FAKE_WORKSPACE.next" "$FAKE_WORKSPACE"
printf '%s\n' 'SCM:00000000-00002' > \
  "$FAKE_CASE/session/checkpoints/001-test.md"
printf '%s\n' '{"type":"assistant.turn_end"}' > \
  "$FAKE_CASE/session/events.jsonl"
printf '%s\n' 100000 100300 > "$FAKE_CASE/epoch-values"
export FAKE_EPOCH_MILLISECONDS_FILE="$FAKE_CASE/epoch-values"
export FAKE_EPOCH_APPEND_EVENTS_AT_CALL=2
export FAKE_EPOCH_EVENTS="$FAKE_CASE/session/events.jsonl"
: > "$FAKE_CASE/ready"
: > "$FAKE_CASE/armed"
near_deadline_output="$(
  SELF_COMPACT_POLL_SECONDS=0.01 \
    SELF_COMPACT_MAX_POLLS=20 \
    SELF_COMPACT_START_GRACE_SECONDS=0.3 \
    SELF_COMPACT_RESUME_GRACE_SECONDS=0.001 \
    "$SCRIPT_DIR/resume-after-compact.sh" \
    "%1" "$FAKE_WORKSPACE" 1 0 "$FAKE_CASE/ready" "$FAKE_CASE/armed" \
    "$FAKE_CASE/cancelled" "SCM:00000000-00002" "proceed" \
    "$FAKE_BIN/tmux" "/compact near-deadline"
)"
case "$near_deadline_output" in
  *"marked compact advanced summary_count to 2"*"post-compact activity already present"*) ;;
  *) fail "near-deadline start was not accepted: $near_deadline_output" ;;
esac
assert_count 0 '^KEY:|^TYPE:' "$FAKE_TMUX_ACTIONS"

# The unreadable fallback also reaches one exact compact Enter end to end when
# Ctrl-U repairs the editor; it does not use Esc or append to the old draft.
setup_case unreadable-submit
printf '%s' unreadable > "$FAKE_CAPTURE_MODE"
printf '%s' "unreadable integration draft" > "$FAKE_TMUX_INPUT"
export FAKE_REPAIR_ON_CU=1
export FAKE_COMPACT_MODE=success
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
grep -q '^NOTICE:self-compact: input changed or unreadable; will clear it in 10 seconds' \
  "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"

# If Enter leaves the exact helper command but no start follows, the watcher
# clears only that exact command, warns visibly, and exits promptly.
setup_case no-start-exact
export FAKE_COMPACT_MODE=no-start-keep
run_submit >/dev/null
log="$(wait_for_watcher_log 'compaction did not start within')"
assert_file_equals "" "$FAKE_TMUX_INPUT"
grep -q '^NOTICE:self-compact: compaction did not start; cancelled' \
  "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
if find "$FAKE_CASE/session/files" -name 'self-compact-*.ready' -print -quit |
  grep -q .; then
  fail "no-start watcher left a ready marker"
fi
if find "$FAKE_CASE/session/files" -name 'self-compact-*.armed' -print -quit |
  grep -q .; then
  fail "no-start watcher left an armed marker"
fi

# A different readable draft at no-start expiry is preserved without Ctrl-U.
setup_case no-start-new-draft
export FAKE_COMPACT_MODE=no-start-new-draft
run_submit >/dev/null
wait_for_watcher_log 'compaction did not start within' >/dev/null
assert_file_equals "new user draft" "$FAKE_TMUX_INPUT"
assert_count 0 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"

# An unreadable no-start buffer is also left untouched.
setup_case no-start-unreadable
export FAKE_COMPACT_MODE=no-start-unreadable
run_submit >/dev/null
wait_for_watcher_log 'compaction did not start within' >/dev/null
assert_count 0 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"

# A failed compact exits immediately and never injects continuation.
setup_case failed-compact
export FAKE_COMPACT_MODE=failed
run_submit >/dev/null
wait_for_watcher_log 'compact failed before producing the marked checkpoint' \
  >/dev/null
assert_count 0 '^TYPE:proceed$|^KEY:Enter:proceed$' "$FAKE_TMUX_ACTIONS"

# Activity beginning during post-compact recovery is checked before Esc and
# typing. No Esc or continuation Enter occurs after the activity event.
setup_case post-compact-race
export FAKE_COMPACT_MODE=success
export FAKE_POST_COMPACT_MODE=unreadable
export FAKE_ACTIVITY_ON_CU=1
export FAKE_REPAIR_ON_CU=1
run_submit >/dev/null
wait_for_watcher_log 'post-compact activity started during recovery' >/dev/null
assert_count 1 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^TYPE:proceed$|^KEY:Enter:proceed$' "$FAKE_TMUX_ACTIONS"
grep -q '"type":"assistant.turn_end"' "$FAKE_CASE/session/events.jsonl"

# Activity after continuation typing is caught by render polling. A second
# captured row prevents cleanup ownership as well as Enter ownership.
setup_case post-compact-enter-race
export FAKE_COMPACT_MODE=success
split_continuation="continue after this deliberately split continuation command"
export FAKE_CAPTURE_SPLIT_COLUMNS=20
export FAKE_CAPTURE_SPLIT_TYPE_COUNT=2
export FAKE_ACTIVITY_ON_TYPE="$split_continuation"
run_submit "$split_continuation" >/dev/null
wait_for_watcher_log 'post-compact activity started during recovery' >/dev/null
assert_count 1 "^TYPE:$split_continuation$" "$FAKE_TMUX_ACTIONS"
assert_count 0 "^KEY:Enter:$split_continuation$" "$FAKE_TMUX_ACTIONS"
assert_file_equals "$split_continuation" "$FAKE_TMUX_INPUT"

# Existing automatic activity still wins without any TUI mutation.
setup_case automatic-activity
mkdir -p "$FAKE_CASE/session/checkpoints"
sed 's/^summary_count: .*/summary_count: 2/' \
  "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.next"
mv "$FAKE_WORKSPACE.next" "$FAKE_WORKSPACE"
printf '%s\n' 'SCM:00000000-00003' > \
  "$FAKE_CASE/session/checkpoints/001-test.md"
cat > "$FAKE_CASE/session/events.jsonl" <<'EOF'
{"type":"session.compaction_start"}
{"type":"session.compaction_complete","success":true}
{"type":"assistant.turn_start"}
EOF
: > "$FAKE_CASE/ready"
: > "$FAKE_CASE/armed"
auto_output="$(
  SELF_COMPACT_POLL_SECONDS=0.01 \
    SELF_COMPACT_MAX_POLLS=20 \
    SELF_COMPACT_RESUME_GRACE_SECONDS=0.01 \
    "$SCRIPT_DIR/resume-after-compact.sh" \
    "%1" "$FAKE_WORKSPACE" 1 0 "$FAKE_CASE/ready" "$FAKE_CASE/armed" \
    "$FAKE_CASE/cancelled" "SCM:00000000-00003" "proceed" \
    "$FAKE_BIN/tmux" "/compact auto"
)"
case "$auto_output" in
  *"post-compact activity already present"*) ;;
  *) fail "automatic activity was not preserved: $auto_output" ;;
esac
assert_count 0 '^KEY:|^TYPE:' "$FAKE_TMUX_ACTIONS"
[ ! -e "$FAKE_CASE/ready" ] || fail "one-shot watcher left ready marker"
[ ! -e "$FAKE_CASE/armed" ] || fail "one-shot watcher left armed marker"

# The real tmux check uses a private socket inside the test root, never a live
# user server, and proves both geometry and inherited window-size restoration.
if [ -n "$REAL_TMUX_BIN" ]; then
  REAL_TMUX_SOCKET="$PROJECT_ROOT/.sct.$$"
  cat > "$FAKE_BIN/isolated-tmux" <<EOF
#!/usr/bin/env bash
exec "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" "\$@"
EOF
  chmod +x "$FAKE_BIN/isolated-tmux"
  "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" new-session -d \
    -s self-compact-test -x 100 -y 30
  real_geometry_before="$(
    "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" display-message -p \
      -t self-compact-test:0.0 '#{window_width}x#{window_height}'
  )"
  real_configured_before="$(
    "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" show-options -w -qv \
      -t self-compact-test:0 window-size
  )"
  real_effective_before="$(
    "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" show-options -w -A -v \
      -t self-compact-test:0 window-size
  )"
  (
    source "$SCRIPT_DIR/input-recovery.sh"
    sc_input_init "$FAKE_BIN/isolated-tmux" "self-compact-test:0.0"
    SELF_COMPACT_RESIZE_HOLD_SECONDS=0.01 sc_resize_pulse
  )
  real_geometry_after="$(
    "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" display-message -p \
      -t self-compact-test:0.0 '#{window_width}x#{window_height}'
  )"
  real_configured_after="$(
    "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" show-options -w -qv \
      -t self-compact-test:0 window-size
  )"
  real_effective_after="$(
    "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" show-options -w -A -v \
      -t self-compact-test:0 window-size
  )"
  [ "$real_geometry_after" = "$real_geometry_before" ] ||
    fail "real tmux geometry changed: $real_geometry_before -> $real_geometry_after"
  [ "$real_configured_after" = "$real_configured_before" ] ||
    fail "real tmux configured window-size state changed"
  [ "$real_effective_after" = "$real_effective_before" ] ||
    fail "real tmux effective window-size changed"
  "$REAL_TMUX_BIN" -S "$REAL_TMUX_SOCKET" kill-server
  rm -f "$REAL_TMUX_SOCKET"
  REAL_TMUX_SOCKET=""
fi

echo "submit-compact test passed"
