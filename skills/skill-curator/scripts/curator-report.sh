#!/usr/bin/env bash
# curator-report.sh — write a dry-run report to ~/.copilot/skill-state/reports/
# and update curator state.
#
# Usage: curator-report.sh < report.md     (reads markdown from stdin)
#        curator-report.sh /path/to/report.md

set -euo pipefail

STATE_DIR="$HOME/.copilot/skill-state"
REPORTS_DIR="$STATE_DIR/reports"
mkdir -p "$REPORTS_DIR"

TS=$(date -u +%Y%m%d-%H%M%S)
OUT="$REPORTS_DIR/${TS}-curator-report.md"

if [[ $# -eq 1 ]]; then
  cp "$1" "$OUT"
else
  cat > "$OUT"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pull the first line of the report (usually the human summary heading) for the state-file summary.
SUMMARY=$(head -1 "$OUT" | sed 's/^#* *//')
[[ -z "$SUMMARY" ]] && SUMMARY="dry-run report"

"$SCRIPT_DIR/curator-state.sh" set last_report_path "$OUT" >/dev/null
"$SCRIPT_DIR/curator-state.sh" note "$SUMMARY" >/dev/null

echo "wrote report: $OUT"
