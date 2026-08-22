#!/usr/bin/env bash
# Tests for the shared Copilot CLI pane parser.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/copilot-pane.sh"

PASS=0
FAIL=0

ok() {
  PASS=$((PASS + 1))
  printf 'ok   %s\n' "$1"
}

no() {
  FAIL=$((FAIL + 1))
  printf 'FAIL %s\n' "$1"
  [ $# -gt 1 ] && printf '     %s\n' "$2"
}

check() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "$name"
  else
    no "$name" "expected [$expected] got [$actual]"
  fi
}

# A boxed-style pane whose transcript contains a past user message. The message
# box uses bare borders and a caret; the input box below uses corner glyphs.
boxed_with() {
  local input="$1" status="$2"
  cat <<EOF
 ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
  ❯ deploy the thing right now                            18:32
 ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 ● Hello! How can I help?

 ~/copilot-workspace/agent-zulu           Session: 17.72 AIC used
╻▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
┃$input
╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
$status
EOF
}

IDLE_STATUS=' ← open sidebar · / commands · ? help · tab next tab   GPT-5.6 Sol · (3%)'
BUSY_STATUS=' ◎ Working · 1.7 KiB esc interrupt                     GPT-5.6 Sol · (3%)'

# --- regression: the caret in transcript scrollback is not unsent input ------

screen="$(boxed_with '  ' "$IDLE_STATUS")"
check 'boxed empty input reads as empty' '' "$(cp_input_text <<<"$screen")"

if cp_input_is_empty <<<"$screen"; then
  ok 'boxed empty input is_empty'
else
  no 'boxed empty input is_empty' 'past user message was read as input'
fi

# --- typed text is seen -----------------------------------------------------

screen="$(boxed_with 'check mailbox' "$IDLE_STATUS")"
check 'boxed typed input is read' 'checkmailbox' "$(cp_input_text <<<"$screen")"

if cp_input_is_empty <<<"$screen"; then
  no 'boxed typed input is not empty' 'typed text reported as empty box'
else
  ok 'boxed typed input is not empty'
fi

# --- wrapped input collapses to one signature -------------------------------

wrapped="$(
  cat <<'EOF'
 ~/copilot-workspace/agent-zulu           Session: 1 AIC used
╻▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
┃check mailbox; skip
┃ if empty [mb:abc]
╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 ← open sidebar · / commands
EOF
)"
check 'wrapped input squashes' 'checkmailbox;skipifempty[mb:abc]' \
  "$(cp_input_text <<<"$wrapped")"

# --- busy detection ---------------------------------------------------------

if cp_is_busy <<<"$(boxed_with '  ' "$BUSY_STATUS")"; then
  ok 'working pane is busy'
else
  no 'working pane is busy'
fi

if cp_is_busy <<<"$(boxed_with '  ' "$IDLE_STATUS")"; then
  no 'idle pane is not busy' 'idle hint line matched the busy pattern'
else
  ok 'idle pane is not busy'
fi

TASK_AUTOPILOT_STATUS=' ○ Proving expanded License Admin walkthrough - autopilot  esc interrupt'
if cp_autopilot_is_selected <<<"$(boxed_with '  ' "$TASK_AUTOPILOT_STATUS")"; then
  ok 'task-labelled autopilot footer is selected'
else
  no 'task-labelled autopilot footer is selected'
fi

LEGACY_AUTOPILOT_STATUS=' ◎ Working - autopilot · 1.7 KiB esc interrupt'
if cp_autopilot_is_selected <<<"$(boxed_with '  ' "$LEGACY_AUTOPILOT_STATUS")"; then
  ok 'legacy autopilot footer is selected'
else
  no 'legacy autopilot footer is selected'
fi

transcript_autopilot="$(
  cat <<EOF
 ● Continue the autopilot charter.
$(boxed_with '  ' "$IDLE_STATUS")
EOF
)"
if cp_autopilot_is_selected <<<"$transcript_autopilot"; then
  no 'transcript autopilot prose is not selected'
else
  ok 'transcript autopilot prose is not selected'
fi

# A busy pane also has an empty input box, so emptiness alone must not be
# treated as readiness by callers.
if cp_input_is_empty <<<"$(boxed_with '  ' "$BUSY_STATUS")"; then
  ok 'busy pane still has an empty box'
else
  no 'busy pane still has an empty box'
fi

# --- loading gate -----------------------------------------------------------

if cp_is_loaded <<<"$(boxed_with '  ' "$IDLE_STATUS")"; then
  ok 'loaded pane detected'
else
  no 'loaded pane detected'
fi

starting="$(
  cat <<'EOF'
╻▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
┃
╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 ← open sidebar
EOF
)"
if cp_is_loaded <<<"$starting"; then
  no 'still-loading pane is not loaded' 'missing AIC marker was accepted'
else
  ok 'still-loading pane is not loaded'
fi

# --- process identity across CLI versions -----------------------------------

for command in \
  copilot \
  copilot-loader \
  copilot-loader- \
  copilot-loader-1.0.81-0 \
  copilot-1.0.81 \
  copilot-1.0.81- \
  copilot-1.0.81-4; do
  if cp_command_is_copilot "$command"; then
    ok "Copilot command accepted: $command"
  else
    no "Copilot command accepted: $command"
  fi
done

for command in \
  '' \
  node \
  zsh \
  copilot-photos-import \
  copilot-helper \
  copilot-loader-helper \
  copilot-1.0.81-helper \
  copilot-1.x.81-4; do
  if cp_command_is_copilot "$command"; then
    no "non-Copilot command rejected: ${command:-<empty>}"
  else
    ok "non-Copilot command rejected: ${command:-<empty>}"
  fi
done

# --- caret style still works ------------------------------------------------

caret_empty="$(
  cat <<'EOF'
 ● Hello! How can I help?
 ~/copilot-workspace/agent-zulu           Session: 5 AIC used
❯
────────────────────────────────
 ? for help
EOF
)"
check 'caret empty input reads as empty' '' "$(cp_input_text <<<"$caret_empty")"
if cp_input_is_empty <<<"$caret_empty"; then
  ok 'caret empty input is_empty'
else
  no 'caret empty input is_empty'
fi

caret_typed="$(
  cat <<'EOF'
 ~/copilot-workspace/agent-zulu           Session: 5 AIC used
❯ check mailbox
  ; skip if empty
────────────────────────────────
 ? for help
EOF
)"
check 'caret typed input is read' 'checkmailbox;skipifempty' \
  "$(cp_input_text <<<"$caret_typed")"

# --- absent box fails closed ------------------------------------------------

if cp_input_region <<<'just a shell prompt' >/dev/null 2>&1; then
  no 'no box returns failure'
else
  ok 'no box returns failure'
fi

if cp_input_is_empty <<<'just a shell prompt'; then
  no 'no box is not empty' 'an unreadable pane was reported as an empty box'
else
  ok 'no box is not empty'
fi

# --- real captured panes ----------------------------------------------------

for fixture in "$SCRIPT_DIR"/fixtures/*.txt; do
  [ -e "$fixture" ] || continue
  name="$(basename "$fixture" .txt)"
  if cp_input_region <"$fixture" >/dev/null 2>&1; then
    ok "fixture $name: input box located"
  else
    no "fixture $name: input box located"
  fi
  case "$name" in
  *-empty)
    if cp_input_is_empty <"$fixture"; then
      ok "fixture $name: box is empty"
    else
      no "fixture $name: box is empty" "read [$(cp_input_text <"$fixture")]"
    fi
    ;;
  esac
  case "$name" in
  busy-*)
    cp_is_busy <"$fixture" && ok "fixture $name: busy" || no "fixture $name: busy"
    ;;
  idle-*)
    cp_is_busy <"$fixture" && no "fixture $name: not busy" || ok "fixture $name: not busy"
    ;;
  esac
done

# --- lines below the input box ----------------------------------------------

check 'boxed below-input is the footer' "$IDLE_STATUS" \
  "$(cp_below_input <<<"$(boxed_with '  ' "$IDLE_STATUS")")"

check 'caret below-input is the footer' ' ? for help' \
  "$(cp_below_input <<<"$caret_empty")"

if cp_below_input <<<'just a shell prompt' >/dev/null 2>&1; then
  no 'no box: below-input fails'
else
  ok 'no box: below-input fails'
fi

menu="$(
  cat <<EOF
 ~/w  Session: 1 AIC used
╻▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
┃
╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 ↑↓ navigate · enter select · esc close
EOF
)"
check 'boxed below-input sees an overlay' ' ↑↓ navigate · enter select · esc close' \
  "$(cp_below_input <<<"$menu")"

# The CLI can draw several rule segments to close the caret input frame. Those
# belong to the frame, not to the content and not to the footer below it.
multi_rule="$(
  cat <<'EOF'
 ~/w  Session: 1 AIC used
❯ proceed
──
────────────────
footer stashed
  ↑/↓ navigate · Enter select
  Esc close
EOF
)"
check 'caret multi-rule frame reads content' 'proceed' \
  "$(cp_input_text <<<"$multi_rule")"
check 'caret multi-rule frame footer excludes rules' \
  'footer stashed
  ↑/↓ navigate · Enter select
  Esc close' \
  "$(cp_below_input <<<"$multi_rule")"

# A trailing tab is real input; only trailing spaces are terminal padding.
tabbed="$(printf ' ~/w  Session: 1 AIC used\n\xe2\x9d\xaf proceed\t   \n────────────────\nfooter\n')"
check 'caret trailing tab is preserved' 'proceed	' \
  "$(cp_input_region <<<"$tabbed")"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]