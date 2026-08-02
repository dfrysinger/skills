#!/usr/bin/env bash
# score-sessions.sh — emit the DuckDB query that scores recent sessions for
# skill-review eligibility, ranking which sessions are most likely to contain a
# reusable procedure worth capturing.
#
# This is the Copilot-CLI substitute for Hermes's in-loop `_iters_since_skill`
# counter: since we cannot hook the agent loop, we score sessions AFTER THE FACT
# from session_store_sql. The sweep runs this query, then reviews high-scoring
# sessions not already in the ledger.
#
# Scoring signals (additive), per rubber-duck guidance (raw tool count alone is
# noisy):
#   + tool-call volume        (work happened)
#   + distinct tool variety   (a real workflow, not one tool spammed)
#   + user-correction phrases ("no", "actually", "from now on", "remember",
#     "stop doing", "too verbose", "just give me") — first-class skill signals
#   + explicit skill intent   (user message mentions skill/reusable/procedure)
#   - already trivial         (single short turn) handled by HAVING threshold
#
# The caller (skill-review sweep) passes a `since` ISO timestamp (the ledger
# watermark) so only newer sessions are scored. NO trailing semicolon —
# session_store_sql rejects it ("multiple SQL statements are not allowed").
#
# Usage:
#   score-sessions.sh                    # default: fixed 14-day lookback window
#   score-sessions.sh --lookback-days N  # override the lookback window
#   LOOKBACK_DAYS=N score-sessions.sh    # same, via env
#   score-sessions.sh [SINCE_ISO]        # SINCE may only EXTEND the window back
#   score-sessions.sh --min-score N      # informational; thresholding is the
#                                          agent's job after reading rows
#
# Window model (post-2026-06 fix): the scoring window is a FIXED lookback of
# LOOKBACK_DAYS, NOT the ledger watermark. Dedup of already-reviewed sessions is
# the caller's job, per-session, via review-ledger.sh `has <session_id>`. A
# passed SINCE_ISO may only EXTEND the window further back (a floor, via LEAST);
# it can never advance it forward. This removes the orphaning bug where a single
# near-now ledger watermark (e.g. an end-of-task review of the current session)
# would shrink the window to ~now and skip the entire prior backlog.

set -u
SINCE=""
LOOKBACK_DAYS="${LOOKBACK_DAYS:-14}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --min-score*) : ;;
    --lookback-days) shift; LOOKBACK_DAYS="${1:-14}" ;;
    --lookback-days=*) LOOKBACK_DAYS="${1#*=}" ;;
    *) SINCE="$1" ;;
  esac
  shift
done
# Guard: LOOKBACK_DAYS must be a bare integer (it is interpolated into SQL).
case "$LOOKBACK_DAYS" in *[!0-9]*|'') LOOKBACK_DAYS=14 ;; esac

# Fixed lookback floor. A supplied SINCE can only push the window OLDER (LEAST),
# never newer — guarantees we always scan at least LOOKBACK_DAYS back.
if [[ -z "$SINCE" ]]; then
  SINCE_CLAUSE="e.timestamp > now() - INTERVAL '${LOOKBACK_DAYS} days'"
else
  SINCE_CLAUSE="e.timestamp > LEAST(TIMESTAMP '${SINCE}', now() - INTERVAL '${LOOKBACK_DAYS} days')"
fi

cat <<SQL
WITH ev AS (
  SELECT
    e.session_id,
    e.timestamp AS ts,
    e.type,
    e.tool_start_name,
    lower(COALESCE(e.user_content, '')) AS uc
  FROM events e
  WHERE ${SINCE_CLAUSE}
),
per_session AS (
  SELECT
    session_id,
    MAX(ts)::VARCHAR AS last_ts,
    MIN(ts)::VARCHAR AS first_ts,
    COUNT(*) FILTER (WHERE type = 'tool.execution_complete'
                       OR tool_start_name IS NOT NULL)            AS tool_calls,
    COUNT(DISTINCT tool_start_name)                               AS tool_variety,
    COUNT(*) FILTER (WHERE regexp_matches(uc, '(^|[^a-z])(no|actually|stop doing|too verbose|just give me|from now on|remember|don''t format|why are you explaining)([^a-z]|$)')) AS correction_hits,
    COUNT(*) FILTER (WHERE uc LIKE '%skill%'
                       OR uc LIKE '%reusable%'
                       OR uc LIKE '%make this a%'
                       OR uc LIKE '%procedure%')                  AS skill_intent_hits,
    -- Self-exclusion guard: the headless daemon stamps a sentinel token as the
    -- first line of its sweep/curator prompt, which lands in this session's
    -- user.message content. Flag the WHOLE session (session-level, not row-level)
    -- so the daemon never scores or reviews its own runs. NULL-safe via uc's
    -- COALESCE upstream.
    MAX(CASE WHEN type = 'user.message'
              AND uc LIKE '%[autoreview-daemon-session:96efca49-7380-4494-86c4-ab4ab954ee3f]%'
             THEN 1 ELSE 0 END)                                   AS is_daemon
  FROM ev
  GROUP BY session_id
)
SELECT
  session_id,
  last_ts,
  first_ts,
  tool_calls,
  tool_variety,
  correction_hits,
  skill_intent_hits,
  ( LEAST(tool_calls, 30)
    + 2 * LEAST(tool_variety, 8)
    + 5 * correction_hits
    + 4 * skill_intent_hits )                                    AS score
FROM per_session
WHERE is_daemon = 0
  AND (tool_calls >= 5 OR correction_hits > 0 OR skill_intent_hits > 0)
ORDER BY score DESC, last_ts DESC
LIMIT 50
SQL
