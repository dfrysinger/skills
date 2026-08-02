# Evidence-backed self-learning plan

## Objective

Make the personal self-learning system improve the quality of future work, not
merely grow a well-formatted skill library.

Every lesson must be routed to the right destination, carry enough evidence to
explain why it was retained, and pass a proportionate quality check before it
is promoted or materially rewrites an existing skill.

The system remains a personal, local proving ground. It does not become a
centralized memory service or duplicate product-level agent-learning
infrastructure.

## User outcome

The owner can answer these questions for every agent-created skill:

1. What repeated problem caused this skill to exist?
2. Which independent tasks support the lesson?
3. Why is this a skill rather than an instruction, factual memory, reference,
   or discarded observation?
4. When was its important evidence last checked?
5. Did it improve the task it was meant to help without harming a related task?
6. What scheduled work depends on it?
7. How can one complete curator run be undone?

## Lane

Systemic.

The work changes provenance metadata, creation and review contracts, promotion
gates, curator authority, validation, and rollback across multiple skills and
both managed roots.

## Lessons carried forward

This design combines four proven patterns without copying their scale:

- Keep always-loaded guidance small and move procedures behind on-demand skill
  loading. Claude Code documents this split between persistent instructions,
  bounded auto memory, and skills.
- Use provenance and lifecycle management for agent-created content. Hermes
  demonstrates pins, recoverable archives, dry runs, and curator-owned
  provenance.
- Verify factual claims against current evidence at use time rather than trying
  to reconcile every change continuously. GitHub Copilot Memory documents this
  citation-based approach.
- Measure whether a learned procedure helps and whether it damages related
  tasks. A structurally valid skill is not necessarily a useful skill.

Public references:

- https://code.claude.com/docs/en/memory
- https://hermes-agent.nousresearch.com/docs/user-guide/features/curator
- https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/

## Existing system to extend

Reuse the current owners instead of adding another learning subsystem:

- `skill-review` discovers lessons, patches skills, and creates new local
  agent-created skills.
- `skill-create` defines the authoring and validation contract.
- `memory-curator` migrates durable memories into skills before safe deletion.
- `skill-curator` proposes consolidation and reversible archival.
- `.agent-created.json` records provenance for curator-managed skills.
- The review ledger, tombstones, shared writer lease, dry-run approval gate,
  Git commits, self-test, and watchdog continue to own their current concerns.

## Core decisions

### 1. Route before writing

Use one artifact-routing contract in every learning path:

| Destination | Use for | Do not use for |
|---|---|---|
| Instruction | A stable rule that should influence nearly every relevant turn | Multi-step procedures or changing project facts |
| Factual memory | A concise current fact or user preference whose truth can change | Procedures or large reference material |
| Skill | A reusable procedure with a trigger, ordered policy, observable stopping condition, and clear interface | One-off narratives, facts, or advice without an executable process |
| Support file | Detailed reference, template, script, or reproduction material used by an existing skill | A separately invokable procedure |
| Discard | Transient failures, duplicated knowledge, unsupported beliefs, or lessons too narrow to reuse | Evidence-backed reusable behavior |

The router must allow an explicit `discard` result. Producing no artifact is a
successful outcome when the evidence does not justify persistence.

Instruction and factual-memory destinations are recommendations in M1, not
unattended writes. The review ledger records their destination and reason so
they remain distinguishable from discard. A later explicit owner action or the
existing memory surface may apply a recommendation. Factual memory is limited
to concise, volatile, non-procedural facts or preferences that the owner is
likely to ask about again; anything a skill can carry belongs in the skill.

`memory-curator` retains its existing `roll | dup | obsolete | keep`
categorization as the sole deletion authority. The shared routing contract
governs only whether a rolled lesson belongs in a skill, support file, or no
new artifact. `obsolete` and `keep` never become deletable merely because the
artifact router returns discard. Only rolled or exact-duplicate memories enter
the existing delete list.

### 2. Extend the existing provenance envelope

The `.agent-created` file remains the curator authority marker.
`.agent-created.json` gains a versioned evidence envelope:

```json
{
  "schema_version": 2,
  "skill": "example-skill",
  "created_by": "skill-review",
  "source_session_id": "uuid",
  "source_mode": "dispatch",
  "review_prompt_version": "skill-review-1",
  "created_at": "2026-08-02T00:00:00Z",
  "evidence": [
    {
      "task_key": "task:opaque-uuid",
      "session_id": "uuid",
      "observed_at": "2026-08-02T00:00:00Z",
      "independence": "verified",
      "evidence_kind": "successful-procedure",
      "summary": "A short non-sensitive description of the reusable friction"
    }
  ],
  "routing": {
    "destination": "skill",
    "reason": "Why procedure-level persistence is justified"
  },
  "claims": [
    {
      "claim": "The concrete behavior this skill relies on",
      "verification": "session-evidence",
      "last_verified_at": "2026-08-02T00:00:00Z"
    }
  ],
  "evaluation": {
    "status": "not_evaluated",
    "evaluated_at": null,
    "candidate_id": null,
    "model": null,
    "source_case": null,
    "sibling_case": null,
    "waiver_class": null,
    "waiver_reason": null
  }
}
```

`created_by` is one of `skill-review`, `skill-create`, or `memory-curator`.
`evidence_kind` is one of `successful-procedure`, `failure-recovery`,
`owner-correction`, or `independent-recurrence`. Evaluation status is one of
`not_evaluated`, `pending`, `pass`, `regression`, `inconclusive`, or `waived`.
When status is `waived`, `waiver_class` is one of `documentation-only`,
`reference-only`, or `deterministic-helper`, and `waiver_reason` is non-empty.

`source_session_id` remains a deprecated compatibility mirror of the first
evidence entry's `session_id`. An absent `schema_version` means schema v1.
Lazy v1-to-v2 migration maps `source_session_id` into the first evidence entry,
retains `review_prompt_version`, and preserves all unrecognized fields.
Schema-v1 readers therefore continue to find their named scalar fields while
schema-v2 readers use the evidence list.

The envelope contains summaries, identifiers, and local evidence only. It must
not copy repository content, conversation transcripts, credentials, internal
URLs, or private proper nouns into the public repository.

Promotion from local to public strips the private evidence envelope as it does
today. All private evidence lives in `.agent-created.json`, not in support
files. The public skill keeps only publishable technique.

### 3. Count independent tasks, not mentions

Evidence strength is the number of distinct task instances supporting the same
procedure, not the number of messages or sessions that repeat one incident.

A distinct task differs in at least one meaningful dimension: user ask, day,
target repository or project, input, failure mode, or correction.

Each evidence entry carries an opaque `task_key`. Prefer a platform task ID
when one exists. Otherwise the task owner mints a random opaque UUID once, and
the handoff or rotation baton carries it explicitly into continuation sessions.
Task identity must never be derived from repository names, dates, asks,
failure text, session IDs, or other private or collision-prone content.

Dispatch resolves task identity in this order: platform task ID, explicit
handoff/rotation task key, then a newly minted UUID for a task that is known to
start in the current session. A scheduled sweep that cannot prove whether a
historical session starts or continues a task records the observation as
`independence: "unverified"` and does not increase evidence strength. Verified
distinct task count is derived from unique task keys on entries whose
`independence` is `verified`; it is not stored separately.

One task may justify a local draft when the procedure is expensive to
rediscover. It does not justify promotion or broadening without a recorded
reason.

### 4. Verify changing claims at the boundary

Procedural steps can be durable while factual assumptions change.

Claims tied to code, tool behavior, paths, versions, or service capabilities
must say how they are verified:

- `current-source`: reread the named current source before relying on it;
- `deterministic-check`: run the named script or command;
- `session-evidence`: the claim is historical context, not a current fact;
- `owner-policy`: the claim is an explicit stable user policy.

The skill body should point to verification where a stale claim could produce a
wrong action. The system does not add citations to every sentence.

### 5. Evaluate effect before promotion or major rewrite

Creation remains cheap; authority becomes earned.

Evaluation is required when:

- promoting a local agent-created skill into the public plugin;
- replacing or broadening a class-level umbrella;
- a curator consolidation materially changes how an existing skill executes;
- a skill is implicated in a repeated regression.

The minimum evaluation has two cases:

1. **Source case:** a representative task the skill is intended to improve.
2. **Sibling case:** a related task where an overfitted rule could cause harm.

Run each case with and without the candidate skill when practical. Record:

- terminal success or failure;
- observable acceptance checkpoints;
- unnecessary or harmful actions;
- model, candidate identity, and evidence paths.

The gate passes when the candidate improves the source case or preserves an
already successful result while reducing meaningful friction, and it causes no
material sibling regression.

An evaluation may be explicitly waived only for a documentation-only,
reference-only, or deterministic helper change whose effect is already fully
proved by existing tests. The waiver carries a reason.

Promotion and major rewrites use an allowlist: only `pass`, or `waived` with a
valid enumerated waiver class and non-empty reason, may proceed.
`not_evaluated` triggers a fresh evaluation; `pending`, `regression`, and
`inconclusive` remain local.

### 6. Protect scheduled dependencies

A skill referenced by an installed LaunchAgent, daemon prompt, or durable
scheduled configuration is treated as implicitly pinned.

The curator may report it but may not place it in `consolidations:` or
`prunings:` until the dependency is removed or retargeted.

Session-only reminders that cannot be enumerated reliably remain outside the
automatic guarantee. Their owners must pin long-lived dependencies explicitly.

### 7. Roll back a complete curator run

Git remains the storage and reversal mechanism. Add a run manifest rather than
another backup format.

Before live mutation, record:

- dry-run report path and approval timestamp;
- public and local root starting commits;
- pre-existing dirty paths;
- planned consolidations and prunings.

After each scoped commit, append its root and commit ID. Also record every
tombstone written and every curator-ledger entry appended. A rollback command
reverses commits in reverse order, clears only the recorded tombstones and
ledger effects through existing restore semantics, refuses unrelated or
ambiguous state, and writes a second manifest for the rollback itself.

No hard reset, broad checkout, or deletion is allowed.

## Data flow

### End-of-task learning

1. `skill-review` acquires the shared writer lease before its first mutation
   and renews it immediately before every envelope, content, commit, or ledger
   write.
2. `skill-review` identifies a candidate lesson.
3. The routing contract chooses instruction, memory, skill, support file, or
   discard.
4. Skill/support-file routes search loaded skills and both roots for reuse.
5. The evidence helper initializes or appends the versioned envelope using a
   locked temporary file, `fsync`, and atomic replace. For a new agent-created
   skill it writes and validates the envelope first, then creates the authority
   marker. A valid envelope without a marker is an incomplete draft that the
   helper may resume. A marker without a valid envelope is quarantined until an
   explicit re-stamp supplies the missing source inputs; no autonomous caller
   may infer them.
6. `writing-great-skills`, validation, and `dual-review` govern content.
7. The local commit and review ledger are written under the same lease. Ledger
   entries include routed outcomes with destination, reason, and task key so
   recommendation and discard paths are observable.

### Scheduled consolidation

1. Daily sweep selects unreviewed sessions.
2. Routing and evidence recording use the same helpers as dispatch.
3. Existing evidence is appended only when the task is genuinely distinct.
4. The weekly curator uses evidence strength, usage, project completion,
   scheduled dependencies, and evaluation status in its dry-run proposal.

### Promotion

1. Publishability gate removes private/project-specific details.
2. A promotion inventory lists every file in the skill. Every listed file,
   including support files, is included in the existing independent review and
   must be explicitly classified public-safe. Known private sentinels,
   transcript markers, credentials, private URLs, and unresolved task-specific
   reproductions fail closed.
3. Evidence gate checks the required source and sibling cases.
4. Promotion strips local provenance files.
5. Public validation, review, versioning, commit, push, and plugin refresh run
   through existing paths.

## Failure model

| Failure | Required behavior |
|---|---|
| No marker and no envelope | Treat as hand-made and preserve the existing recommendation-only path |
| Agent-created marker with missing or malformed envelope | Fail closed before autonomous create, promotion, or curator mutation |
| Valid envelope without marker | Treat as an incomplete draft; resume marker creation only under the writer lease |
| Envelope present but schema-invalid | Fail closed before autonomous mutation |
| Source session unavailable | Keep existing content; record evidence unavailable |
| Duplicate evidence | Do not add the existing task key |
| Factual claim cannot be verified | Do not use the claim; correct or narrow the skill |
| Evaluation is inconclusive | Keep local draft; do not promote or broaden authority |
| Sibling regression | Reject the candidate change and retain the prior skill |
| Scheduled dependency discovery fails | Do not archive or consolidate the candidate |
| Curator run partially commits | Manifest remains incomplete; rollback or resume explicitly |
| Rollback encounters unrelated changes | Refuse and report exact blocking paths |

## Security and privacy

- Evidence metadata stays in the local root and local state.
- Public promotion removes `.agent-created` and `.agent-created.json`; its
  complete file inventory and review gate reject private evidence elsewhere.
- Evidence summaries must not contain credentials, tokens, private URLs,
  transcript text, or copied private code.
- Current-source verification follows the caller's existing repository access;
  the envelope grants no new access.
- Citation or source text remains untrusted input.

## Milestones

### M1: Routing and evidence envelope

Deliver:

- one public-safe artifact-routing reference shared by `skill-review`,
  `skill-create`, and `memory-curator`;
- existing routing prose in those callers is replaced with links to the shared
  contract rather than retained as a second artifact-routing authority;
- `memory-curator` retains its separate deletion categorization and maps only
  its rolled skill-write path through the shared artifact router;
- a versioned evidence-envelope helper;
- backward-compatible migration of existing `.agent-created.json` files;
- creation and patch flows that initialize or append evidence;
- review-ledger support for routed non-artifact outcomes;
- validator and deterministic tests;
- curator reads evidence but does not yet enforce evaluation status, including
  a compatibility check for every provenance field its prompt names.

Acceptance:

- a reusable procedure routes to a skill and records one source task;
- a factual observation routes away from skill creation;
- a transient or unsupported observation routes to discard;
- repeated evidence from the same task does not add another task key;
- a distinct second task adds another task key;
- a handoff or rotation carrying the same task key remains one verified task;
- an unlinked historical session remains unverified rather than inflating
  evidence strength;
- legacy provenance remains readable;
- schema-v1 readers retain the scalar source-session and prompt-version fields;
- malformed evidence fails closed before autonomous mutation;
- public promotion still strips local provenance, and no `.agent-created*`
  path exists in the public root;
- a private sentinel in either `SKILL.md` or a support file blocks promotion;
- obsolete-but-unrolled memory never enters the memory-curator delete list.

### M2: Evaluation gate

Deliver:

- source/sibling case manifest;
- with/without-skill runner using the existing bounded Copilot harness;
- result comparison and waiver record;
- required gate for promotion and major umbrella rewrites;
- a small regression fixture proving an overfitted skill can fail the sibling
  case.

Acceptance:

- a helpful candidate passes;
- an overfitted candidate is rejected;
- an inconclusive run stays local;
- every result is tied to an exact candidate and model identity.

### M3: Dependency protection and run rollback

Deliver:

- installed LaunchAgent and daemon-prompt dependency scanner;
- curator implicit-pin integration;
- live-run manifest across both roots;
- reversible commit-based rollback command;
- interrupted-run and unrelated-dirty-path tests.

Acceptance:

- a scheduled skill cannot be proposed for archive;
- retargeting the schedule removes the implicit pin;
- a multi-root curator run can be reverted in one command;
- rollback refuses to overwrite unrelated work.

### M4: Hot-context budget

Investigate the available Copilot memory surfaces before implementation.

Deliver only if the platform exposes an enforceable local boundary:

- a visible budget for always-loaded personal instructions and memory;
- routing pressure that moves procedure detail into skills;
- warnings rather than silent truncation.

Do not build a second memory store solely to create a budget.

## Deterministic check contract

### Routing

- Each destination has one positive fixture.
- Ambiguous input resolves to discard or manual review, never forced creation.
- Routing records accept only the five named destinations and require a
  non-empty reason and task key.
- Unknown or malformed destinations fail validation.
- Destination correctness is a live model acceptance property, not a
  deterministic model-output assertion.

### Evidence envelope

- Initialize schema v2 atomically.
- Read legacy schema v1.
- Preserve the v1 scalar compatibility fields in schema v2.
- Append a distinct task.
- Deduplicate the same task.
- Derive distinct task count from unique verified task keys.
- Preserve one task key across a simulated handoff and rotation.
- Distinguish two same-repository, same-day tasks with separate minted keys.
- Exclude unverified historical observations from evidence strength.
- Reject invalid destination, missing task key or source ID, invalid timestamp, and
  malformed JSON.
- Preserve unknown future fields during updates.
- Treat no-marker/no-envelope skills as hand-made; reject marker-without-envelope.
- Resume a valid envelope-without-marker draft and require explicit inputs to
  repair marker-without-envelope.
- Confirm every provenance field named by the curator resolves on schema v2.
- Confirm promotion leaves no `.agent-created*` path in the public root.
- Confirm private sentinels in `SKILL.md` and support files block promotion.
- Confirm an obsolete-but-unrolled memory is never placed on the delete list.

### Evaluation

- Candidate identity covers every runtime input.
- Source and sibling cases cannot share the same task identifier.
- Pass, regression, inconclusive, and waiver states are explicit.
- Promotion and major rewrite gates allow only `pass` or a valid narrow
  `waived` record.
- `not_evaluated` triggers evaluation; `pending`, `regression`, and
  `inconclusive` are rejected.

### Scheduled dependencies

- Detect direct skill references in installed daemon prompts and LaunchAgents.
- Ignore archived skills and unrelated text.
- Fail closed when dependency enumeration is incomplete.

### Rollback

- Record both roots and every created commit.
- Record every tombstone path and curator-ledger mutation.
- Revert in reverse order.
- Restore archived skills through existing restore semantics.
- Preserve unrelated dirty paths.
- Refuse missing commits, rewritten history, or ambiguous root identity.
- Record rollback as a reversible operation.

## Live acceptance

### M1 live acceptance

Run a real end-of-task review against three controlled sessions:

1. reusable procedure → skill + evidence envelope;
2. changing factual observation → factual-memory recommendation, no skill;
3. transient failure → discard, no artifact.

Inspect the actual local root, envelope, review ledger, and absence of public
repository changes. The first controlled pass must be 3/3. If one case
disagrees, rerun that unchanged case once to distinguish variance from a
reproducible misroute. A repeated misroute requires a corrected prompt or
contract. An isolated miss is recorded as variance, but the gate remains closed
until that case produces two consecutive correct unchanged runs.

### M2

Run the real model on a source/sibling fixture pair with and without one
candidate skill. Confirm the useful candidate passes and an intentionally
overfitted candidate fails.

### M3

Create a disposable local skill referenced by a test LaunchAgent, prove the
curator protects it, remove the reference, execute a reversible two-root test
run, and roll it back without touching unrelated fixtures.

## Rollout and compatibility

- Schema v1 provenance remains valid throughout M1.
- Schema v2 is written only after its reader and validator are installed.
- Existing skills are migrated lazily when new evidence is appended.
- No bulk migration is required to deploy M1.
- Evaluation begins advisory, then becomes mandatory for promotion and major
  rewrites only after the live acceptance suite passes.
- M1-created envelopes begin as `not_evaluated`. Once M2 ships, promotion of a
  pre-gate skill triggers a fresh evaluation rather than requiring a bulk
  backfill.
- Curator mutation remains dry-run plus explicit approval.
- Every milestone is separately releasable and reversible.

## Definition of Done

### Plan

- [x] Objective, non-goals, reuse contract, data flow, failure model,
      privacy boundary, milestones, tests, live acceptance, rollout, and
      rollback are explicit.

### M1 Definition of Done

- [x] Artifact-routing contract is one shared source of truth.
- [x] Evidence-envelope schema and helper are implemented and documented.
- [x] Legacy provenance is backward compatible.
- [x] Dispatch, sweep, creation, and memory-roll paths use the routing contract.
- [x] Evidence deduplication counts independent tasks rather than mentions.
- [x] Malformed evidence fails closed before autonomous mutation.
- [x] Deterministic routing, schema, migration, and guard tests pass.
- [x] Real three-case acceptance produces skill, factual-memory recommendation,
      and discard outcomes with no public mutation.
- [x] Dual review has no verified in-scope material finding.
- [x] M1 is pushed, installed, and observed through the existing self-test.

### Later milestones

- [ ] M2 evaluation gate is implemented and rejects an overfitted skill.
- [ ] M3 scheduled dependency protection and run rollback are implemented.
- [ ] M4 is either implemented against a real platform boundary or explicitly
      closed as unnecessary.

### All phases Definition of Done

- [x] M1 routing and evidence envelopes are released and installed.
- [ ] M2 measures source benefit and sibling regressions, and gates promotion
      or major rewrites.
- [ ] M3 protects scheduled dependencies and reverses a complete multi-root
      curator run without overwriting unrelated work.
- [ ] M4 either enforces a real visible hot-context budget or records evidence
      that no enforceable local boundary exists and closes without a second
      memory store.
- [ ] Every implemented milestone has deterministic coverage, a matching live
      proof, clean dual review, a released version, and installed self-test
      evidence.

## Explicit non-goals

- Build a centralized multi-user service, scheduler, artifact database, or
  approval UI.
- Replace GitHub Copilot Memory or duplicate repository-fact storage.
- Copy private session content into a public skill or commit.
- Require citations for timeless procedural wording.
- Evaluate every small wording or reference-only edit.
- Automatically publish agent-created skills.
- Make curator mutation unattended.
- Introduce a second writer lock, ledger, or provenance authority.
