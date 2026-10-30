---
name: session-transcript-census
description: Census and search Copilot agent session transcripts across cloud history and local or running sessions. Use when mining past conversations for behavioral examples, locating a named or UUID session, investigating why an agent stopped, or preparing transcript evidence for an evaluation corpus.
---

# session-transcript-census

Build a **census** before selecting transcript evidence. Cloud history, local
session state, running sessions, checkpoints, and retained artifacts are
different sources; an empty result from one source is unresolved, not absence.

## 1. Fix the search boundary

Record:

- the question the search must answer;
- the time window;
- exact phrases and broader behavior classes;
- supplied session UUIDs, task IDs, agent names, workspaces, repositories, and
  branches; and
- whether the result will be a summary, incident trace, or evaluation case.

Treat names as hints. Stable session or task IDs are authority.

**Complete when** every supplied identifier and the observable behavior being
sought are explicit.

## 2. Census session sources

Query both session stores when available:

1. **Cloud history:** time-bound `sessions`, then `turns`, `checkpoints`,
   `session_files`, `session_refs`, and relevant tool evidence by exact
   `session_id`.
2. **Local and running sessions:** use `source: "local"` and SQLite-compatible
   date expressions. List recently updated sessions, then query exact IDs.

Running sessions may appear only in local state, and local timestamps may not
compare correctly with cloud SQL syntax. A supplied session UUID must be
queried directly in both stores even when name or text searches return nothing.

Preserve finite limits and start with 30 days unless the user gives another
window. Record each source queried, query timestamp, filters, and row count.

**Complete when** cloud and local/running coverage is recorded, every supplied
ID has a direct lookup result, and any unavailable source is labeled.

## 3. Find candidate incidents

Search exact user language first, then behavior classes. For premature stops,
include phrases such as:

- `why did you stop`
- `are you stuck` or `you stuck`
- `keep going`
- `you're supposed to`
- `what do you need`
- `any progress`
- `I thought you were going to`
- `don't lose track`

Also inspect nearby scheduled prompts, assistant endings, long timestamp gaps,
checkpoint state, active objectives, and reminder state. A phrase match is a
lead, not proof. Confirm that unfinished ready work existed and distinguish:

- premature completion or idle loss;
- a genuine human-only gate;
- an active owner or dependency wait;
- authentication or protected-input handoff; and
- an attended pause the user actually requested.

**Complete when** each retained incident has a supported classification and
the candidate cutoff is identifiable.

## 4. Export exact evidence

For each retained incident, preserve:

- stable session and task IDs;
- exact turn indexes and timestamps;
- the last pre-stop user request and assistant response;
- the correction turn that restarted or redirected work;
- relevant checkpoints, objective state, schedules, and owner results; and
- connected artifacts or commits.

Screen credentials, tokens, protected input, and private attachments before
writing evidence. Label omissions; a redacted span is not an exact quote.

When building an evaluation case, invoke `skill-evaluation` and follow its
historical-case-capture reference for capture receipts, candidate/judge
boundaries, freezing, and verification.

**Complete when** every behavioral claim maps to exact frozen evidence or is
explicitly marked unavailable.

## 5. Report coverage

Return:

- sources searched and unavailable sources;
- time window and direct identifiers checked;
- candidate and retained incident counts;
- classification for each retained incident;
- exact evidence locations; and
- gaps that prevent claiming the search was exhaustive.

Say “searched all sessions” only when both cloud and local/running sources were
covered for the declared window. Otherwise name the narrower population.

**Complete when** another agent can reproduce the search and distinguish
confirmed absence from an unqueried or unavailable source.

