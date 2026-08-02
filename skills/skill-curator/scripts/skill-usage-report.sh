#!/usr/bin/env bash
# skill-usage-report.sh — derive use_count, last_used_at, and days-since-use
# for every skill in dfrysinger/skills by querying the Copilot CLI cloud
# session store. This replaces Hermes Agent's tools/skill_usage.py sidecar
# (.usage.json) — Copilot CLI already logs every `skill` tool call.
#
# Output: TSV on stdout with columns:
#   name <TAB> use_count <TAB> last_used_iso <TAB> days_since_use <TAB> state
# State derived per Hermes thresholds (stale ≥30d, archive ≥90d) and
# config_overrides in ~/.copilot/skill-state/curator.json.
#
# The query requires the Copilot CLI `session_store_sql` tool. This script
# emits a DuckDB query that the calling agent should run via that tool;
# parsing happens in the agent's reasoning step. We print the query so the
# agent can copy/paste it into session_store_sql.
#
# NOTE: session_store_sql rejects a trailing ';' ("multiple SQL statements
# are not allowed"), so the emitted query intentionally omits it.
#
# Usage:
#   skill-usage-report.sh                 # print the DuckDB query
#   skill-usage-report.sh --window 90d    # window default 90d

set -u
WINDOW="${1:-90d}"
WINDOW="${WINDOW#--window}"; WINDOW="${WINDOW# }"
WINDOW="${WINDOW:-90d}"

# Normalize: 90d → 90 days, 4w → 28 days, etc.
case "$WINDOW" in
  *d) DAYS="${WINDOW%d}" ;;
  *w) DAYS=$(( ${WINDOW%w} * 7 )) ;;
  *h) DAYS=$(( ${WINDOW%h} / 24 )) ;;
  *) DAYS="$WINDOW" ;;
esac

# Emit the DuckDB query the agent should run via session_store_sql.
# Keys assumptions confirmed in this session:
#   - tool_requests.name = 'skill' for every /skill-name invocation
#   - tool_requests.arguments_json is JSON like {"skill":"<name>"}
#   - We join to events for the timestamp via tool_call_id.
cat <<SQL
WITH skill_calls AS (
  SELECT
    json_extract_string(tr.arguments_json, '\$.skill') AS skill,
    e.timestamp AS ts
  FROM tool_requests tr
  JOIN events e
    ON e.session_id = tr.session_id
   AND e.tool_complete_call_id = tr.tool_call_id
  WHERE tr.name = 'skill'
    AND e.timestamp > now() - INTERVAL '${DAYS} days'
    AND json_extract_string(tr.arguments_json, '\$.skill') IS NOT NULL
)
SELECT
  skill                              AS name,
  COUNT(*)                           AS use_count,
  MAX(ts)::VARCHAR                   AS last_used_iso,
  date_diff('day', MAX(ts), now())   AS days_since_use,
  CASE
    WHEN date_diff('day', MAX(ts), now()) >= 90 THEN 'archive-eligible'
    WHEN date_diff('day', MAX(ts), now()) >= 30 THEN 'stale'
    ELSE 'active'
  END                                AS state
FROM skill_calls
GROUP BY skill
ORDER BY use_count DESC, last_used_iso DESC
LIMIT 200
SQL
