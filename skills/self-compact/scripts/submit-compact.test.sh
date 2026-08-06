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

wait_for_path_absent() {
  local path="$1"
  for _ in $(seq 1 200); do
    [ ! -e "$path" ] && return 0
    sleep 0.02
  done
  fail "timed out waiting for $path to be removed"
}

wait_for_path() {
  local path="$1"
  for _ in $(seq 1 200); do
    [ -e "$path" ] && return 0
    sleep 0.02
  done
  fail "timed out waiting for $path"
}

wait_for_process_exit() {
  local pid="$1"
  for _ in $(seq 1 200); do
    kill -0 "$pid" >/dev/null 2>&1 || return 0
    sleep 0.02
  done
  fail "timed out waiting for process $pid to exit"
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
          pane_width_count="$(increment_file "$FAKE_PANE_WIDTH_COUNT")"
          if [ "${FAKE_REMOVE_HANDOFF_ON_PANE_WIDTH_COUNT:-0}" -eq "$pane_width_count" ]; then
            find "$FAKE_CASE/session/files" -name 'self-compact-*.handoff' \
              -delete
            action "HOOK:removed-handoff-at-pane-width:$pane_width_count"
          fi
          if [ "${FAKE_APPEND_EVENTS_ON_PANE_WIDTH_COUNT:-0}" -eq "$pane_width_count" ]; then
            cat "$FAKE_PANE_WIDTH_EVENTS" \
              >> "$FAKE_CASE/session/events.jsonl"
            action "HOOK:appended-events-at-pane-width:$pane_width_count"
          fi
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
        if [[ "$input" != /compact\ * ]] &&
          [ "${FAKE_CONTINUATION_ENTER_STATUS:-0}" -ne 0 ]; then
          exit "$FAKE_CONTINUATION_ENTER_STATUS"
        fi
        if [ "${FAKE_ENTER_STATUS:-0}" -ne 0 ] &&
          [ "${FAKE_ENTER_DELIVERED:-0}" != 1 ]; then
          exit "$FAKE_ENTER_STATUS"
        fi
        case "$input" in
          /compact\ *)
            printf '%s\n' "$input" >> "$FAKE_TMUX_QUEUE"
            custom_instructions="${input#/compact }"
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
                  printf '%s\n' "checkpoint without identity prose" > \
                    "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/002-test.md"
                  escaped_instructions="$(
                    printf '%s' "$custom_instructions" |
                      sed 's/\\/\\\\/g; s/"/\\"/g'
                  )"
                  append_event \
                    "{\"type\":\"session.compaction_complete\",\"data\":{\"success\":true,\"customInstructions\":\"$escaped_instructions\",\"checkpointNumber\":2}}"
                  if [ "${FAKE_POST_COMPACT_PREEXISTING_ACTIVITY:-0}" = 1 ]; then
                    append_event '{"agentId":null,"type":"assistant.turn_start"}'
                  fi
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
                  printf '%s\n' "checkpoint without identity prose" > \
                    "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/002-test.md"
                  escaped_instructions="$(
                    printf '%s' "$custom_instructions" |
                      sed 's/\\/\\\\/g; s/"/\\"/g'
                  )"
                  append_event \
                    "{\"type\":\"session.compaction_complete\",\"data\":{\"success\":true,\"customInstructions\":\"$escaped_instructions\",\"checkpointNumber\":2}}"
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
                  '{"type":"session.compaction_complete","data":{"success":false,"error":"Nothing to compact"}}'
                ;;
              mismatched-then-matching)
                : > "$FAKE_TMUX_INPUT"
                append_event '{"type":"session.compaction_start"}'
                sed 's/^summary_count: .*/summary_count: 2/' \
                  "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.next"
                mv "$FAKE_WORKSPACE.next" "$FAKE_WORKSPACE"
                mkdir -p "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints"
                printf '%s\n' "checkpoint without identity prose" > \
                  "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/002-test.md"
                append_event \
                  '{"type":"session.compaction_complete","data":{"success":true,"customInstructions":"Use SELF_COMPACT_BRIEF. B:deadbeef","checkpointNumber":2}}'
                escaped_instructions="$(
                  printf '%s' "$custom_instructions" |
                    sed 's/\\/\\\\/g; s/"/\\"/g'
                )"
                append_event \
                  "{\"type\":\"session.compaction_complete\",\"data\":{\"success\":true,\"customInstructions\":\"$escaped_instructions\",\"checkpointNumber\":2}}"
                ;;
              *)
                echo "unexpected compact mode: $FAKE_COMPACT_MODE" >&2
                exit 1
                ;;
            esac
            if [ "${FAKE_ENTER_STATUS:-0}" -ne 0 ]; then
              exit "$FAKE_ENTER_STATUS"
            fi
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
          if [ -n "${FAKE_CAPTURE_MODE_ON_TYPE:-}" ] &&
            { [ -z "${FAKE_CAPTURE_MODE_ON_TYPE_COUNT:-}" ] ||
              [ "$FAKE_CAPTURE_MODE_ON_TYPE_COUNT" -eq "$count" ]; }; then
            printf '%s' "$FAKE_CAPTURE_MODE_ON_TYPE" > "$FAKE_CAPTURE_MODE"
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
      if [ -n "${FAKE_DETACHED_PATH:-}" ]; then
        PATH="$FAKE_DETACHED_PATH"
        export PATH
      fi
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

if [ -n "${FAKE_EPOCH_EXACT_DEADLINE_ARMED:-}" ] &&
  [ -e "$FAKE_EPOCH_EXACT_DEADLINE_ARMED" ] &&
  printf '%s\n' "$@" | grep -qx -- '-MTime::HiRes=time'; then
  call=0
  [ -s "$FAKE_EPOCH_CALL_COUNT" ] &&
    call="$(cat "$FAKE_EPOCH_CALL_COUNT")"
  call=$((call + 1))
  printf '%s' "$call" > "$FAKE_EPOCH_CALL_COUNT"
  if [ "$call" -eq 1 ]; then
    printf '%s\n' 100000
  else
    if [ "$call" -eq 2 ]; then
      printf '%s\n' \
        '{"agentId":null,"type":"session.compaction_start"}' \
        '{"agentId":null,"type":"session.compaction_complete","data":{"success":true,"customInstructions":"Use SELF_COMPACT_BRIEF. B:0123abcd","checkpointNumber":2}}' \
        >> "$FAKE_EPOCH_EVENTS"
      sed 's/^summary_count: .*/summary_count: 2/' \
        "$FAKE_WORKSPACE" > "$FAKE_WORKSPACE.next"
      mv "$FAKE_WORKSPACE.next" "$FAKE_WORKSPACE"
      mkdir -p "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints"
      printf '%s\n' "checkpoint without identity prose" > \
        "${FAKE_WORKSPACE%/workspace.yaml}/checkpoints/002-test.md"
    fi
    printf '%s\n' 100300
  fi
  exit 0
fi

if [ -n "${FAKE_EPOCH_MILLISECONDS_FILE:-}" ] &&
  printf '%s\n' "$@" | grep -qx -- '-MTime::HiRes=time'; then
  if [ -n "${FAKE_EPOCH_AFTER_TYPE_COUNT:-}" ]; then
    current_type_count=0
    [ -s "$FAKE_TYPE_COUNT" ] &&
      current_type_count="$(cat "$FAKE_TYPE_COUNT")"
    if [ "$current_type_count" -lt "$FAKE_EPOCH_AFTER_TYPE_COUNT" ]; then
      exec /usr/bin/perl "$@"
    fi
  fi
  call=0
  [ -s "$FAKE_EPOCH_CALL_COUNT" ] &&
    call="$(cat "$FAKE_EPOCH_CALL_COUNT")"
  call=$((call + 1))
  printf '%s' "$call" > "$FAKE_EPOCH_CALL_COUNT"
  value="$(sed -n "${call}p" "$FAKE_EPOCH_MILLISECONDS_FILE")"
  if [ -z "$value" ] && [ "${FAKE_EPOCH_INCREMENT_AFTER_END:-0}" = 1 ]; then
    line_count="$(wc -l < "$FAKE_EPOCH_MILLISECONDS_FILE" | tr -d '[:space:]')"
    last_value="$(tail -1 "$FAKE_EPOCH_MILLISECONDS_FILE")"
    value=$((last_value + ((call - line_count) * 100000)))
  fi
  [ -n "$value" ] || value="$(tail -1 "$FAKE_EPOCH_MILLISECONDS_FILE")"
  if [ "${FAKE_EPOCH_APPEND_EVENTS_AT_CALL:-0}" -eq "$call" ]; then
    printf '%s\n' \
      '{"type":"session.compaction_start"}' \
      '{"type":"session.compaction_complete","data":{"success":true,"customInstructions":"Use SELF_COMPACT_BRIEF. B:0123abcd","checkpointNumber":2}}' \
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
  if [ "${SELF_COMPACT_TEST_PROGRESS:-0}" = 1 ]; then
    printf 'submit-compact test case: %s\n' "$name" >&2
  fi
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
  FAKE_PANE_WIDTH_COUNT="$FAKE_CASE/pane-width-count"
  FAKE_PANE_CWD="$FAKE_CASE/workspace"
  FAKE_PANE_PID=100
  FAKE_SESSION_NAME="test-session"
  FAKE_ORIGINAL_GEOMETRY="120x40"
  FAKE_TOOL_CALL_ID="call-self-compact-test"

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
  : > "$FAKE_PANE_WIDTH_COUNT"
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
  unset FAKE_CAPTURE_MODE_ON_TYPE FAKE_CAPTURE_MODE_ON_TYPE_COUNT
  unset FAKE_WINDOW_LINKED FAKE_EPOCH_MILLISECONDS_FILE
  unset FAKE_EPOCH_APPEND_EVENTS_AT_CALL FAKE_EPOCH_EVENTS
  unset FAKE_EPOCH_INCREMENT_AFTER_END
  unset FAKE_EPOCH_AFTER_TYPE_COUNT
  unset FAKE_EPOCH_EXACT_DEADLINE_ARMED
  unset FAKE_PUBLICATION_PID
  unset FAKE_FOREGROUND_CLOSURE_CONTENT FAKE_CLOSURE_TURN
  unset FAKE_TASK_COMPLETE_BEFORE_TURN_END
  unset FAKE_REMOVE_HANDOFF_BEFORE_COMPLETION
  unset FAKE_SUBAGENT_AFTER_TURN_END
  unset FAKE_DETACHED_PATH
  unset FAKE_ENTER_STATUS FAKE_ENTER_DELIVERED
  unset FAKE_CONTINUATION_ENTER_STATUS
  unset FAKE_POST_COMPACT_PREEXISTING_ACTIVITY
  unset FAKE_REMOVE_HANDOFF_ON_PANE_WIDTH_COUNT
  unset FAKE_APPEND_EVENTS_ON_PANE_WIDTH_COUNT FAKE_PANE_WIDTH_EVENTS
  unset FAKE_HANDOFF_MUTATION
  unset FAKE_BEFORE_HELPER_START_EVENTS
  unset FAKE_BEFORE_HELPER_COMPLETION_EVENTS
  unset FAKE_AFTER_HELPER_COMPLETION_EVENTS
  unset FAKE_SKIP_HELPER_START
  unset FAKE_SUBMIT_SCRIPT FAKE_PORTABLE_HOME FAKE_PORTABLE_HELPER

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
  export FAKE_EPOCH_CALL_COUNT FAKE_PANE_WIDTH_COUNT
  export FAKE_TOOL_CALL_ID
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
  local status=0
  if [ -n "${FAKE_BEFORE_HELPER_START_EVENTS:-}" ]; then
    cat "$FAKE_BEFORE_HELPER_START_EVENTS" \
      >> "$FAKE_CASE/session/events.jsonl"
  fi
  if [ "${FAKE_SKIP_HELPER_START:-0}" != 1 ]; then
    printf '%s\n' \
      "{\"agentId\":null,\"type\":\"tool.execution_start\",\"data\":{\"toolCallId\":\"$FAKE_TOOL_CALL_ID\",\"toolName\":\"bash\"}}" \
      >> "$FAKE_CASE/session/events.jsonl"
  fi
  TMUX_PANE="%1" \
    SELF_COMPACT_SESSION_STATE_DIR="$FAKE_CASE" \
    SELF_COMPACT_WORKSPACE="$FAKE_WORKSPACE" \
    SELF_COMPACT_CAPTURE_DELAY_SECONDS=0.001 \
    SELF_COMPACT_RESIZE_HOLD_SECONDS=0.001 \
    SELF_COMPACT_RENDER_WAIT_SECONDS="${SELF_COMPACT_RENDER_WAIT_SECONDS:-0.05}" \
    SELF_COMPACT_RENDER_POLL_SECONDS="${SELF_COMPACT_RENDER_POLL_SECONDS:-0.001}" \
    SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS="${SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS:-25}" \
    SELF_COMPACT_AUTH_WAIT_SECONDS="${SELF_COMPACT_AUTH_WAIT_SECONDS:-3}" \
    SELF_COMPACT_QUIESCENCE_GRACE_SECONDS="${SELF_COMPACT_QUIESCENCE_GRACE_SECONDS:-0.02}" \
    SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.05 \
    SELF_COMPACT_NOTICE_MILLISECONDS=20 \
    SELF_COMPACT_POLL_SECONDS=0.02 \
    SELF_COMPACT_MAX_POLLS=250 \
    SELF_COMPACT_START_GRACE_SECONDS="${SELF_COMPACT_START_GRACE_SECONDS:-0.3}" \
    SELF_COMPACT_RESUME_GRACE_SECONDS=0.01 \
    SELF_COMPACT_CONTINUATION_CONFIRM_DELAY_SECONDS=0.01 \
    SELF_COMPACT_CONTINUATION_CONFIRM_POLLS=100 \
    SELF_COMPACT_RUN_TOKEN=0123abcd \
    "${FAKE_SUBMIT_SCRIPT:-$SCRIPT_DIR/submit-compact.sh}" "$@" || status=$?
  if [ -n "${FAKE_PUBLICATION_PID:-}" ]; then
    wait "$FAKE_PUBLICATION_PID"
  fi
  handoff="$(
    find "$FAKE_CASE/session/files" -name 'self-compact-*.handoff' \
      -print -quit
  )"
  if [ -n "$handoff" ]; then
    case "${FAKE_HANDOFF_MUTATION:-}" in
      '') ;;
      wrong-token)
        printf '%s\n%s\n%s\n' \
          wrong-lock-token "$(sed -n '2p' "$handoff")" \
          "$(sed -n '3p' "$handoff")" > "$handoff"
        ;;
      wrong-call-id)
        printf '%s\n%s\n%s\n' \
          "$(sed -n '1p' "$handoff")" wrong-call-id \
          "$(sed -n '3p' "$handoff")" > "$handoff"
        ;;
      extra-line)
        printf '%s\n' extra-line >> "$handoff"
        ;;
      *)
        fail "unexpected fake handoff mutation: $FAKE_HANDOFF_MUTATION"
        ;;
    esac
  fi
  if [ "${FAKE_REMOVE_HANDOFF_BEFORE_COMPLETION:-0}" = 1 ]; then
    find "$FAKE_CASE/session/files" -name 'self-compact-*.handoff' -delete
  fi
  if [ -n "${FAKE_BEFORE_HELPER_COMPLETION_EVENTS:-}" ]; then
    cat "$FAKE_BEFORE_HELPER_COMPLETION_EVENTS" \
      >> "$FAKE_CASE/session/events.jsonl"
  fi
  printf '%s\n' \
    "{\"agentId\":null,\"type\":\"tool.execution_complete\",\"data\":{\"toolCallId\":\"$FAKE_TOOL_CALL_ID\",\"result\":{\"content\":\"test foreground exit $status\"}}}" \
    >> "$FAKE_CASE/session/events.jsonl"
  if [ -n "${FAKE_AFTER_HELPER_COMPLETION_EVENTS:-}" ]; then
    cat "$FAKE_AFTER_HELPER_COMPLETION_EVENTS" \
      >> "$FAKE_CASE/session/events.jsonl"
  fi
  if [ -n "${FAKE_FOREGROUND_CLOSURE_CONTENT:-}" ]; then
    CONTENT="$FAKE_FOREGROUND_CLOSURE_CONTENT" /usr/bin/perl -MJSON::PP -e '
      print encode_json({
        agentId => undef,
        type => "assistant.message",
        data => {content => $ENV{CONTENT}, toolRequests => []}
      }), "\n"
    ' >> "$FAKE_CASE/session/events.jsonl"
  fi
  if [ "${FAKE_TASK_COMPLETE_BEFORE_TURN_END:-0}" = 1 ]; then
    printf '%s\n' '{"agentId":null,"type":"session.task_complete"}' \
      >> "$FAKE_CASE/session/events.jsonl"
  fi
  printf '%s\n' '{"agentId":null,"type":"assistant.turn_end"}' \
    >> "$FAKE_CASE/session/events.jsonl"
  if [ "${FAKE_SUBAGENT_AFTER_TURN_END:-0}" = 1 ]; then
    printf '%s\n' \
      '{"agentId":"subagent-1","type":"assistant.turn_start"}' \
      '{"agentId":"subagent-1","type":"tool.execution_start","data":{"toolCallId":"sub-tool","toolName":"bash"}}' \
      '{"agentId":"subagent-1","type":"tool.execution_complete","data":{"toolCallId":"sub-tool"}}' \
      '{"agentId":"subagent-1","type":"assistant.turn_end"}' \
      >> "$FAKE_CASE/session/events.jsonl"
  fi
  if [ "${FAKE_CLOSURE_TURN:-0}" = 1 ]; then
    printf '%s\n' \
      '{"agentId":null,"type":"assistant.turn_start"}' \
      '{"agentId":null,"type":"assistant.message","data":{"content":"closing narration","toolRequests":[]}}' \
      '{"agentId":null,"type":"assistant.turn_end"}' \
      >> "$FAKE_CASE/session/events.jsonl"
  fi
  return "$status"
}

run_submit() {
  append_brief_turn \
    $'SELF_COMPACT_BRIEF\nKeep: active baton\nDrop: resolved detail\nAfter compaction: continue the task and do not compact again'
  run_submit_command
}

append_brief_turn() {
  local content="$1"
  CONTENT="$content" HELPER_PATH="$SCRIPT_DIR/submit-compact.sh" \
    TOOL_CALL_ID="$FAKE_TOOL_CALL_ID" /usr/bin/perl -MJSON::PP -e '
    my $content = $ENV{CONTENT};
    print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
    print encode_json({
      agentId => undef,
      type => "assistant.message",
      data => {
        content => $content,
        toolRequests => [{
          toolCallId => $ENV{TOOL_CALL_ID},
          name => "bash",
          arguments => {command => "\"" . $ENV{HELPER_PATH} . "\""}
        }]
      }
    }), "\n";
  ' >> "$FAKE_CASE/session/events.jsonl"
}

append_brief_turn_variant() {
  local mode="$1"
  local content="$2"
  MODE="$mode" CONTENT="$content" HELPER_PATH="$SCRIPT_DIR/submit-compact.sh" \
    TOOL_CALL_ID="$FAKE_TOOL_CALL_ID" /usr/bin/perl -MJSON::PP -e '
    my ($mode, $content, $helper, $call_id) =
      @ENV{qw(MODE CONTENT HELPER_PATH TOOL_CALL_ID)};
    my $canonical = {
      toolCallId => $call_id,
      name => "bash",
      arguments => {command => "\"" . $helper . "\""}
    };
    my @messages = ({
      agentId => undef,
      type => "assistant.message",
      data => {content => $content, toolRequests => [$canonical]}
    });
    if ($mode eq "duplicate-request") {
      push @messages, {
        agentId => undef,
        type => "assistant.message",
        data => {content => "", toolRequests => [$canonical]}
      };
    } elsif ($mode eq "batched-request") {
      push @{$messages[0]{data}{toolRequests}}, {
        toolCallId => "call-other-tool",
        name => "bash",
        arguments => {command => "printf other"}
      };
    } elsif ($mode eq "noncanonical-command") {
      $messages[0]{data}{toolRequests}[0]{arguments}{command} =
        "\"" . $helper . "\" --unexpected";
    } elsif ($mode eq "portable-command") {
      $messages[0]{data}{toolRequests}[0]{arguments}{command} =
        q{"$HOME/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh"};
    } elsif ($mode eq "portable-composed-command") {
      $messages[0]{data}{toolRequests}[0]{arguments}{command} =
        q{"$HOME/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh" && true};
    } elsif ($mode eq "portable-requoted-command") {
      $messages[0]{data}{toolRequests}[0]{arguments}{command} =
        q{"${HOME}/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh"};
    } else {
      die "unknown brief turn variant: $mode\n"
        unless $mode eq "canonical";
    }
    print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
    print encode_json($_), "\n" for @messages;
  ' >> "$FAKE_CASE/session/events.jsonl"
}

setup_portable_helper() {
  FAKE_PORTABLE_HOME="$FAKE_CASE/home"
  portable_parent="$FAKE_PORTABLE_HOME/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact"
  mkdir -p "$portable_parent"
  ln -s "$SCRIPT_DIR" "$portable_parent/scripts"
  FAKE_PORTABLE_HELPER="$portable_parent/scripts/submit-compact.sh"
  export FAKE_PORTABLE_HOME FAKE_PORTABLE_HELPER
}

write_event_hook() {
  local variable_name="$1"
  shift
  local path="$FAKE_CASE/$variable_name.jsonl"
  printf '%s\n' "$@" > "$path"
  printf -v "$variable_name" '%s' "$path"
  export "$variable_name"
}

append_split_brief_turn() {
  local content="$1"
  CONTENT="$content" HELPER_PATH="$SCRIPT_DIR/submit-compact.sh" \
    TOOL_CALL_ID="$FAKE_TOOL_CALL_ID" /usr/bin/perl -MJSON::PP -e '
    print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
    print encode_json({
      agentId => undef,
      type => "assistant.message",
      data => {content => $ENV{CONTENT}, toolRequests => []}
    }), "\n";
    print encode_json({
      agentId => undef,
      type => "assistant.message",
      data => {
        content => "",
        toolRequests => [{
          toolCallId => $ENV{TOOL_CALL_ID},
          name => "bash",
          arguments => {command => "\"" . $ENV{HELPER_PATH} . "\""}
        }]
      }
    }), "\n";
  ' >> "$FAKE_CASE/session/events.jsonl"
}

wait_for_watcher_log() {
  local pattern="$1"
  local log=""
  for _ in $(seq 1 400); do
    log="$(
      find "$FAKE_CASE/session/files" -name 'self-compact-*.log' \
        -print -quit 2>/dev/null
    )"
    [ -n "$log" ] && grep -qE "$pattern" "$log" 2>/dev/null && {
      printf '%s\n' "$log"
      return 0
    }
    sleep 0.02
  done
  find "$FAKE_CASE/session/files" -name 'self-compact-*.log' -type f \
    -exec sh -c 'echo "--- $1"; tail -n 40 "$1"' _ {} \; >&2 || true
  echo "--- events" >&2
  tail -n 40 "$FAKE_CASE/session/events.jsonl" >&2 || true
  echo "--- run-shell" >&2
  cat "$FAKE_RUN_SHELL_COMMAND" >&2 || true
  fail "timed out waiting for watcher log pattern [$pattern]"
}

assert_authorization_rejected() {
  local pattern="$1"
  local status=0
  run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
    status=$?
  [ "$status" -eq 0 ] ||
    fail "foreground did not arm the rejecting verifier"
  wait_for_watcher_log "$pattern" >/dev/null
  wait_for_path_absent "$FAKE_CASE/session/files/self-compact.lock"
  assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
  grep -q '^NOTICE:self-compact cancelled:' "$FAKE_TMUX_ACTIONS" ||
    fail "authorization rejection did not emit a visible cancellation notice"
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
[ ! -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "invalid-locale foreground failure acquired the session lock"

: > "$FAKE_CASE/ready"
: > "$FAKE_CASE/armed"
mkdir "$FAKE_CASE/lock"
printf '%s\n' test-lock > "$FAKE_CASE/lock/token"
status=0
(
  export PATH="$invalid_locale_bin:$PATH"
  export SELF_COMPACT_LOCALE=definitely-invalid
  "$SCRIPT_DIR/resume-after-compact.sh" \
    "%1" "$FAKE_WORKSPACE" 1 "$FAKE_CASE/ready" "$FAKE_CASE/armed" \
    "$FAKE_CASE/cancelled" "$FAKE_CASE/handoff" "0123abcd" \
    "Compaction done; resume, do not compact." \
    "$FAKE_BIN/tmux" "/compact Use SELF_COMPACT_BRIEF. B:0123abcd" \
    "Use SELF_COMPACT_BRIEF. B:0123abcd" "$FAKE_CASE/lock" test-lock \
    call-test "$SCRIPT_DIR/submit-compact.sh" "$FAKE_CASE/watcher.log" 25 1 0.1
) > "$FAKE_CASE/watcher.out" 2> "$FAKE_CASE/watcher.err" || status=$?
[ "$status" -ne 0 ] || fail "invalid-locale watcher unexpectedly continued"
grep -q 'could not verify a UTF-8 locale; input state remains unknown' \
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

# The protocol submitter never retries a known mismatched or menu-bearing
# command. One literal paste is the complete typing budget.
setup_case normal-path-menu
export FAKE_APPEND_ON_TYPE=" menu draft"
export FAKE_APPEND_ON_TYPE_COUNT=1
export FAKE_MENU_ON_TYPE_COUNT=1
export FAKE_ESC_CLOSE_AFTER=2
status=0
SELF_COMPACT_RECOVERY_DELAY_SECONDS=0.01 run_submit || status=$?
wait_for_watcher_log 'compact command rendered with a known mismatch' >/dev/null
assert_count 0 '^KEY:C-u:|^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

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

# The helper authorizes only a structurally complete brief in the current
# assistant message content.
assert_brief_rejected() {
  local name="$1"
  local content="$2"
  setup_case "$name"
  append_brief_turn "$content"
  status=0
  run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
    status=$?
  [ "$status" -eq 0 ] || fail "$name foreground did not arm the verifier"
  wait_for_watcher_log 'bound assistant turn has no complete SELF_COMPACT_BRIEF' \
    >/dev/null
  assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
  wait_for_path_absent "$FAKE_CASE/session/files/self-compact.lock"
}

setup_case current-turn-brief-missing
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -eq 0 ] || fail "missing-brief foreground did not arm verifier"
wait_for_watcher_log 'timed out waiting for persisted brief authorization' \
  >/dev/null
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case current-turn-brief-delayed-visibility
(
  for _ in $(seq 1 200); do
    find "$FAKE_CASE/session/files" -name 'self-compact-*.handoff' -print -quit |
      grep -q . && break
    sleep 0.002
  done
  CONTENT=$'SELF_COMPACT_BRIEF\nKeep: delayed baton\nDrop: resolved detail\nAfter compaction: continue and do not compact again' \
    HELPER_PATH="$SCRIPT_DIR/submit-compact.sh" \
    TOOL_CALL_ID="$FAKE_TOOL_CALL_ID" \
    /usr/bin/perl -MJSON::PP -e '
      print encode_json({agentId => undef, type => "assistant.turn_start"}), "\n";
      print encode_json({
        agentId => undef,
        type => "assistant.message",
        data => {
          content => $ENV{CONTENT},
          toolRequests => [{
            toolCallId => $ENV{TOOL_CALL_ID},
            name => "bash",
            arguments => {command => "\"" . $ENV{HELPER_PATH} . "\""}
          }]
        }
      }), "\n"
    ' > "$FAKE_CASE/session/events.jsonl.next"
  cat "$FAKE_CASE/session/events.jsonl" \
    >> "$FAKE_CASE/session/events.jsonl.next"
  mv "$FAKE_CASE/session/events.jsonl.next" \
    "$FAKE_CASE/session/events.jsonl"
) &
FAKE_PUBLICATION_PID=$!
export FAKE_PUBLICATION_PID
printf '%s\n' "$FAKE_PUBLICATION_PID" >> "$FAKE_BACKGROUND_PIDS"
run_submit_command >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case split-brief-and-tool-message
append_split_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: split event baton\nDrop: resolved detail\nAfter compaction: continue and do not compact again'
run_submit_command >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case same-turn-closing-narration
export FAKE_FOREGROUND_CLOSURE_CONTENT="foreground helper returned"
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case direct-task-complete-turn-end
export FAKE_TASK_COMPLETE_BEFORE_TURN_END=1
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case separate-tool-free-closure-turn
export FAKE_CLOSURE_TURN=1
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case subagent-events-ignored
printf '%s\n' \
  '{"agentId":"subagent-1","type":"tool.execution_start","data":{"toolCallId":"old-sub-tool","toolName":"bash"}}' \
  >> "$FAKE_CASE/session/events.jsonl"
export FAKE_SUBAGENT_AFTER_TURN_END=1
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case positive-handoff-required
export FAKE_REMOVE_HANDOFF_BEFORE_COMPLETION=1
run_submit >/dev/null
wait_for_watcher_log 'timed out waiting for persisted brief authorization' \
  >/dev/null
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case current-turn-brief-large-history
awk 'BEGIN {
  payload = sprintf("%1024s", "")
  gsub(/ /, "x", payload)
  for (i = 1; i <= 20000; i++)
    print "{\"type\":\"tool.execution_complete\",\"data\":{\"content\":\"" payload "\"}}"
}' >> "$FAKE_CASE/session/events.jsonl"
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: large history baton\nDrop: resolved detail\nAfter compaction: continue and do not compact again'
mkdir "$FAKE_CASE/session/files/self-compact.lock"
printf '%s\n' watcher-owned \
  > "$FAKE_CASE/session/files/self-compact.lock/state"
brief_started="$(/usr/bin/perl -MTime::HiRes=time -e 'printf "%.0f\n", time() * 1000')"
status=0
SELF_COMPACT_AUTH_WAIT_SECONDS=0.5 \
  run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
brief_finished="$(/usr/bin/perl -MTime::HiRes=time -e 'printf "%.0f\n", time() * 1000')"
[ "$status" -ne 0 ] || fail "large-history lock unexpectedly allowed submission"
grep -q 'another or ambiguous self-compact run owns' "$FAKE_CASE/submit.err"
[ "$((brief_finished - brief_started))" -lt 2000 ] ||
  fail "candidate call-ID discovery exceeded two seconds on a 20,000-line history"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case bounded-authorization-large-history
awk 'BEGIN {
  payload = sprintf("%256s", "")
  gsub(/ /, "x", payload)
  for (i = 1; i <= 250; i++) {
    if (i % 2)
      print "{\"agentId\":null,\"type\":\"tool.execution_complete\",\"data\":{\"toolCallId\":\"old-" i "\",\"content\":\"" payload "\"}}"
    else
      print "{\"agentId\":\"subagent-history\",\"type\":\"assistant.message\",\"data\":{\"content\":\"" payload "\"}}"
  }
}' >> "$FAKE_CASE/session/events.jsonl"
authorization_started="$(/usr/bin/perl -MTime::HiRes=time -e 'printf "%.0f\n", time() * 1000')"
SELF_COMPACT_AUTH_SCAN_BYTES=262144 run_submit >/dev/null
wait_for_pattern '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
authorization_finished="$(/usr/bin/perl -MTime::HiRes=time -e 'printf "%.0f\n", time() * 1000')"
authorization_elapsed=$((authorization_finished - authorization_started))
[ "$authorization_elapsed" -lt 20000 ] ||
  fail "bounded authorization took ${authorization_elapsed}ms on a 250-event history"
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case older-turn-brief-rejected
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: old baton\nDrop: old detail\nAfter compaction: continue and do not compact again'
FAKE_TOOL_CALL_ID="call-current-turn-test"
printf '%s\n' '{"type":"assistant.turn_start"}' \
  >> "$FAKE_CASE/session/events.jsonl"
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -eq 0 ] || fail "older-turn foreground did not arm verifier"
wait_for_watcher_log 'timed out waiting for persisted brief authorization' \
  >/dev/null
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

assert_brief_rejected assistant-bare-mention \
  $'I will emit SELF_COMPACT_BRIEF later, not now.'
assert_brief_rejected missing-keep-content \
  $'SELF_COMPACT_BRIEF\nKeep:\nDrop: detail\nAfter compaction: continue and do not compact again'
assert_brief_rejected keep-content-moved-off-label \
  $'SELF_COMPACT_BRIEF\nKeep:\ncontinued baton\nDrop: detail\nAfter compaction: continue and do not compact again'
assert_brief_rejected missing-literal \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: never initiate another compact'
assert_brief_rejected no-recompact-literal-moved-off-label \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: continue\nand do not compact again'

brief_content=$'SELF_COMPACT_BRIEF\nKeep: authorization identity baton\nDrop: resolved detail\nAfter compaction: continue and do not compact again'

setup_case duplicate-helper-request-identity
append_brief_turn_variant duplicate-request "$brief_content"
assert_authorization_rejected 'duplicate helper request identity'

setup_case helper-request-batched-with-tool
append_brief_turn_variant batched-request "$brief_content"
assert_authorization_rejected 'helper request was batched with another tool'

setup_case matching-call-id-noncanonical-command
append_brief_turn_variant noncanonical-command "$brief_content"
assert_authorization_rejected \
  'helper request was not the canonical zero-argument command'

setup_case portable-installed-helper-command
setup_portable_helper
append_brief_turn_variant portable-command "$brief_content"
HOME="$FAKE_PORTABLE_HOME" FAKE_SUBMIT_SCRIPT="$FAKE_PORTABLE_HELPER" \
  run_submit_command >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case portable-installed-helper-composition-rejected
setup_portable_helper
append_brief_turn_variant portable-composed-command "$brief_content"
HOME="$FAKE_PORTABLE_HOME" FAKE_SUBMIT_SCRIPT="$FAKE_PORTABLE_HELPER" \
  assert_authorization_rejected \
    'helper request was not the canonical zero-argument command'

setup_case portable-installed-helper-requoting-rejected
setup_portable_helper
append_brief_turn_variant portable-requoted-command "$brief_content"
HOME="$FAKE_PORTABLE_HOME" FAKE_SUBMIT_SCRIPT="$FAKE_PORTABLE_HELPER" \
  assert_authorization_rejected \
    'helper request was not the canonical zero-argument command'

for handoff_case in wrong-token wrong-call-id extra-line; do
  setup_case "handoff-$handoff_case"
  append_brief_turn "$brief_content"
  export FAKE_HANDOFF_MUTATION="$handoff_case"
  SELF_COMPACT_AUTH_WAIT_SECONDS=0.15 \
    assert_authorization_rejected \
      'timed out waiting for persisted brief authorization'
done

# The watcher must retain positive handoff ownership through the last
# read-only checks before it changes the editor.
setup_case handoff-removed-after-positive-observation
append_brief_turn "$brief_content"
export FAKE_REMOVE_HANDOFF_ON_PANE_WIDTH_COUNT=2
assert_authorization_rejected 'positive handoff was lost'
assert_count 1 '^HOOK:removed-handoff-at-pane-width:2$' "$FAKE_TMUX_ACTIONS"

# Root identity is parsed semantically: insignificant JSON whitespace is
# accepted, while a nested agentId cannot disguise new root activity.
setup_case root-agent-id-whitespace
append_brief_turn "$brief_content"
/usr/bin/perl -pi -e 's/"agentId":null/"agentId" : null/g' \
  "$FAKE_CASE/session/events.jsonl"
run_submit_command >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case nested-agent-id-does-not-hide-root-activity
append_brief_turn "$brief_content"
printf '%s\n' \
  '{"agentId":null,"type":"user.message","data":{"agentId":"nested-agent"},"content":"root user won"}' \
  > "$FAKE_CASE/pane-width-events.jsonl"
export FAKE_PANE_WIDTH_EVENTS="$FAKE_CASE/pane-width-events.jsonl"
export FAKE_APPEND_EVENTS_ON_PANE_WIDTH_COUNT=2
assert_authorization_rejected 'root-agent activity started before compact preparation'
assert_count 1 '^HOOK:appended-events-at-pane-width:2$' "$FAKE_TMUX_ACTIONS"

setup_case malformed-json-in-authorization-region
append_brief_turn "$brief_content"
write_event_hook FAKE_BEFORE_HELPER_COMPLETION_EVENTS \
  '{"agentId":null,"type":"assistant.message","data":'
assert_authorization_rejected 'malformed.*JSON.*authorization'
grep -Eq '^NOTICE:self-compact cancelled: .*malformed.*JSON.*authorization' \
  "$FAKE_TMUX_ACTIONS" ||
  fail "malformed authorization JSON did not produce a visible diagnostic"

# Root activity conflicts in either gap around the helper execution and after
# completion. None may reach editor preparation.
setup_case root-user-between-request-and-start
append_brief_turn "$brief_content"
write_event_hook FAKE_BEFORE_HELPER_START_EVENTS \
  '{"agentId":null,"type":"user.message","content":"root user conflict"}'
assert_authorization_rejected 'user activity|root.*activity|conflict'

setup_case root-tool-between-request-and-start
append_brief_turn "$brief_content"
write_event_hook FAKE_BEFORE_HELPER_START_EVENTS \
  '{"agentId":null,"type":"tool.execution_start","data":{"toolCallId":"conflicting-tool","toolName":"bash"}}'
assert_authorization_rejected 'root.*tool|root.*activity|conflict'

setup_case root-user-between-start-and-completion
append_brief_turn "$brief_content"
write_event_hook FAKE_BEFORE_HELPER_COMPLETION_EVENTS \
  '{"agentId":null,"type":"user.message","content":"root user conflict"}'
assert_authorization_rejected 'user activity|root.*activity|conflict'

setup_case root-tool-between-start-and-completion
append_brief_turn "$brief_content"
write_event_hook FAKE_BEFORE_HELPER_COMPLETION_EVENTS \
  '{"agentId":null,"type":"tool.execution_start","data":{"toolCallId":"conflicting-tool","toolName":"bash"}}'
assert_authorization_rejected 'root.*tool|root.*activity|conflict'

setup_case root-user-after-completion
append_brief_turn "$brief_content"
write_event_hook FAKE_AFTER_HELPER_COMPLETION_EVENTS \
  '{"agentId":null,"type":"user.message","content":"root user conflict"}'
assert_authorization_rejected 'user activity followed|root.*activity'

setup_case root-tool-request-after-completion
append_brief_turn "$brief_content"
write_event_hook FAKE_AFTER_HELPER_COMPLETION_EVENTS \
  '{"agentId":null,"type":"assistant.message","data":{"content":"","toolRequests":[{"toolCallId":"conflicting-request","name":"bash","arguments":{"command":"printf conflict"}}]}}'
assert_authorization_rejected 'new root tool request followed'

setup_case root-tool-execution-after-completion
append_brief_turn "$brief_content"
write_event_hook FAKE_AFTER_HELPER_COMPLETION_EVENTS \
  '{"agentId":null,"type":"tool.execution_start","data":{"toolCallId":"conflicting-tool","toolName":"bash"}}'
assert_authorization_rejected 'new root tool activity followed'

setup_case second-root-turn-after-completion
append_brief_turn "$brief_content"
write_event_hook FAKE_AFTER_HELPER_COMPLETION_EVENTS \
  '{"agentId":null,"type":"assistant.turn_start"}'
assert_authorization_rejected \
  'new root assistant turn began before the authorizing turn ended'

# Equivalent subagent activity in both execution gaps is unrelated and remains
# ignored.
setup_case subagent-between-request-and-start
append_brief_turn "$brief_content"
write_event_hook FAKE_BEFORE_HELPER_START_EVENTS \
  '{"agentId":"subagent-gap","type":"user.message","content":"subagent work"}' \
  '{"agentId":"subagent-gap","type":"tool.execution_start","data":{"toolCallId":"sub-tool","toolName":"bash"}}'
run_submit_command >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case subagent-between-start-and-completion
append_brief_turn "$brief_content"
write_event_hook FAKE_BEFORE_HELPER_COMPLETION_EVENTS \
  '{"agentId":"subagent-gap","type":"user.message","content":"subagent work"}' \
  '{"agentId":"subagent-gap","type":"tool.execution_start","data":{"toolCallId":"sub-tool","toolName":"bash"}}'
run_submit_command >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case no-current-root-bash-start
append_brief_turn "$brief_content"
export FAKE_SKIP_HELPER_START=1
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] ||
  fail "missing current root Bash start unexpectedly launched a watcher"
grep -q 'could not identify the current root-agent Bash tool call' \
  "$FAKE_CASE/submit.err"
[ ! -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "call-ID discovery failure acquired the session lock"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case authorization-wait-out-of-range
status=0
SELF_COMPACT_AUTH_WAIT_SECONDS=3600 \
  run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] || fail "out-of-range authorization wait was accepted"
grep -q 'AUTH_WAIT_SECONDS must be greater than zero and at most 30 seconds' \
  "$FAKE_CASE/submit.err"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
[ ! -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "out-of-range authorization wait acquired the session lock"

setup_case authorization-shorter-than-quiescence
append_brief_turn "$brief_content"
status=0
SELF_COMPACT_AUTH_WAIT_SECONDS=0.1 \
  SELF_COMPACT_QUIESCENCE_GRACE_SECONDS=0.2 \
  run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] ||
  fail "authorization wait shorter than quiescence was accepted"
grep -Eq 'AUTH_WAIT_SECONDS.*greater than.*QUIESCENCE_GRACE_SECONDS|QUIESCENCE_GRACE_SECONDS.*less than.*AUTH_WAIT_SECONDS' \
  "$FAKE_CASE/submit.err"
[ ! -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "invalid authorization/quiescence relation acquired the session lock"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case direct-quiescence-out-of-range
direct_lock="$FAKE_CASE/direct.lock"
mkdir "$direct_lock"
printf '%s\n' direct-lock-token > "$direct_lock/token"
status=0
"$SCRIPT_DIR/resume-after-compact.sh" \
  "%1" "$FAKE_WORKSPACE" 1 "$FAKE_CASE/direct.ready" \
  "$FAKE_CASE/direct.armed" "$FAKE_CASE/direct.cancelled" \
  "$FAKE_CASE/direct.handoff" 0123abcd \
  "Compaction done; resume, do not compact." "$FAKE_BIN/tmux" \
  "/compact Use SELF_COMPACT_BRIEF. B:0123abcd" \
  "Use SELF_COMPACT_BRIEF. B:0123abcd" "$direct_lock" direct-lock-token \
  call-direct "$SCRIPT_DIR/submit-compact.sh" "$FAKE_CASE/direct.log" \
  25 1 31 > "$FAKE_CASE/direct.out" 2> "$FAKE_CASE/direct.err" ||
  status=$?
[ "$status" -ne 0 ] || fail "direct watcher accepted out-of-range quiescence"
grep -q 'invalid quiescence grace' "$FAKE_CASE/direct.err"
grep -q '^NOTICE:self-compact cancelled: invalid quiescence grace;' \
  "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
[ ! -d "$direct_lock" ] ||
  fail "direct invalid-quiescence watcher left its foreground lock"

setup_case tool-argument-mention
CONTENT='ordinary assistant content' /usr/bin/perl -MJSON::PP -e '
  print encode_json({type => "assistant.turn_start"}), "\n";
  print encode_json({
    type => "assistant.message",
    data => {
      content => $ENV{CONTENT},
      toolRequests => [{
        name => "bash",
        arguments => {
          command => "SELF_COMPACT_BRIEF Keep: fake Drop: fake After compaction: do not compact again"
        }
      }]
    }
  }), "\n";
' >> "$FAKE_CASE/session/events.jsonl"
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -eq 0 ] || fail "tool-argument foreground did not arm verifier"
wait_for_watcher_log 'timed out waiting for persisted brief authorization' \
  >/dev/null
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

# The timed fallback is compact-only and available only from a genuinely empty
# editor with no visible or hidden draft observed during preparation.
setup_case timed-fallback-empty-editor
export FAKE_CAPTURE_MODE_ON_TYPE=unreadable
export FAKE_CAPTURE_MODE_ON_TYPE_COUNT=1
export FAKE_POST_COMPACT_MODE=readable
printf '%s\n' 100000 100010 100011 100040 200000 220000 250000 \
  > "$FAKE_CASE/epoch-milliseconds"
export FAKE_EPOCH_MILLISECONDS_FILE="$FAKE_CASE/epoch-milliseconds"
export FAKE_EPOCH_INCREMENT_AFTER_END=1
export FAKE_EPOCH_AFTER_TYPE_COUNT=1
SELF_COMPACT_RENDER_WAIT_SECONDS=0.02 \
  SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS=20 \
  run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^TYPE:/compact Use SELF_COMPACT_BRIEF\. B:0123abcd$' \
  "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:/compact Use SELF_COMPACT_BRIEF\. B:0123abcd$' \
  "$FAKE_TMUX_ACTIONS"

setup_case timed-fallback-rejects-stashed-draft
printf '%s' "private draft" > "$FAKE_TMUX_INPUT"
export FAKE_CAPTURE_MODE_ON_TYPE=unreadable
export FAKE_CAPTURE_MODE_ON_TYPE_COUNT=1
status=0
SELF_COMPACT_RENDER_WAIT_SECONDS=0.02 \
  SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS=20 \
  run_submit > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -eq 0 ] ||
  fail "draft-bearing foreground did not arm verifier"
wait_for_watcher_log 'compact command was not exact and this run handled a draft' \
  >/dev/null
assert_count 1 '^TYPE:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case timed-fallback-wait-out-of-range
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: continue and do not compact again'
status=0
SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS=0.05 \
  run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] || fail "out-of-range ambiguous wait was accepted"
grep -q 'ambiguous render wait must be between 20 and 30 seconds' \
  "$FAKE_CASE/submit.err"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
[ ! -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "out-of-range ambiguous wait acquired the session lock"

# Session-scoped exclusion blocks live and transferred owners, while exactly
# one well-formed dead foreground owner can be reclaimed.
setup_case concurrent-helper-session-lock
mkdir "$FAKE_CASE/session/files/self-compact.lock"
printf '%s\n' other-owner > "$FAKE_CASE/session/files/self-compact.lock/token"
printf '%s\n' foreground > "$FAKE_CASE/session/files/self-compact.lock/state"
printf '%s\n' "$$" > "$FAKE_CASE/session/files/self-compact.lock/submitter.pid"
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: continue and do not compact again'
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] || fail "live lock allowed a second helper"
grep -q 'another or ambiguous self-compact run owns' "$FAKE_CASE/submit.err"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case stale-foreground-lock-reclaimed
mkdir "$FAKE_CASE/session/files/self-compact.lock"
stale_run_id="20260804T000000Z-999999"
printf '%s\n' "deadbeef-$stale_run_id" \
  > "$FAKE_CASE/session/files/self-compact.lock/token"
printf '%s\n' foreground > "$FAKE_CASE/session/files/self-compact.lock/state"
printf '%s\n' 999999 > "$FAKE_CASE/session/files/self-compact.lock/submitter.pid"
printf '%s\n' 20260804T000000Z \
  > "$FAKE_CASE/session/files/self-compact.lock/created"
printf '%s\n%s\n%s\n%s\n%s\n' \
  "$FAKE_CASE/session/files/self-compact-$stale_run_id.ready" \
  "$FAKE_CASE/session/files/self-compact-$stale_run_id.armed" \
  "$FAKE_CASE/session/files/self-compact-$stale_run_id.cancelled" \
  "$FAKE_CASE/session/files/self-compact-$stale_run_id.handoff" \
  "$FAKE_CASE/session/files/self-compact-$stale_run_id.log" \
  > "$FAKE_CASE/session/files/self-compact.lock/run-files"
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"

setup_case malformed-foreground-lock-fails-closed
mkdir "$FAKE_CASE/session/files/self-compact.lock"
printf '%s\n' deadbeef-20260804T000000Z-not-a-pid \
  > "$FAKE_CASE/session/files/self-compact.lock/token"
printf '%s\n' foreground > "$FAKE_CASE/session/files/self-compact.lock/state"
printf '%s\n' not-a-pid \
  > "$FAKE_CASE/session/files/self-compact.lock/submitter.pid"
printf '%s\n' 20260804T000000Z \
  > "$FAKE_CASE/session/files/self-compact.lock/created"
printf '%s\n' invalid > "$FAKE_CASE/session/files/self-compact.lock/run-files"
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: continue and do not compact again'
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] || fail "malformed foreground lock was reclaimed"
grep -q 'another or ambiguous self-compact run owns' "$FAKE_CASE/submit.err"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case launching-lock-fails-closed
mkdir "$FAKE_CASE/session/files/self-compact.lock"
printf '%s\n' stuck-owner > "$FAKE_CASE/session/files/self-compact.lock/token"
printf '%s\n' watcher-launching > "$FAKE_CASE/session/files/self-compact.lock/state"
printf '%s\n' 999999 > "$FAKE_CASE/session/files/self-compact.lock/submitter.pid"
: > "$FAKE_CASE/session/files/self-compact.lock/watcher-launching"
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: continue and do not compact again'
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] || fail "watcher-launching lock was reclaimed"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

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
  *"self-compact verifier armed; foreground helper complete"*) ;;
  *) fail "unexpected submit output: $output" ;;
esac
grep -qF '|| true' "$FAKE_RUN_SHELL_COMMAND"
log="$(wait_for_watcher_log 'submitted post-compact continuation')"
assert_file_equals $'LANG=unset\nLC_ALL=unset' "$FAKE_RUN_SHELL_ENV"
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"
assert_file_equals "already queued" "$FAKE_TMUX_INPUT"
grep -q 'matching compact advanced summary_count to 2 at checkpoint 2' "$log"

# The detached verifier uses the validated absolute tmux path even when tmux is
# absent from its inherited PATH.
setup_case detached-no-tmux-path
export FAKE_DETACHED_PATH=/usr/bin:/bin
export FAKE_COMPACT_MODE=success
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"

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
assert_count 1 '^TYPE:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:C-u:' "$FAKE_TMUX_ACTIONS"
assert_count 0 '^KEY:Escape:' "$FAKE_TMUX_ACTIONS"
assert_count 0 \
  '^NOTICE:self-compact: input changed or unreadable; will clear it in 10 seconds' \
  "$FAKE_TMUX_ACTIONS"

# Hotel's 52-column pane safely fits the fixed 43-column token-bearing control
# without shortening the long assistant-side brief.
setup_case hotel-long-brief-narrow-pane
printf '%s\n' "52 40" > "$FAKE_GEOMETRY"
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^TYPE:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^TYPE:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"
one_row_command="$(grep '^TYPE:/compact ' "$FAKE_TMUX_ACTIONS" | sed 's/^TYPE://')"
[ "${#one_row_command}" -eq 43 ] ||
  fail "fixed compact command used ${#one_row_command} columns instead of 43"
grep -Fqx "KEY:Enter:$one_row_command" "$FAKE_TMUX_ACTIONS" ||
  fail "exact one-row compact did not receive its single Enter"
checkpoint="$FAKE_CASE/session/checkpoints/002-test.md"
grep -q 'checkpoint without identity prose' "$checkpoint" ||
  fail "checkpoint-without-marker lifecycle did not land"

# The old positional steer is a hard error before workspace or editor mutation.
setup_case positional-steer-retired
status=0
run_submit_command "Keep: old inline steer" \
  > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -eq 2 ] || fail "positional steer did not return usage status 2"
grep -q 'inline steers and --continuation are retired' "$FAKE_CASE/submit.err"
[ ! -s "$FAKE_RUN_SHELL_COMMAND" ] ||
  fail "positional steer launched a watcher"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

# Caller-selected continuation and unknown options are also hard errors.
setup_case continuation-retired
status=0
run_submit_command --continuation "continue" \
  > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -eq 2 ] || fail "--continuation did not return usage status 2"
grep -q 'inline steers and --continuation are retired' "$FAKE_CASE/submit.err"
[ ! -s "$FAKE_RUN_SHELL_COMMAND" ] ||
  fail "--continuation launched a watcher"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

setup_case unknown-option
status=0
run_submit_command --unknown \
  > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" || status=$?
[ "$status" -eq 2 ] || fail "unknown option did not return usage status 2"
[ ! -s "$FAKE_RUN_SHELL_COMMAND" ] || fail "unknown option launched a watcher"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

# Start-grace validation is a foreground precondition: invalid input cannot
# reach Enter or transfer ownership to a watcher.
setup_case invalid-start-grace
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: continue and do not compact again'
status=0
SELF_COMPACT_START_GRACE_SECONDS=not-a-duration \
  run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] || fail "invalid start grace unexpectedly armed a watcher"
grep -Eq 'START_GRACE_SECONDS|start grace' "$FAKE_CASE/submit.err"
assert_count 0 '^KEY:C-s$|^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"
[ ! -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "invalid start grace left a session lock"

# A compaction start before assistant.turn_end is also accepted.
setup_case start-before-end
printf '%s' "hidden lifecycle draft" > "$FAKE_TMUX_STASH"
export FAKE_COMPACT_MODE=start-before-end
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"
assert_file_equals "hidden lifecycle draft" "$FAKE_TMUX_INPUT"

# A start written by the deadline clock call itself is accepted by the final
# event recheck instead of being lost at the exact boundary.
setup_case start-at-exact-deadline
export FAKE_COMPACT_MODE=no-start-keep
export FAKE_EPOCH_EXACT_DEADLINE_ARMED="$FAKE_CASE/session/files/self-compact.lock/armed"
export FAKE_EPOCH_EVENTS="$FAKE_CASE/session/events.jsonl"
run_submit >/dev/null
wait_for_watcher_log 'submitted post-compact continuation' >/dev/null
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' \
  "$FAKE_TMUX_ACTIONS"

# Activity already present immediately after the matching compact completion
# suppresses continuation preparation entirely.
setup_case preexisting-post-compact-activity
export FAKE_COMPACT_MODE=success
export FAKE_POST_COMPACT_PREEXISTING_ACTIVITY=1
run_submit >/dev/null
wait_for_watcher_log \
  'post-compact activity already present.*continuation not needed' >/dev/null
assert_count 0 '^TYPE:Compaction done;|^KEY:Enter:Compaction done;' \
  "$FAKE_TMUX_ACTIONS"
wait_for_path_absent "$FAKE_CASE/session/files/self-compact.lock"

# An untrapped watcher death after ARMED strands the watcher-owned lock, so a
# second helper cannot queue another compact.
setup_case post-enter-watcher-death-lock
mkdir "$FAKE_CASE/session/files/self-compact.lock"
printf '%s\n' post-enter-lock \
  > "$FAKE_CASE/session/files/self-compact.lock/token"
printf '%s\n' watcher-owned \
  > "$FAKE_CASE/session/files/self-compact.lock/state"
: > "$FAKE_CASE/session/files/self-compact.lock/armed"
printf '%s\n' 999999 \
  > "$FAKE_CASE/session/files/self-compact.lock/watcher.pid"
append_brief_turn \
  $'SELF_COMPACT_BRIEF\nKeep: baton\nDrop: detail\nAfter compaction: continue and do not compact again'
status=0
run_submit_command > "$FAKE_CASE/submit.out" 2> "$FAKE_CASE/submit.err" ||
  status=$?
[ "$status" -ne 0 ] ||
  fail "post-Enter watcher death released the stranded lock"
grep -q 'another or ambiguous self-compact run owns' "$FAKE_CASE/submit.err"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "stranded watcher lock was removed"
assert_count 0 '^TYPE:|^KEY:Enter:' "$FAKE_TMUX_ACTIONS"

# Exercise the real watcher EXIT trap after it has crossed ARMED. A signal
# cannot make that watcher-owned exclusion look safely reclaimable.
setup_case real-watcher-trap-after-armed
export FAKE_COMPACT_MODE=no-start-keep
SELF_COMPACT_START_GRACE_SECONDS=2 run_submit >/dev/null
wait_for_path "$FAKE_CASE/session/files/self-compact.lock/armed"
assert_file_equals watcher-owned \
  "$FAKE_CASE/session/files/self-compact.lock/state"
watcher_pid="$(cat "$FAKE_CASE/session/files/self-compact.lock/watcher.pid")"
kill "$watcher_pid"
wait_for_process_exit "$watcher_pid"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "ARMED watcher trap released the watcher-owned lock"
status=0
run_submit > "$FAKE_CASE/competing.out" 2> "$FAKE_CASE/competing.err" ||
  status=$?
[ "$status" -ne 0 ] ||
  fail "competing helper acquired a lock stranded by an ARMED watcher"
grep -q 'another or ambiguous self-compact run owns' \
  "$FAKE_CASE/competing.err"

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

# A nonzero Enter result is ambiguous: hold exclusion through the start
# deadline, then release only after proving no compact started.
setup_case enter-error-no-start
export FAKE_ENTER_STATUS=1
SELF_COMPACT_START_GRACE_SECONDS=1.5 run_submit >/dev/null
log="$(wait_for_watcher_log \
  'compact Enter returned nonzero; observing the compaction-start deadline')"
[ -d "$FAKE_CASE/session/files/self-compact.lock" ] ||
  fail "nonzero Enter released the lock before the start deadline"
unset FAKE_ENTER_STATUS
status=0
run_submit > "$FAKE_CASE/competing.out" 2> "$FAKE_CASE/competing.err" ||
  status=$?
[ "$status" -ne 0 ] ||
  fail "competing helper acquired the lock during ambiguous Enter delivery"
grep -q 'another or ambiguous self-compact run owns' \
  "$FAKE_CASE/competing.err"
log="$(wait_for_watcher_log 'compaction did not start within')"
grep -q 'compact Enter returned nonzero; observing the compaction-start deadline' "$log"
assert_file_equals "" "$FAKE_TMUX_INPUT"
wait_for_path_absent "$FAKE_CASE/session/files/self-compact.lock"

# A nonzero Enter result may still mean the key was delivered. Follow the
# matching lifecycle instead of releasing exclusion or queuing another compact.
setup_case enter-error-delivered
export FAKE_ENTER_STATUS=1
export FAKE_ENTER_DELIVERED=1
export FAKE_COMPACT_MODE=success
run_submit >/dev/null
log="$(wait_for_watcher_log 'submitted post-compact continuation')"
grep -q 'compact Enter returned nonzero; observing the compaction-start deadline' "$log"
assert_count 1 '^KEY:Enter:/compact ' "$FAKE_TMUX_ACTIONS"
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' "$FAKE_TMUX_ACTIONS"

# A continuation Enter error is recoverable: clean only the exact continuation
# and release the lock rather than stranding either.
setup_case continuation-enter-error
export FAKE_COMPACT_MODE=success
export FAKE_CONTINUATION_ENTER_STATUS=1
run_submit >/dev/null
wait_for_pattern '^TYPE:Compaction done; resume, do not compact\.$' \
  "$FAKE_TMUX_ACTIONS"
wait_for_path_absent "$FAKE_CASE/session/files/self-compact.lock"
assert_file_equals "" "$FAKE_TMUX_INPUT"
assert_count 1 '^KEY:Enter:Compaction done; resume, do not compact\.$' \
  "$FAKE_TMUX_ACTIONS"

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
wait_for_watcher_log 'first compact completion did not match this run token or failed' \
  >/dev/null
assert_count 0 '^TYPE:Compaction done;|^KEY:Enter:Compaction done;' "$FAKE_TMUX_ACTIONS"

# The first completion after the observed start owns the verdict. A later
# matching token cannot rescue an earlier mismatched compact.
setup_case first-completion-after-start-wins
export FAKE_COMPACT_MODE=mismatched-then-matching
run_submit >/dev/null
wait_for_watcher_log 'first compact completion did not match this run token or failed' \
  >/dev/null
assert_count 0 '^TYPE:Compaction done;|^KEY:Enter:Compaction done;' \
  "$FAKE_TMUX_ACTIONS"

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
assert_count 0 '^TYPE:Compaction done;|^KEY:Enter:Compaction done;' "$FAKE_TMUX_ACTIONS"
grep -q '"type":"assistant.turn_end"' "$FAKE_CASE/session/events.jsonl"

# Activity after continuation typing is caught by render polling. A second
# captured row prevents cleanup ownership as well as Enter ownership.
setup_case post-compact-enter-race
export FAKE_COMPACT_MODE=success
split_continuation="Compaction done; resume, do not compact."
export FAKE_CAPTURE_SPLIT_COLUMNS=20
export FAKE_CAPTURE_SPLIT_TYPE_COUNT=2
export FAKE_ACTIVITY_ON_TYPE="$split_continuation"
run_submit >/dev/null
wait_for_watcher_log 'post-compact activity started during recovery' >/dev/null
assert_count 1 "^TYPE:$split_continuation$" "$FAKE_TMUX_ACTIONS"
assert_count 0 "^KEY:Enter:$split_continuation$" "$FAKE_TMUX_ACTIONS"
assert_file_equals "$split_continuation" "$FAKE_TMUX_INPUT"

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
