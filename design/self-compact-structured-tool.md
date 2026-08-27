# Self-Compact Structured Tool

## Result

Self-compact now carries its steering brief in one structured extension tool
argument rather than a visible assistant message. The extension API is one
string, `brief`, so the skill can revise the internal brief format later
without changing every caller or migrating the tool schema.

## Ownership

- `extensions/self-compact/extension.mjs` owns the model-facing tool, its
  one-argument schema, basic size and structure validation, and the handoff to
  the existing submitter.
- `skills/self-compact/scripts/submit-compact.sh` owns authorization. It accepts
  only the SDK tool-call ID, finds that exact running `self_compact` request in
  the current session event log, extracts the persisted `brief` argument, and
  arms the detached verifier.
- `skills/self-compact/scripts/resume-after-compact.sh` remains the crash-safe
  verifier. It waits for the same tool call to complete with the matching
  handoff receipt and for the assistant turn to end before it creates one
  session-inbox compaction request.
- `extensions/session-inbox` remains a general local SDK transport. It owns the
  native `history.compact` call and the fixed continuation, but no
  self-compact skill policy.

## Sequence

1. The agent builds one brief beginning with `Keep:`, containing `Drop:`, and
   ending with an `After compaction:` instruction that includes the exact words
   `do not compact again`.
2. The agent calls `self_compact` as the only and final tool request in the
   root assistant turn. The brief is not printed in assistant prose.
3. The extension validates the brief, then launches the submitter with only
   the current session ID and SDK tool-call ID. The brief is never placed in a
   shell argument or environment variable. The extension does not impose a
   second process timeout; the submitter owns its bounded scan and verifier
   startup budgets, so it cannot be killed after transferring verifier
   ownership but before returning the handoff receipt.
4. The submitter recovers the brief from the persisted tool request, writes the
   private instruction artifact, acquires the existing session lock, launches
   the verifier, and returns a unique handoff receipt.
5. The extension returns that receipt as the structured tool result.
6. After the exact tool completion and assistant turn end are persisted, the
   verifier sends one deduplicated compact request through session-inbox.
7. The verifier proves the token-bound compaction event, summary-count advance,
   one numbered checkpoint, and one fixed continuation before releasing the
   lock.

## Why this boundary

Putting the tool in its own extension keeps workflow-specific policy out of the
generic session-inbox transport. Reusing the detached verifier preserves the
already-tested crash survival, exclusion, receipt, checkpoint, draft
non-interference, and ambiguity behavior instead of rebuilding those guarantees
inside a process whose lifetime is tied to the current CLI session.

The tool call is private from normal chat prose, not secret. Its arguments
remain available in collapsible tool activity and the local session event log
for diagnosis. Generic diagnostics must not copy the brief.

The submitter rejects any matching tool request whose assistant message also
contains prose. Its foreground retry scans only the newest 1 MiB of the event
log because the running request and execution-start events are appended at the
tail; the detached verifier retains the larger historical scan bound needed for
the rest of the turn and compaction lifecycle.

## Limits

The current validator still understands the `Keep:`, `Drop:`, and
`After compaction:` format. That is deliberately implementation policy rather
than API shape: changing it requires coordinated edits to the skill, extension
validator, submitter validator, and tests, but not a new tool parameter schema.

The session event protocol has no atomic "run after this turn" operation. The
detached verifier therefore remains necessary to wait until the authorizing
tool call and turn have both finished without deadlocking the tool handler.
