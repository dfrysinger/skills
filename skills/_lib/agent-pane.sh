#!/usr/bin/env bash
# Fail-closed dispatch across Copilot CLI, Claude Code, and Codex CLI panes.

_AP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=copilot-pane.sh
. "$_AP_LIB_DIR/copilot-pane.sh"
# shellcheck source=claude-pane.sh
. "$_AP_LIB_DIR/claude-pane.sh"
# shellcheck source=codex-pane.sh
. "$_AP_LIB_DIR/codex-pane.sh"

# Reads `ps -ax -o pid=,ppid=,comm=,args=` from stdin and prints the backend
# belonging to ROOT_PID. The nearest recognized process wins. Conflicting
# identities at the same depth fail closed.
ap_backend_from_processes() {
  local root_pid="$1"
  awk -v root="$root_pid" '
    function basename(path, count, parts) {
      count = split(path, parts, "/")
      return parts[count]
    }
    function command_backend(command, args, count, words, executable) {
      executable = basename(command)
      count = split(args, words, /[[:space:]]+/)
      if (count && words[1] != "") executable = basename(words[1])

      if (executable == "node" && count >= 2)
        executable = basename(words[2])

      if (executable == "claude") return "claude"
      if (executable == "codex") return "codex"
      if (executable == "copilot" || executable == "copilot-loader" ||
          executable == "copilot-loader-" ||
          executable ~ /^copilot-loader-[0-9]+\.[0-9]+\.[0-9]+(-[0-9]+)?$/ ||
          executable ~ /^copilot-[0-9]+\.[0-9]+\.[0-9]+(-[0-9]*)?$/)
        return "copilot"
      return ""
    }
    function distance(pid, current, seen, depth) {
      current = pid
      for (depth = 0; depth <= 64; depth++) {
        if (current == root) return depth
        if (!(current in parent) || seen[current]++) return -1
        current = parent[current]
      }
      return -1
    }
    {
      pid = $1
      parent[pid] = $2
      command[pid] = $3
      $1 = $2 = $3 = ""
      sub(/^[[:space:]]+/, "", $0)
      args[pid] = $0
      pids[pid] = 1
    }
    END {
      best_depth = 999
      best = ""
      conflict = 0
      for (pid in pids) {
        depth = distance(pid)
        if (depth < 0) continue
        candidate = command_backend(command[pid], args[pid])
        if (candidate == "") continue
        if (depth < best_depth) {
          best_depth = depth
          best = candidate
          conflict = 0
        } else if (depth == best_depth && candidate != best) {
          conflict = 1
        }
      }
      if (best != "" && !conflict) print best
      else exit 1
    }'
}

ap_pane_backend() {
  local pane="$1" pane_pid
  pane_pid="$(tmux display-message -p -t "$pane" '#{pane_pid}' 2>/dev/null || true)"
  [[ "$pane_pid" =~ ^[0-9]+$ ]] || return 1
  ps -ax -o pid=,ppid=,comm=,args= | ap_backend_from_processes "$pane_pid"
}

ap_pane_is_backend() {
  local actual
  actual="$(ap_pane_backend "$1")" || return 1
  [ "$actual" = "$2" ]
}

ap_capture() {
  local pane="$1" backend="$2"
  if [ "$backend" = codex ] || [ "$backend" = claude ]; then
    tmux capture-pane -p -e -J -t "$pane" 2>/dev/null
  else
    tmux capture-pane -p -J -t "$pane" 2>/dev/null
  fi
}

ap_input_region() {
  case "$1" in
    copilot) cp_input_region ;;
    claude)  cl_input_region ;;
    codex)   cx_input_region ;;
    *) return 1 ;;
  esac
}

ap_input_signature() { tr -d '[:space:]'; }

ap_input_is_empty() {
  local backend="$1" text
  text="$(ap_input_region "$backend")" || return 1
  [ -z "$(ap_input_signature <<<"$text")" ]
}

ap_is_loaded() {
  case "$1" in
    copilot) cp_is_loaded ;;
    claude)  cl_is_loaded ;;
    codex)   cx_is_loaded ;;
    *) return 1 ;;
  esac
}

ap_pane_accepts_input() {
  local pane="$1" expected_backend="$2" screen
  ap_pane_is_backend "$pane" "$expected_backend" || return 1
  screen="$(ap_capture "$pane" "$expected_backend")" || return 1
  [ -n "$screen" ] || return 1
  ap_is_loaded "$expected_backend" <<<"$screen" || return 1
  ap_input_is_empty "$expected_backend" <<<"$screen"
}
