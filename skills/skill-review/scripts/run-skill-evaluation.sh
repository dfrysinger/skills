#!/usr/bin/env bash
# Run source and sibling cases with and without one isolated candidate skill.

set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "usage: $(basename "$0") <skill-dir> --model <model> [--cases <file>]" >&2
  exit 2
fi

SKILL_DIR="$1"
shift
MODEL=""
CASES=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="${2:-}"; shift 2 ;;
    --cases) CASES="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$MODEL" ]] || { echo "REFUSED: --model is required" >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-daemon.sh
source "$SCRIPT_DIR/lib-daemon.sh"
COPILOT="${COPILOT_BIN:-$HOME/.local/bin/copilot}"
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/skill-evaluation.XXXXXX")"
PLUGIN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/skill-evaluation-plugin.XXXXXX")"
SANDBOX_DIR="$(mktemp -d "${TMPDIR:-/tmp}/skill-evaluation-sandbox.XXXXXX")"
trap 'rm -rf "$RUN_DIR" "$PLUGIN_DIR" "$SANDBOX_DIR"' EXIT

PREPARE=("$SCRIPT_DIR/skill-evaluation.py" prepare "$SKILL_DIR" --model "$MODEL" \
  --run-dir "$RUN_DIR" --plugin-dir "$PLUGIN_DIR")
[[ -n "$CASES" ]] && PREPARE+=(--cases "$CASES")
"${PREPARE[@]}" >/dev/null

TOKEN="$(skills_derive_github_token github.com)"
[[ -n "$TOKEN" ]] || { echo "REFUSED: no Copilot authentication token available" >&2; exit 1; }
mkdir -p "$SANDBOX_DIR"

run_case() {
  local case_name="$1"
  local mode="$2"
  local log="$RUN_DIR/${case_name}-${mode}.jsonl"
  local cell="$SANDBOX_DIR/${case_name}-${mode}"
  mkdir -p "$cell/home" "$cell/cwd"
  local command=(
    "$COPILOT" -C "$cell/cwd"
    -p "$(cat "$RUN_DIR/$case_name.prompt")"
    --model "$MODEL" --effort low
    --available-tools=skill,view --allow-tool=skill,view
    --no-custom-instructions --disable-builtin-mcps --disallow-temp-dir
    --no-remote --no-color
    --output-format json --log-level error
  )
  if [[ "$mode" == "candidate" ]]; then
    command+=(--plugin-dir "$PLUGIN_DIR")
  fi
  : > "$log"
  COPILOT_HOME="$cell/home" COPILOT_GITHUB_TOKEN="$TOKEN" \
    skills_run_copilot_bounded "$log" '"type":"result"' 300 3 -- "${command[@]}" ||
    true
}

run_case source baseline
run_case source candidate
run_case sibling baseline
run_case sibling candidate
"$SCRIPT_DIR/skill-evaluation.py" finalize --run-dir "$RUN_DIR"
