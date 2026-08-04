#!/usr/bin/env bash
# Shared Copilot TUI input capture and bounded recovery helpers.

SC_TMUX_BIN=""
SC_PANE=""
SC_STATE_STATUS="unknown"
SC_STATE_TEXT_HEX="unknown"
SC_STATE_STASHED=0
SC_STATE_CURSOR_X=-1
SC_STATE_CURSOR_Y=-1
SC_STATE_MENU=0
SC_STATE_RECORD="unknown|unknown|0|-1|-1|0"
SC_PREPARE_WAS_AMBIGUOUS=false
SC_PREPARE_HAD_DRAFT=true
SC_INPUT_LOCALE=""
SC_EDITOR_MARGIN=4

sc_locale_supports_parser() {
  local candidate="$1"
  local charmap normalized_charmap
  [ -n "$candidate" ] || return 1
  charmap="$(
    LC_ALL="$candidate" LANG="$candidate" locale charmap 2>/dev/null
  )" || return 1
  normalized_charmap="$(
    printf '%s' "$charmap" |
      LC_ALL=C tr '[:lower:]' '[:upper:]' |
      LC_ALL=C tr -d '[:space:]_.-'
  )"
  case "$normalized_charmap" in
    *UTF8*) ;;
    *) return 1 ;;
  esac

  printf '%s\n' '❯ proceed' '────────────────' |
    LC_ALL="$candidate" LANG="$candidate" awk '
      NR == 1 {
        value = $0
        if (value !~ /^❯([[:space:]]|$)/) bad = 1
        sub(/^❯ ?/, "", value)
        if (value != "proceed") bad = 1
      }
      NR == 2 {
        if ($0 !~ /^─+$/) bad = 1
      }
      END {
        if (NR != 2 || bad) exit 1
      }' 2>/dev/null
}

sc_ascii_printable() {
  local value="$1"
  ! printf '%s' "$value" | LC_ALL=C grep -q '[^ -~]'
}

sc_pane_one_row_limit() {
  local pane_width
  pane_width="$(
    "$SC_TMUX_BIN" display-message -p -t "$SC_PANE" '#{pane_width}' \
      2>/dev/null
  )" || return 1
  case "$pane_width" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "$pane_width" -gt "$SC_EDITOR_MARGIN" ] || return 1
  printf '%s\n' "$((pane_width - SC_EDITOR_MARGIN))"
}

sc_one_row_command_fits() {
  local value="$1"
  local limit="$2"
  case "$limit" in
    ''|*[!0-9]*) return 1 ;;
  esac
  sc_ascii_printable "$value" &&
    [ "${#value}" -le "$limit" ]
}

sc_input_init() {
  local candidate
  SC_TMUX_BIN="${1:?tmux executable is required}"
  SC_PANE="${2:?tmux pane is required}"
  SC_INPUT_LOCALE=""

  if [ "${SELF_COMPACT_LOCALE+x}" = x ] &&
    sc_locale_supports_parser "$SELF_COMPACT_LOCALE"; then
    SC_INPUT_LOCALE="$SELF_COMPACT_LOCALE"
  else
    for candidate in C.UTF-8 en_US.UTF-8 UTF-8; do
      if sc_locale_supports_parser "$candidate"; then
        SC_INPUT_LOCALE="$candidate"
        break
      fi
    done
  fi

  if [ -z "$SC_INPUT_LOCALE" ]; then
    sc_set_unknown_state
    return 1
  fi
  LC_ALL="$SC_INPUT_LOCALE"
  LANG="$SC_INPUT_LOCALE"
  export LC_ALL LANG
}

sc_sleep() {
  sleep "$1"
}

sc_epoch_milliseconds() {
  local perl_bin seconds
  perl_bin="$(command -v perl 2>/dev/null || true)"
  if [ -n "$perl_bin" ]; then
    "$perl_bin" -MTime::HiRes=time -e \
      'printf "%.0f\n", time() * 1000'
    return
  fi
  seconds="$(date +%s)"
  printf '%s000\n' "$seconds"
}

sc_seconds_to_milliseconds() {
  awk -v seconds="$1" '
    BEGIN {
      if (seconds !~ /^[0-9]+([.][0-9]+)?$/) exit 1
      milliseconds = int((seconds * 1000) + 0.5)
      if (milliseconds < 1) milliseconds = 1
      print milliseconds
    }'
}

sc_ambiguous_wait_is_bounded() {
  awk -v seconds="$1" '
    BEGIN {
      if (seconds !~ /^[0-9]+([.][0-9]+)?$/) exit 1
      exit !(seconds >= 20 && seconds <= 30)
    }'
}

sc_text_hex() {
  LC_ALL=C od -An -tx1 | tr -d '[:space:]'
}

sc_literal_hex() {
  printf '%s' "$1" | sc_text_hex
}

sc_notice() {
  local message="$1"
  local duration="${SELF_COMPACT_NOTICE_MILLISECONDS:-10000}"
  "$SC_TMUX_BIN" display-message -d "$duration" -t "$SC_PANE" "$message" \
    >/dev/null 2>&1 || true
}

sc_refresh_clients() {
  local client client_session session clients
  session="$(
    "$SC_TMUX_BIN" display-message -p -t "$SC_PANE" '#{session_name}' \
      2>/dev/null
  )" || return 1
  clients="$(
    "$SC_TMUX_BIN" list-clients -F '#{client_name}|#{session_name}' 2>/dev/null
  )" || return 1

  while IFS='|' read -r client client_session; do
    [ -n "$client" ] || continue
    [ "$client_session" = "$session" ] || continue
    "$SC_TMUX_BIN" refresh-client -t "$client" >/dev/null 2>&1 ||
      return 1
  done <<< "$clients"
}

sc_resize_pulse() {
  local geometry session window_index width height linked target
  local window_size_effective window_size_configured window_size_inherited
  geometry="$(
    "$SC_TMUX_BIN" display-message -p -t "$SC_PANE" \
      '#{session_name}|#{window_index}|#{window_width}|#{window_height}|#{window_linked}' \
      2>/dev/null
  )" || return 1
  IFS='|' read -r session window_index width height linked <<< "$geometry"
  case "$width:$height:$linked" in
    *[!0-9:]*|:*|*::*|*:) return 1 ;;
  esac
  [ "$linked" -eq 0 ] || return 1
  [ "$width" -gt 2 ] || return 1
  target="$session:$window_index"
  window_size_effective="$(
    "$SC_TMUX_BIN" show-options -w -A -v -t "$target" window-size 2>/dev/null
  )" || return 1
  window_size_configured="$(
    "$SC_TMUX_BIN" show-options -w -qv -t "$target" window-size 2>/dev/null
  )" || return 1
  if [ -n "$window_size_configured" ]; then
    window_size_inherited=false
  else
    window_size_inherited=true
  fi

  (
    pulse_started=false
    restored=false
    restore_window() {
      local restore_status=0 restored_effective
      if [ "$pulse_started" = true ] && [ "$restored" != true ]; then
        "$SC_TMUX_BIN" resize-window -t "$target" -x "$width" -y "$height" \
          >/dev/null 2>&1 || restore_status=1
        if [ "$window_size_inherited" = true ]; then
          "$SC_TMUX_BIN" set-option -wu -t "$target" window-size \
            >/dev/null 2>&1 || restore_status=1
        else
          "$SC_TMUX_BIN" set-option -w -t "$target" \
            window-size "$window_size_configured" >/dev/null 2>&1 ||
            restore_status=1
        fi
        restored_effective="$(
          "$SC_TMUX_BIN" show-options -w -A -v -t "$target" window-size \
            2>/dev/null
        )" || restore_status=1
        [ "$restored_effective" = "$window_size_effective" ] ||
          restore_status=1
        if [ "$restore_status" -eq 0 ]; then
          restored=true
        fi
      fi
      return "$restore_status"
    }
    trap 'restore_window || true' EXIT
    trap 'exit 1' HUP INT TERM

    "$SC_TMUX_BIN" resize-window -t "$target" -x "$((width - 1))" -y "$height" \
      >/dev/null 2>&1
    pulse_started=true
    sc_sleep "${SELF_COMPACT_RESIZE_HOLD_SECONDS:-0.1}"
    restore_window || return 1
    trap - EXIT HUP INT TERM
  )
}

sc_prompt_hex() {
  awk '
    {
      line[NR] = $0
    }
    function emit(value) {
      if (emitted) printf "\n"
      printf "%s", value
      emitted = 1
    }
    END {
      for (i = NR; i >= 1; i--) {
        if (line[i] ~ /^❯([[:space:]]|$)/) {
          prompt = i
          break
        }
      }
      if (!prompt) exit 1
      for (i = NR; i > prompt; i--) {
        if (line[i] ~ /^─+$/) {
          bottom = i
          break
        }
      }
      if (!bottom) exit 1
      value = line[prompt]
      sub(/^❯ ?/, "", value)
      sub(/ +$/, "", value)
      emit(value)
      for (i = prompt + 1; i < bottom; i++) {
        if (line[i] !~ /^─+$/) {
          value = line[i]
          sub(/^  /, "", value)
          sub(/ +$/, "", value)
          emit(value)
        }
      }
    }' | sc_text_hex
}

sc_menu_visible() {
  awk '
    { line[NR] = $0 }
    END {
      for (i = NR; i >= 1; i--) {
        if (line[i] ~ /^❯([[:space:]]|$)/) {
          prompt = i
          break
        }
      }
      if (!prompt) exit 1
      for (i = NR; i > prompt; i--) {
        if (line[i] ~ /^─+$/) {
          bottom = i
          break
        }
      }
      if (!bottom) exit 1
      last = bottom + 4
      if (last > NR) last = NR
      for (i = bottom + 1; i <= last; i++) {
        candidate = tolower(line[i])
        if (candidate ~ /esc/ &&
          candidate ~ /(close|cancel|dismiss)/) escape_hint = 1
        if (candidate ~ /enter/ &&
          candidate ~ /select/) select_hint = 1
        if (index(line[i], "↑") && index(line[i], "↓")) navigation_hint = 1
      }
      exit !(escape_hint && select_hint && navigation_hint)
    }'
}

sc_footer_stashed() {
  awk '
    { line[NR] = $0 }
    END {
      for (i = NR; i >= 1; i--) {
        if (line[i] ~ /^❯([[:space:]]|$)/) {
          prompt = i
          break
        }
      }
      if (!prompt) exit 1
      for (i = NR; i > prompt; i--) {
        if (line[i] ~ /^─+$/) {
          bottom = i
          break
        }
      }
      if (!bottom) exit 1
      for (i = bottom + 1; i <= NR; i++) {
        if (tolower(line[i]) ~ /stashed/) exit 0
      }
      exit 1
    }'
}

sc_capture_sample() {
  local capture capture_sentinel cursor cursor_x cursor_y pane_height
  local capture_lines start_line
  local menu=0 stashed=0 text_hex
  cursor="$(
    "$SC_TMUX_BIN" display-message -p -t "$SC_PANE" \
      '#{cursor_x}|#{cursor_y}|#{pane_height}' 2>/dev/null
  )" || {
    printf '%s\n' 'unknown|unknown|0|-1|-1|0'
    return
  }
  IFS='|' read -r cursor_x cursor_y pane_height <<< "$cursor"
  case "$cursor_x:$cursor_y:$pane_height" in
    *[!0-9:]*|:*|*::*|*:)
      printf '%s\n' 'unknown|unknown|0|-1|-1|0'
      return
      ;;
  esac
  [ "$pane_height" -gt 0 ] || {
    printf '%s\n' 'unknown|unknown|0|-1|-1|0'
    return
  }
  capture_lines="${SELF_COMPACT_CAPTURE_LINES:-24}"
  case "$capture_lines" in
    ''|*[!0-9]*) capture_lines=24 ;;
  esac
  if [ "$pane_height" -gt "$capture_lines" ]; then
    start_line=$((pane_height - capture_lines))
  else
    start_line=0
  fi
  capture_sentinel=$'\034'
  capture="$(
    "$SC_TMUX_BIN" capture-pane -p -t "$SC_PANE" \
      -J -S "$start_line" -E "$((pane_height - 1))" 2>/dev/null ||
      exit 1
    printf '%s' "$capture_sentinel"
  )" || {
    printf '%s\n' 'unknown|unknown|0|-1|-1|0'
    return
  }
  capture="${capture%$capture_sentinel}"
  text_hex="$(printf '%s\n' "$capture" | sc_prompt_hex)" || {
    printf '%s\n' "unknown|unknown|0|$cursor_x|$cursor_y|0"
    return
  }
  if printf '%s\n' "$capture" | sc_footer_stashed; then
    stashed=1
  fi
  if printf '%s\n' "$capture" | sc_menu_visible; then
    menu=1
  fi
  printf 'readable|%s|%s|%s|%s|%s\n' \
    "$text_hex" "$stashed" "$cursor_x" "$cursor_y" "$menu"
}

sc_set_unknown_state() {
  SC_STATE_STATUS="unknown"
  SC_STATE_TEXT_HEX="unknown"
  SC_STATE_STASHED=0
  SC_STATE_CURSOR_X=-1
  SC_STATE_CURSOR_Y=-1
  SC_STATE_MENU=0
  SC_STATE_RECORD="unknown|unknown|0|-1|-1|0"
}

sc_load_state_record() {
  SC_STATE_RECORD="$1"
  IFS='|' read -r \
    SC_STATE_STATUS SC_STATE_TEXT_HEX SC_STATE_STASHED \
    SC_STATE_CURSOR_X SC_STATE_CURSOR_Y SC_STATE_MENU <<< "$SC_STATE_RECORD"
}

sc_capture_stable_state() {
  local activity_callback="${1:-}"
  local first="" record
  local capture_delay="${SELF_COMPACT_CAPTURE_DELAY_SECONDS:-0.05}"

  for capture_number in 1 2 3; do
    if sc_activity_exists "$activity_callback"; then
      return 10
    fi
    record="$(sc_capture_sample)"
    if [ "$capture_number" -eq 1 ]; then
      first="$record"
    elif [ "$record" != "$first" ]; then
      sc_set_unknown_state
      return 1
    fi
    if [ "$capture_number" -lt 3 ]; then
      if sc_activity_exists "$activity_callback"; then
        return 10
      fi
      sc_sleep "$capture_delay"
    fi
  done

  if sc_activity_exists "$activity_callback"; then
    return 10
  fi
  case "$first" in
    readable\|*) sc_load_state_record "$first"; return 0 ;;
    *) sc_set_unknown_state; return 1 ;;
  esac
}

sc_capture_state() {
  sc_refresh_clients || {
    sc_set_unknown_state
    return 1
  }
  if sc_capture_stable_state; then
    return 0
  fi
  sc_resize_pulse || true
  sc_capture_stable_state
}

sc_state_is_empty() {
  [ "$SC_STATE_STATUS" = "readable" ] && [ -z "$SC_STATE_TEXT_HEX" ]
}

sc_state_is_exact() {
  local expected_hex="$1"
  [ "$SC_STATE_STATUS" = "readable" ] &&
    [ "$SC_STATE_MENU" -eq 0 ] &&
    [ "$SC_STATE_TEXT_HEX" = "$expected_hex" ]
}

sc_wait_for_exact_render() {
  local expected_hex="$1"
  local activity_callback="${2:-}"
  local wait_seconds="${SELF_COMPACT_RENDER_WAIT_SECONDS:-5}"
  local poll_seconds="${SELF_COMPACT_RENDER_POLL_SECONDS:-0.05}"
  local wait_milliseconds poll_milliseconds
  local started_milliseconds deadline_milliseconds now_milliseconds
  local remaining_milliseconds sleep_milliseconds sleep_seconds
  local capture_status

  wait_milliseconds="$(sc_seconds_to_milliseconds "$wait_seconds")" ||
    return 1
  poll_milliseconds="$(sc_seconds_to_milliseconds "$poll_seconds")" ||
    return 1
  started_milliseconds="$(sc_epoch_milliseconds)"
  case "$started_milliseconds" in
    ''|*[!0-9]*) return 1 ;;
  esac
  deadline_milliseconds=$((started_milliseconds + wait_milliseconds))

  while :; do
    if sc_activity_exists "$activity_callback"; then
      return 10
    fi
    capture_status=0
    sc_capture_stable_state "$activity_callback" || capture_status=$?
    [ "$capture_status" -eq 10 ] && return 10
    if sc_activity_exists "$activity_callback"; then
      return 10
    fi
    if [ "$capture_status" -eq 0 ] && sc_state_is_exact "$expected_hex"; then
      return 0
    fi

    now_milliseconds="$(sc_epoch_milliseconds)"
    case "$now_milliseconds" in
      ''|*[!0-9]*) return 1 ;;
    esac
    [ "$now_milliseconds" -lt "$deadline_milliseconds" ] || return 1
    remaining_milliseconds=$((deadline_milliseconds - now_milliseconds))
    sleep_milliseconds="$poll_milliseconds"
    if [ "$sleep_milliseconds" -gt "$remaining_milliseconds" ]; then
      sleep_milliseconds="$remaining_milliseconds"
    fi
    sleep_seconds="$(
      awk -v milliseconds="$sleep_milliseconds" \
        'BEGIN { printf "%.3f\n", milliseconds / 1000 }'
    )"
    if sc_activity_exists "$activity_callback"; then
      return 10
    fi
    sc_sleep "$sleep_seconds"
  done
}

sc_transition_kind() {
  local before="$1"
  local after="$2"
  local a_status a_text a_stashed a_x a_y a_menu
  local b_status b_text b_stashed b_x b_y b_menu
  IFS='|' read -r \
    a_status a_text a_stashed a_x a_y a_menu <<< "$before"
  IFS='|' read -r \
    b_status b_text b_stashed b_x b_y b_menu <<< "$after"

  if [ "$a_status" != readable ] || [ "$b_status" != readable ] ||
    [ "$a_menu" -ne 0 ] || [ "$b_menu" -ne 0 ]; then
    printf '%s\n' inconclusive
  elif [ -n "$a_text" ] && [ -z "$b_text" ]; then
    # A stable full-to-empty delta is sufficient when the footer redraw hides
    # the otherwise expected stashed indicator.
    printf '%s\n' stored
  elif [ -z "$a_text" ] && [ -n "$b_text" ]; then
    printf '%s\n' restored
  elif [ -z "$a_text" ] && [ -z "$b_text" ] &&
    [ "$a_stashed" -eq 0 ] && [ "$b_stashed" -eq 0 ] &&
    [ "$a_x" = "$b_x" ] && [ "$a_y" = "$b_y" ] &&
    [ "$a_x" -le "${SELF_COMPACT_EMPTY_CURSOR_MAX_X:-2}" ]; then
    printf '%s\n' empty
  else
    printf '%s\n' inconclusive
  fi
}

sc_activity_exists() {
  local callback="${1:-}"
  [ -n "$callback" ] && "$callback"
}

sc_prepare_empty_input() {
  local activity_callback="${1:-}"
  local before after kind reverse
  local before_status before_text before_stashed

  SC_PREPARE_WAS_AMBIGUOUS=false
  SC_PREPARE_HAD_DRAFT=true
  sc_capture_state || true
  before="$SC_STATE_RECORD"
  IFS='|' read -r before_status before_text before_stashed _ <<< "$before"
  if [ "$before_status" = readable ] &&
    [ -z "$before_text" ] &&
    [ "$before_stashed" -eq 0 ]; then
    SC_PREPARE_HAD_DRAFT=false
  fi
  if sc_activity_exists "$activity_callback"; then
    return 10
  fi
  "$SC_TMUX_BIN" send-keys -t "$SC_PANE" C-s || return 1
  sc_capture_state || true
  after="$SC_STATE_RECORD"
  kind="$(sc_transition_kind "$before" "$after")"

  if [ "$kind" = inconclusive ]; then
    # The first Ctrl-S may already have stored the draft. Re-read state B once;
    # never send another toggle until a visible restored-draft delta proves it.
    sc_capture_state || true
    after="$SC_STATE_RECORD"
    kind="$(sc_transition_kind "$before" "$after")"
  fi

  case "$kind" in
    stored)
      SC_PREPARE_HAD_DRAFT=true
      return 0
      ;;
    empty)
      SC_PREPARE_HAD_DRAFT=false
      return 0
      ;;
    restored)
      SC_PREPARE_HAD_DRAFT=true
      if sc_activity_exists "$activity_callback"; then
        return 10
      fi
      "$SC_TMUX_BIN" send-keys -t "$SC_PANE" C-s || return 1
      sc_capture_state || true
      reverse="$(sc_transition_kind "$after" "$SC_STATE_RECORD")"
      [ "$reverse" = stored ] && return 0
      ;;
  esac

  SC_PREPARE_WAS_AMBIGUOUS=true
  SC_PREPARE_HAD_DRAFT=true
  return 2
}

sc_prepare_empty_editor() {
  local activity_callback="${1:-}"
  local prepare_status key_status

  prepare_status=0
  sc_prepare_empty_input "$activity_callback" || prepare_status=$?
  case "$prepare_status" in
    0)
      sc_capture_state || true
      sc_state_is_empty && return 0
      ;;
    10) return 10 ;;
    2) ;;
    *) return 1 ;;
  esac

  SC_PREPARE_HAD_DRAFT=true
  sc_notice \
    "self-compact: input changed or unreadable; will clear it in 10 seconds unless activity starts"
  sc_sleep "${SELF_COMPACT_RECOVERY_DELAY_SECONDS:-10}"
  sc_activity_exists "$activity_callback" && return 10

  key_status=0
  sc_send_recovery_key C-u "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  sc_capture_state || true
  sc_state_is_empty && return 0

  key_status=0
  sc_send_recovery_key C-u "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  key_status=0
  sc_send_recovery_key Escape "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  sc_capture_state || true

  if [ "$SC_STATE_MENU" -eq 1 ]; then
    key_status=0
    sc_send_recovery_key Escape "$activity_callback" || key_status=$?
    [ "$key_status" -eq 10 ] && return 10
    [ "$key_status" -eq 0 ] || return 1
    sc_capture_state || true
  fi

  key_status=0
  sc_send_recovery_key C-u "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  sc_capture_state || true
  sc_state_is_empty && return 0

  sc_notice "self-compact: input recovery failed; command was not submitted"
  return 1
}

sc_wait_for_ambiguous_submit() {
  local expected_hex="$1"
  local activity_callback="${2:-}"
  local wait_seconds="${SELF_COMPACT_AMBIGUOUS_WAIT_SECONDS:-25}"
  local poll_seconds="${SELF_COMPACT_RENDER_POLL_SECONDS:-0.05}"
  local wait_milliseconds poll_milliseconds
  local started_milliseconds deadline_milliseconds now_milliseconds
  local remaining_milliseconds sleep_milliseconds sleep_seconds capture_status

  sc_ambiguous_wait_is_bounded "$wait_seconds" || return 1
  wait_milliseconds="$(sc_seconds_to_milliseconds "$wait_seconds")" ||
    return 1
  poll_milliseconds="$(sc_seconds_to_milliseconds "$poll_seconds")" ||
    return 1
  started_milliseconds="$(sc_epoch_milliseconds)"
  case "$started_milliseconds" in
    ''|*[!0-9]*) return 1 ;;
  esac
  deadline_milliseconds=$((started_milliseconds + wait_milliseconds))

  while :; do
    sc_activity_exists "$activity_callback" && return 10
    capture_status=0
    sc_capture_stable_state "$activity_callback" || capture_status=$?
    [ "$capture_status" -eq 10 ] && return 10
    sc_activity_exists "$activity_callback" && return 10

    if [ "$capture_status" -eq 0 ]; then
      sc_state_is_exact "$expected_hex" && return 0
      if [ "$SC_STATE_MENU" -eq 1 ] ||
        { [ "$SC_STATE_STATUS" = readable ] &&
          [ -n "$SC_STATE_TEXT_HEX" ]; }; then
        return 1
      fi
    fi

    now_milliseconds="$(sc_epoch_milliseconds)"
    case "$now_milliseconds" in
      ''|*[!0-9]*) return 1 ;;
    esac
    [ "$now_milliseconds" -lt "$deadline_milliseconds" ] || return 2
    remaining_milliseconds=$((deadline_milliseconds - now_milliseconds))
    sleep_milliseconds="$poll_milliseconds"
    if [ "$sleep_milliseconds" -gt "$remaining_milliseconds" ]; then
      sleep_milliseconds="$remaining_milliseconds"
    fi
    sleep_seconds="$(
      awk -v milliseconds="$sleep_milliseconds" \
        'BEGIN { printf "%.3f\n", milliseconds / 1000 }'
    )"
    sc_activity_exists "$activity_callback" && return 10
    sc_sleep "$sleep_seconds"
  done
}

sc_cleanup_exact_command() {
  local expected_hex="$1"
  sc_capture_state || true
  if sc_state_is_exact "$expected_hex"; then
    "$SC_TMUX_BIN" send-keys -t "$SC_PANE" C-u || true
  fi
}

sc_send_recovery_key() {
  local key="$1"
  local activity_callback="${2:-}"
  local status
  if sc_activity_exists "$activity_callback"; then
    return 10
  fi
  status=0
  "$SC_TMUX_BIN" send-keys -t "$SC_PANE" "$key" || status=$?
  return "$status"
}

sc_type_literal() {
  local command="$1"
  local activity_callback="${2:-}"
  if sc_activity_exists "$activity_callback"; then
    return 10
  fi
  "$SC_TMUX_BIN" send-keys -t "$SC_PANE" -l -- "$command"
}

sc_prepare_verified_command() {
  local command="$1"
  local activity_callback="${2:-}"
  local expected_hex recovery_status type_status key_status render_status
  local type_count=0 typed_final=false
  expected_hex="$(sc_literal_hex "$command")"

  if sc_prepare_empty_input "$activity_callback"; then
    type_status=0
    sc_type_literal "$command" "$activity_callback" || type_status=$?
    [ "$type_status" -eq 10 ] && return 10
    [ "$type_status" -eq 0 ] || return 1
    type_count=1
    render_status=0
    sc_wait_for_exact_render "$expected_hex" "$activity_callback" ||
      render_status=$?
    case "$render_status" in
      0) return 0 ;;
      10)
        sc_cleanup_exact_command "$expected_hex"
        return 10
        ;;
    esac
  else
    recovery_status=$?
    [ "$recovery_status" -eq 10 ] && return 10
    [ "$recovery_status" -eq 2 ] || return 1
  fi

  sc_notice \
    "self-compact: input changed or unreadable; will clear it in 10 seconds unless activity starts"
  sc_sleep "${SELF_COMPACT_RECOVERY_DELAY_SECONDS:-10}"
  if sc_activity_exists "$activity_callback"; then
    return 10
  fi

  # First destructive key after the grace period is always Ctrl-U.
  key_status=0
  sc_send_recovery_key C-u "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  sc_capture_state || true
  # Only an initially ambiguous path gets the Ctrl-U-first typing opportunity.
  # A normal path already spent typing #1 and must repair menus before typing #2.
  if sc_state_is_empty && [ "$type_count" -eq 0 ]; then
    type_status=0
    sc_type_literal "$command" "$activity_callback" || type_status=$?
    [ "$type_status" -eq 10 ] && return 10
    [ "$type_status" -eq 0 ] || return 1
    type_count=$((type_count + 1))
    render_status=0
    sc_wait_for_exact_render "$expected_hex" "$activity_callback" ||
      render_status=$?
    case "$render_status" in
      0) return 0 ;;
      10)
        sc_cleanup_exact_command "$expected_hex"
        return 10
        ;;
    esac
  fi

  key_status=0
  sc_send_recovery_key C-u "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  key_status=0
  sc_send_recovery_key Escape "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  sc_capture_state || true

  if [ "$SC_STATE_MENU" -eq 1 ]; then
    key_status=0
    sc_send_recovery_key Escape "$activity_callback" || key_status=$?
    [ "$key_status" -eq 10 ] && return 10
    [ "$key_status" -eq 0 ] || return 1
    sc_capture_state || true
  fi

  key_status=0
  sc_send_recovery_key C-u "$activity_callback" || key_status=$?
  [ "$key_status" -eq 10 ] && return 10
  [ "$key_status" -eq 0 ] || return 1
  if [ "$type_count" -lt 2 ]; then
    type_status=0
    sc_type_literal "$command" "$activity_callback" || type_status=$?
    [ "$type_status" -eq 10 ] && return 10
    [ "$type_status" -eq 0 ] || return 1
    type_count=$((type_count + 1))
    typed_final=true
    render_status=0
    sc_wait_for_exact_render "$expected_hex" "$activity_callback" ||
      render_status=$?
    case "$render_status" in
      0) return 0 ;;
      10)
        sc_cleanup_exact_command "$expected_hex"
        return 10
        ;;
    esac
  fi

  if [ "$typed_final" = true ]; then
    # This fourth and final Ctrl-U is best-effort cleanup after the grace period.
    key_status=0
    sc_send_recovery_key C-u "$activity_callback" || key_status=$?
    [ "$key_status" -eq 10 ] && return 10
  fi
  sc_notice "self-compact: input recovery failed; command was not submitted"
  return 1
}
