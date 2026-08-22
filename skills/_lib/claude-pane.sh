#!/usr/bin/env bash
# Claude Code tmux pane parsing.

if ! declare -F cp_input_region >/dev/null 2>&1; then
  _CL_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # shellcheck source=copilot-pane.sh
  . "$_CL_LIB_DIR/copilot-pane.sh"
fi

# Claude's current input frame uses the same caret-and-rule shape as the older
# Copilot layout. Escape-preserving capture suppresses Claude's dim placeholder,
# so strip terminal styling before passing the frame to the shared parser.
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
  _cl_strip_csi | cp_input_region | sed $'1s/^\302\240//'
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
