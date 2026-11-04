# Foreground mailbox ownership

## Outcome and scope

A named Copilot terminal delivers mailbox work to its displayed conversation,
not every SDK session still attached to that process. Agent Stack must also
exclude retired conversations when selecting a session to resume.

The lane is **systemic**: session-control and mailbox-watcher share terminal
identity. The existing native host remains the only foreground authority.
There is no new service, listener, registry, ownership election or lock.
Provider-native Claude/Codex delivery, authentication, mailbox durability,
explicit exact-session maintenance and session rotation are otherwise unchanged.
Running user sessions and pending user mail are not acceptance fixtures.

## Authority and constraints

The implementation direction is the user's request:
"hi lets fix agent stack so this situation with delta cant happen again".
The decision and discovery packet is `foreground-evidence.json` in the
implementing session's artifacts, revision `foreground-evidence-v1`.
It distinguishes implementation authority from permission to disrupt a live
session. No restart, worker kill, upgrade, barrier deletion or terminal input
is part of this repair's deployment.

The observed failure has two writers: two extension workers under one CLI
host continue publishing the same terminal name after a conversation resume.
Their heartbeat freshness and the host's launch argument cannot establish
which conversation is displayed. Existing request arbitration correctly
refuses the resulting ambiguity.

Native `session.getForeground` supplies the actual foreground session over
the extension's existing parent connection. An isolated CLI probe established
that this works without a TCP listener. The SDK's public client method uses
this RPC, but the joined extension session exposes its connection only as a
TypeScript-private property. Keep that dependency in one compatibility helper.
If it is absent or fails, do not guess an owner. Revisit this seam when the SDK
exports a foreground accessor or changes its transport shape.

Keep the existing identity lookup timeout: it already bounds metadata and tmux
reads and prevents stalled identity work from retaining a mailbox claim.
This is an inherited operational timeout, not a correctness requirement.
Tests must prove timeout refusal, not depend on a faster arbitrary threshold.

## Existing owners and changes

1. `session-control/session-identity.mjs` gains a bounded foreground query.
   `preferredAgentName` returns no name unless the joined session is foreground.
   A missing foreground session, unsupported query, malformed reply or failed
   lookup is not permission to retain a prior terminal claim.
2. `session-control/extension.mjs` uses that answer when publishing aliases.
   Background workers retain exact-session addressing but withdraw tmux and
   display-name aliases. Revalidate foreground immediately before admitting a
   name- or tmux-targeted side effect. Reject a stale named request with a
   definitive no-side-effect result; do not silently retarget its generation.
3. `mailbox-watcher/extension.mjs` reuses `preferredAgentName`. Foreground loss
   stops local/import watchers and releases their existing locks. Foreground
   return restarts them through the same existing identity refresh path.
4. Agent Stack's existing selector excludes each session directory containing
   `rotation.barrier`, independently of cached workspace metadata. Recheck a
   selected or deterministic fallback UUID before launch. If it is retired,
   choose a fresh UUID rather than resurrecting it. Do not remove any marker.

Name ownership is sampled at request admission. A native send already admitted
while its conversation was foreground may finish after a subsequent switch.
This patch does not cancel accepted turns or provide an atomic query-and-send
operation that the host does not expose.

Exact-session operations remain deliberate addressing, subject to all existing
generation, rotation, deduplication and confirmation checks. No new capability
or permission grant is required. Existing safeguards remain in force; owner
approval is not replaced with a blanket ban on exact-session maintenance.

## Acceptance and check contract

| State or trigger | Required observable result |
| --- | --- |
| Two joined sessions share a terminal; foreground changes A to B | Only B publishes terminal aliases; A stays exact-addressable |
| Foreground lookup is absent, malformed, rejected or times out | No named claim or new named side effect; existing watcher is stopped |
| A named request resolved to A waits until foreground becomes B | A produces a definitive refusal without sending a turn |
| An exact-session maintenance request targets background A | Existing maintenance behavior and rotation refusal remain intact |
| Pending fixture mail exists during an in-process resume | Existing mailbox path confirms delivery to B; A's conversation is untouched |
| Native or wrapper retirement marker exists, including warm cache or fallback | Launcher does not resume that UUID; marker and transcript are unchanged |
| Duplicate real foreground claims from separate processes | Existing ambiguity refusal remains; no newest-worker election |

Use focused identity, extension, resolver and launcher tests for deterministic
state ordering and failure paths. Exercise the candidate extensions in a real,
owned CLI terminal and switch/resume without replacing its host process.
Keep mailbox roots isolated and inspect native delivery confirmation, not
only the request's exit status. Test duplicate workers, unavailable foreground,
exact-session maintenance and pending mail separately from historical Delta.

## Reframe and rollback

`reframe_status: CLEAR`: the successful native query and existing identity
refresh/watch teardown satisfy the supported caller without a new state owner.
Stop and revisit the design if foreground is unavailable over the existing
connection, if correctness needs a new registry/election, or if proof requires
changing a real user's session or permission policy. Do not add those surfaces
as an incidental implementation repair.

The change is additive source with no migration. Rollback restores the prior
extension and launcher files. Mail and conversation data are never rewritten.
Unsupported runtimes lose name-addressed wakeup rather than guessing a target;
exact-session maintenance and durable pending mail remain recoverable.
Installation or reloading a live session is a separate deployment step.

## Definition of Done: foreground mailbox identity

- The focused state-transition tests and real isolated resume/delivery proof pass.
- Both shared consumers use the same foreground authority and withdraw old claims.
- Exact-session maintenance, ambiguity and rotation protections remain intact.
- Launcher excludes native retirement markers without invalidating unrelated edits.
- The source and its tests are reviewed and published on isolated owned branches.
- Runtime deployment status is stated separately; no live Delta changes are implied.
