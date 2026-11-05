# Provider-Native Cross-Client Mailbox Implementation Charter

## Standing objective

Implement and prove the reviewed critical work order at
[`provider-native-cross-client-mailbox.md`](provider-native-cross-client-mailbox.md)
through the exact heading
`Definition of Done: Provider-Native Cross-Client Mailbox`.

## Workspaces and branches

- Skills:
  `C:\Users\dfrysinger\code\skills-provider-mailbox`,
  branch `feature/provider-native-mailbox`, base `7405e75`.
- Agent Stack:
  `C:\Users\dfrysinger\code\agent-stack-provider-mailbox`,
  branch `feature/provider-native-mailbox`, base `1e75ef0`.
- The shared checkouts at
  `C:\Users\dfrysinger\code\skills` and
  `C:\Users\dfrysinger\code\agent-stack` are not implementation workspaces.

Push reviewed commits to the owned feature branches. Do not merge either branch
to `main`.

## Governing contract

**Governing skill:** `/dfrysinger-skills:development-loop`

**Execution skills:**

- `/dfrysinger-skills:secret-hygiene` when provider tokens, authentication,
  secret files, environment variables, process arguments, or logs are handled.
- `/dfrysinger-skills:dual-review` for the final non-trivial implementation
  diff and any required pre-implementation invariant guard.

**Context skill:** `/dfrysinger-skills:self-compact`

`unattended-run` owns only this charter's schedule and native objective
continuity.

## Authority and fixed boundaries

- Exact decisions:
  [`provider-native-cross-client-mailbox-decisions-v2`](provider-native-cross-client-mailbox-decisions.json).
- Current constraint gate:
  [`CONTINUE`](provider-native-cross-client-mailbox-constraint-challenge.md).
- Approved design review:
  [`provider-native-cross-client-mailbox-design-review.md`](provider-native-cross-client-mailbox-design-review.md).
- Lane: **Critical**.
- Reframe status: `CLEAR`.

Provider-aware schemas, self identity, existing marker evolution, Copilot reuse,
bounded Claude/Codex probes, session-child watchers, one Codex app-server per
launch, and platform-specific enablement are admitted.

Not admitted: automatic upgrade/restart, endpoint registry, heartbeat, durable
provider token, new lock, takeover file, sender-side Claude/Codex control,
broker, resident supervisor, terminal injection, or protected login
automation.

## Current baton

```yaml
phase: provider_adapter_implementation
candidate: mailbox_core_commits_2a4debe_4b164ba_3a52b85
current_gate: CONTINUE
open_reframe_condition: none
design_status: implementation_active
last_constraint_review: provider-native-cross-client-mailbox-v5-focused-CONTINUE
last_design_review: dual-review-round-3-passed
next_action: integrate the admitted Claude and Codex adapters
implementation_objective_handoff:
  handoff_id: provider-native-mailbox-implementation-cycle-1
  status: resolved
  objective_file: C:\Users\dfrysinger\code\skills-provider-mailbox\design\provider-native-cross-client-mailbox-implementation-objective.txt
  target_session: 558f4b0e-bb69-57bf-8c84-e93e01d8a3a7
  receipt: C:\Users\dfrysinger\.copilot\autopilot-enqueue\20261103T200714475Z-13684-7ce98838.json
schedule_registry:
  charter_check:
    id: 4
    interval: 4h
    status: live
  progress:
    id: 5
    interval: 1h
    status: live
  superseded_design_progress:
    id: 3
    interval: 30m
    status: stopped
```

No material user direction arrived after the current challenge. The latest
exact statements remain:

- `"the sessions could be running but just need to be idle"`
- `"yes using agent stack, if its not an agent stack agent session then no"`

Those statements authorize a later repair flow but do not add it to this
implementation.

## Critical path

1. Add red/green guards for address grammar, Windows-safe mailbox/state path
   mapping, provider self identity, outcome marker replay, watcher generation,
   and provider-qualified remote transport.
2. Run bounded Windows mechanism probes:
   - Claude native pipe framing, reply semantics, hook re-fire, terminal
     endpoint errors, and transient busy behavior.
   - Codex installed-version remote resume, token handling, exact loaded
     thread, `turn/start` race, `expectedTurnId`, and child cleanup.
3. If a probe fires the reframe gate, stop that adapter and return to the work
   order. Continue independent admitted work.
4. Implement provider-aware mailbox core and Copilot compatibility.
5. Implement Claude and Codex session-child watchers only after their probes
   pass.
6. Integrate exact provider identity and managed launch in Agent Stack on
   Windows, then macOS per provider after platform proof.
7. Freeze one cross-repository candidate, run deterministic suites, register
   and validate live-proof receipts, run dual implementation review, fix and
   replay reached claims, then push both owned branches.

## Critical-path audit

Run this audit at task start, compaction/resumption, candidate movement, every
phase boundary, failure, ownership handoff, and material user direction:

1. Rebuild remaining dependencies and identify the current critical path.
2. Assign each substantial independent ready scope to one explicit owner in an
   isolated worktree, or name its real dependency.
3. Record owner ID, writable paths, workspace/branch, evidence owed, blockers,
   and integration boundary.
4. Read explicit owner results before reporting or transferring ownership.
5. Keep the coordinator on integration, decisions, unblocking, and unowned
   critical-path work.
6. Preserve one live-proof owner for each frozen candidate and fixture.
7. Compare every systemic/critical next action with the current constraint
   gate. Reinvoke `constraint-challenge` only for a material scope,
   architecture, trust, authority, policy, or reframe trigger.
8. Batch coherent fixes before expensive proof and reuse unaffected evidence
   only through checked applicability.

## Owner roster

| Assignment | Owner route | Scope | Writable paths | Workspace | Evidence owed | Integration boundary |
| --- | --- | --- | --- | --- | --- | --- |
| `mailbox-guards-v1` | `2c7fd513-9f4f-409c-beda-2b0a0870f31f` | Complete; integrated as `2a4debe` | none | Frozen worktree `C:\Users\dfrysinger\code\skills-provider-mailbox-guards` | 30-case red baseline | Closed. |
| `claude-adapter-implementation-v1` | `d676e2d4-50b8-4f01-ad89-e9095e5177ec` | Implement admitted native Windows Claude hook and watcher | New scripts and focused tests only | `C:\Users\dfrysinger\code\skills-provider-mailbox-claude-adapter`, branch `feature/provider-native-mailbox-claude-adapter` | Commit SHA, deterministic tests, secret-hygiene and lifecycle assumptions | Coordinator consumes explicit handoff before inspecting or integrating the worktree. |
| `codex-adapter-implementation-v1` | `be728075-4340-4e55-9be5-a61fb3e5e2eb` | Implement admitted authenticated app-server watcher | New scripts and focused tests only | `C:\Users\dfrysinger\code\skills-provider-mailbox-codex-adapter`, branch `feature/provider-native-mailbox-codex-adapter` | Commit SHA, protocol tests, secret-hygiene and lifecycle assumptions | Coordinator consumes explicit handoff before inspecting or integrating the worktree. |

The coordinator owns design, integration, Agent Stack launch changes, and later
cross-repository candidate proof. No file-writing scopes overlap.

## Proof obligations

The source stage owns:

- every deterministic check in the work order;
- real native Windows Copilot-to-Claude and Copilot-to-Codex delivery;
- exact receiver acknowledgements and replies;
- fail-closed unsupported/unmanaged behavior;
- absence of tokens from durable and user-visible surfaces;
- no terminal input;
- no automatic provider process or binary change.

macOS native replacement is enabled and old tmux wakeup removed separately for
each provider only after that provider's macOS proof. If this machine cannot
produce macOS proof, keep that later-stage obligation pending and do not claim
the full Definition of Done.

## Schedule registry

The four-hour charter check and hourly progress nudge replace the 30-minute
design-incubation reminder only after both are confirmed live. Stop all three
when the full Definition of Done is verified.
