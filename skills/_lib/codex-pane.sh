#!/usr/bin/env bash
# Codex CLI tmux pane parsing.

# Codex renders placeholder text inside the live prompt. Plain tmux capture
# loses the dim styling that distinguishes that placeholder from typed input,
# so callers must capture with escape sequences retained (`tmux ... -e`).
_cx_scan() {
  awk '
    function plain(value, esc) {
      esc = sprintf("%c", 27)
      gsub(esc "\\[[0-9;:]*[ -/]*[@-~]", "", value)
      return value
    }
    { raw[NR] = $0; visible[NR] = plain($0) }
    END {
      for (i = NR; i >= 1; i--) {
        if (visible[i] ~ /^[[:space:]]*›([[:space:]]|$)/) {
          prompt = i
          break
        }
      }
      if (!prompt) exit 1

      value = visible[prompt]
      sub(/^[[:space:]]*›[[:space:]]?/, "", value)

      # The idle suggestion is dim; real user input is not.
      esc = sprintf("%c", 27)
      if (index(raw[prompt], esc "[2m")) exit 0

      sub(/[[:space:]]+$/, "", value)
      print value
      for (i = prompt + 1; i <= NR; i++) {
        value = visible[i]
        if (value ~ /^[[:space:]]*$/) break
        sub(/^[[:space:]]{2}/, "", value)
        sub(/[[:space:]]+$/, "", value)
        print value
      }
    }'
}

cx_input_region() { _cx_scan; }
cx_input_signature() { tr -d '[:space:]'; }

cx_input_is_empty() {
  local text
  text="$(cx_input_region)" || return 1
  [ -z "$(cx_input_signature <<<"$text")" ]
}

# Locating the styled live prompt is the loading gate. Startup/update dialogs
# do not contain it, and process identity is checked separately by the caller.
cx_is_loaded() { cx_input_region >/dev/null; }

