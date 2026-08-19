#!/usr/bin/env bash
# Shared Copilot CLI tmux pane parsing.
#
# Several skills drive a Copilot CLI agent by typing into its tmux pane, and all
# of them need the same two facts: what is currently in the input box, and
# whether the agent is idle enough to accept a keystroke. Reading the pane is
# the only way to get either, so the parser lives here once rather than being
# reinvented per caller.
#
# Two input-box styles are recognised.
#
# Boxed style, current:
#
#     ╻▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
#     ┃ typed text
#     ╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
#      ← open sidebar · / commands
#
# Caret style, older:
#
#     ❯ typed text
#     ────────────────
#
# The distinction that matters: in the boxed style a past user message is also
# drawn in a box and is also introduced by `❯`, but its borders are bare `▄`
# and `▀` with no `╻`/`╹` corner. Keying on the caret alone therefore reads the
# last thing the user said as though it were unsent input, so a pane that is
# busy, or that already holds typed text, reads as ready. The corner glyphs are
# what separate the live input box from transcript scrollback.

# Locates the input box and prints either its contents or the lines below it.
# Both callers need the same locator, so it lives in one awk program selected by
# MODE ("region" or "below").
_cp_scan() {
  awk -v mode="${1:-region}" '
    { line[NR] = $0 }
    END {
      # Prefer the boxed layout: scan up for the last box bottom, then its top.
      # The live input box is the last one drawn.
      for (i = NR; i >= 1; i--) {
        if (line[i] ~ /^[[:space:]]*╹/) { bottom = i; break }
      }
      if (bottom) {
        for (i = bottom - 1; i >= 1; i--) {
          if (line[i] ~ /^[[:space:]]*╻/) { top = i; break }
          # Another box bottom means the one below was never opened; stop
          # rather than walking up into the transcript.
          if (line[i] ~ /^[[:space:]]*╹/) break
        }
        if (!top) exit 1
        style = "box"
      } else {
        # Caret layout: the prompt comes first, then the rule closing it. The
        # CLI can draw several rule segments, so take the first rule below the
        # prompt rather than assuming the last line is it.
        for (i = NR; i >= 1; i--) {
          if (line[i] ~ /^[[:space:]]*❯([[:space:]]|$)/) { top = i; break }
        }
        if (!top) exit 1
        for (i = top + 1; i <= NR; i++) {
          if (line[i] ~ /^─+$/) { bottom = i; break }
        }
        if (!bottom) exit 1
        style = "rule"
      }

      if (mode == "below") {
        # Trailing rule segments belong to the input frame, not below it.
        start = bottom + 1
        if (style == "rule") {
          while (start <= NR && line[start] ~ /^─+$/) start++
        }
        for (i = start; i <= NR; i++) print line[i]
        exit 0
      }

      if (style == "box") {
        for (i = top + 1; i < bottom; i++) {
          value = line[i]
          sub(/^ *┃/, "", value)
          sub(/ +$/, "", value)
          print value
        }
        exit 0
      }

      value = line[top]
      sub(/^ *❯ ?/, "", value)
      sub(/ +$/, "", value)
      print value
      for (i = top + 1; i < bottom; i++) {
        if (line[i] ~ /^─+$/) continue
        value = line[i]
        sub(/^  /, "", value)
        sub(/ +$/, "", value)
        print value
      }
    }'
}

# Prints the input box's content lines on stdout, borders removed, one line per
# rendered row. Wrapped input yields several lines. Returns 1 when no input box
# is present, which includes a pane that is not Copilot CLI at all.
cp_input_region() { _cp_scan region; }

# Prints the lines below the input box: the hint/status footer, and any menu or
# overlay the CLI draws there. Returns 1 when no input box is present.
cp_below_input() { _cp_scan below; }

# Collapses input to a whitespace-free signature. Wrapping inserts newlines and
# padding at arbitrary points, so only a squashed comparison is stable across
# pane widths.
cp_input_signature() { tr -d '[:space:]'; }

cp_input_text() { cp_input_region | cp_input_signature; }

# Returns 0 only when an input box exists and holds nothing. A missing box is
# not empty: it means the pane could not be read, and typing into an unread
# pane is how text lands somewhere unintended.
cp_input_is_empty() {
  local text
  text="$(cp_input_region)" || return 1
  [ -z "$(cp_input_signature <<<"$text")" ]
}

# Returns 0 when the agent is mid-turn. Keystrokes sent now are queued rather
# than acted on, and a queued message only drains at a turn boundary.
cp_is_busy() {
  grep -Eqi 'esc interrupt|[◎◉○●▪▫][[:space:]]*Working'
}

# Returns 0 when the CLI has finished loading. The input box renders before
# skills are registered, and a slash command sent during that window is
# silently dropped, so a rendered box alone does not mean the agent can be
# addressed.
cp_is_loaded() { grep -q 'Session:.*AIC used'; }

# Captures a pane with wrapped lines joined. Returns 1 if the pane is gone.
cp_capture() { tmux capture-pane -p -J -t "$1" 2>/dev/null; }

cp_pane_is_copilot() {
  [ "$(tmux display-message -p -t "$1" '#{pane_current_command}' 2>/dev/null || true)" = copilot ]
}

# Returns 0 when the pane can receive a keystroke: a real Copilot pane that has
# finished loading and whose input box is empty. The agent may still be
# mid-turn, in which case typed input is queued and drains at the next turn
# boundary, which is the intended behaviour for delivering mail.
cp_pane_accepts_input() {
  local pane="$1" screen
  cp_pane_is_copilot "$pane" || return 1
  screen="$(cp_capture "$pane")" || return 1
  [ -n "$screen" ] || return 1
  cp_is_loaded <<<"$screen" || return 1
  cp_input_is_empty <<<"$screen"
}

# Stricter: additionally requires the agent to be between turns. Use this when
# the work must start now rather than be queued behind an in-flight turn.
cp_pane_is_idle() {
  local pane="$1" screen
  cp_pane_accepts_input "$pane" || return 1
  screen="$(cp_capture "$pane")" || return 1
  ! cp_is_busy <<<"$screen"
}
