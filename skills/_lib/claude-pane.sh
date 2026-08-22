#!/usr/bin/env bash
# Claude Code tmux pane parsing.

if ! declare -F cp_input_region >/dev/null 2>&1; then
  _CL_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # shellcheck source=copilot-pane.sh
  . "$_CL_LIB_DIR/copilot-pane.sh"
fi

# Claude's current input frame uses the same caret-and-rule shape as the older
# Copilot layout. Escape-preserving capture distinguishes its dim suggestion
# from typed input, so remove a dim prompt value before stripping terminal
# styling and passing the frame to the shared parser.
_cl_suppress_dim_suggestion() {
  awk '
    {
      esc = sprintf("%c", 27)
      visible = $0
      gsub(esc "\\[[0-9;:]*[ -/]*[@-~]", "", visible)
      if (visible ~ /^[[:space:]]*❯([[:space:]]|$)/ &&
          (start = index($0, esc "[2m"))) {
        $0 = substr($0, 1, start - 1)
      }
      print
    }'
}

_cl_strip_csi() {
  awk '
    {
      esc = sprintf("%c", 27)
      gsub(esc "\\[[0-9;:]*[ -/]*[@-~]", "", $0)
      print
    }'
}

cl_input_region() {
  # Claude draws a non-breaking space after the caret. The shared caret parser
  # removes an ordinary space, so discard this frame glyph from the first row.
  _cl_suppress_dim_suggestion | _cl_strip_csi | cp_input_region |
    sed $'1s/^\302\240//'
}
cl_input_signature() { cp_input_signature; }
cl_input_is_empty() {
  local text
  text="$(cl_input_region)" || return 1
  [ -z "$(cl_input_signature <<<"$text")" ]
}

cl_is_loaded() {
  local below
  below="$(_cl_strip_csi | cp_below_input)" || return 1
  grep -q 'Ctx:' <<<"$below"
}
