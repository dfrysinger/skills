# Provider-Native Cross-Client Mailbox Design Review

## Result

**Gate:** Passed
**Subject:** `provider-native-cross-client-mailbox-design-v6-draft`
**Constraint gate:** `CONTINUE`
**Reviewer families:** Claude Opus 5.5 and GPT-5.6 Terra
**Final material findings:** 0

Both reviewers applied the design architecture and scope lens. The review used
the exact work order, evidence packet, decision record, constraint-challenge
record, existing local-first mailbox design, and Windows Agent Stack design.

## Round 1

Claude completed the discovery pass and found:

1. Claude and Codex receivers lacked provider-qualified self identity.
2. Claude SessionStart re-fire could leave no live watcher.
3. Existing notification markers could not represent submitted, held, or
   refused outcomes without false verification or repeated prompts.

Terra's discovery pass was incomplete pending a Codex native mechanism gate and
found:

1. Codex remote launch did not bind the watcher to the provider-selected
   durable thread.
2. Provider-qualified `@machine` transport had no publish/import integration
   check.

The work order added `MAILBOX_SELF_ADDRESS`, one Windows-safe key mapping for
mailbox and state paths, Claude waiter handover through the existing watcher
lock, outcome detail in existing `.unverified` markers, an exact pre-code
Codex remote-resume probe and per-attempt thread check, and a
provider-qualified immutable remote transport check.

## Focused scope reconciliation

A focused constraint recheck removed unsupported additions from the first fix:

- no takeover file or second lock;
- no session-ID watcher identity;
- no explicit retry command;
- no new receipt store;
- no Codex registry or stored thread binding;
- `.notified` stays compatible;
- only `.unverified` gains structured outcome detail;
- a changed Claude socket creates one non-acting waiter on the existing lock.

The current constraint gate returned to `CONTINUE`.

## Round 2

Both reviewers completed fix verification.

Claude verified the self-identity and marker fixes. It found that a stale old
Claude endpoint could fail before authentication and leave the waiter blocked.

Terra verified the Codex probe gate and remote transport check. It found that
the revised prose assigned Codex TUI launch to both Agent Stack and the child
watcher.

The work order now makes terminal pre-write endpoint loss release the existing
Claude watcher lock while retaining the old watcher on platform-specific
transient busy errors. Agent Stack is the sole Codex TUI launch owner; the
watcher only connects to the already-running app-server.

## Round 3

The resolution-only round verified those two exact fixes.

- Claude Opus: prior finding resolved; no new findings.
- GPT-5.6 Terra: prior finding resolved; no new findings.

Both outputs recorded `review_complete: true`,
`design_scope_lens.applicable: true`, and
`design_scope_lens.applied: true`.

## Implementation admission

Implementation may begin with:

- provider-aware address and path schemas;
- `MAILBOX_SELF_ADDRESS`;
- structured existing marker outcomes;
- legacy Copilot compatibility;
- provider-qualified immutable remote transport proof;
- Claude and Codex mechanism probes.

Claude adapter code starts only after its framing, reply, re-fire, and
transient-error probes pass. Codex adapter code starts only after the installed
version proves managed `resume --last --remote`, exact cwd-matching thread
identity, authenticated token handling, turn races, and child cleanup.

No automatic upgrade or restart, endpoint registry, heartbeat, durable token,
new lock, takeover file, sender-side provider control, broker, resident
supervisor, or terminal injection is admitted.
