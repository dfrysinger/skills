# One-Time Migration Constraint Challenge

**Record:** `skill-evaluation-ui-one-time-migration-pass1-r1`
**Pass:** 1 of 2
**Decision:** `NARROW`
**Gate status:** `CONDITIONALLY_OPEN_FOR_NARROW_DESIGN`

## Minimum design

1. Assistant supplies one explicit, reviewable eight-task manifest with source
   paths and digests, project and task bindings, target skill revision, complete
   planned attempts where known, terminal results, and unknown fields.
2. One bounded adapter converts only that manifest into existing project
   declarations and experiment records.
3. Existing frozen-task, attempt, execution, conflict, and exact-population
   validators remain the admission boundary.
4. Source files remain unchanged. The migration stores only safe projected
   fields and opaque source identifiers or digests.
5. Unknown qualification-critical data produces Unavailable.

No permanent importer, historical schema, synchronization service, or new
qualification rule is justified.

## Keep

- Explicit task, source, and skill mappings. Without them, history can qualify
  the wrong task or skill revision.
- Immutable source digests. Without them, migration input can be silently
  substituted.
- Existing exact-population admission. Without it, incomplete or contradictory
  history can qualify.
- Privacy-safe projection and the approved product vocabulary.

## Remove

- A permanent or reusable general importer.
- Identity inference from names, paths, package names, or directory structure.
- New coordination, locking, transport, or shared migration state. There is
  one evidenced migration writer.

## Unresolved deciding evidence

1. Whether Assistant can explicitly bind each historical source to a task and
   target skill revision.
2. Which experiments have a complete planned population and one valid terminal
   result per attempt.
3. Which source fields are safe metadata and which are private.

Each gap blocks only the affected task or its qualification.

## Highest-leverage assumptions

1. Assistant's mapping is authoritative and specific enough to establish task
   identity.
2. Historical records distinguish the complete planned population from an
   observed subset.
3. Safe identity, outcome, and digest metadata can be extracted without
   copying private evidence.

## Gate

- **Permitted scope:** specify the explicit manifest and one-shot adapter,
  reuse current project and experiment validators, migrate individually proven
  tasks, and leave incomplete fields unavailable.
- **Blocked scope:** general importer, inferred bindings, new qualification
  semantics, private evidence projection, new synchronization or locking, and
  qualification without complete-population evidence.

## Smallest next step

Obtain one representative Assistant task entry with its explicit task mapping,
target skill revision, complete planned attempts, terminal results, safe source
paths and digests, and unknown-field statement. Reconcile it against existing
validators before completing pass two.

---

# Pass 2

**Record:** `skill-evaluation-ui-one-time-migration-pass2-r1`
**Decision:** `REFRAME`
**Gate status:** `BLOCKED_PENDING_RECONSTRUCTION_RECONCILIATION`

## Effect

The one-shot manifest and adapter remain the smallest topology, but the
copying premise was false. The source contains eight complete private packaged
cases, not ready current-format roots. The adapter must reconstruct a new
current-format authoring task privately and preserve three revision identities.

## Keep

- One explicit eight-task manifest and one migration writer.
- Existing freeze, project, experiment, result, and exact-population
  validators as final authority.
- The fixed 46-attempt history and separate candidate and control populations.
- `h01` as evaluated candidate only, never historical winner or published
  skill.
- Migration-owned display labels and `development` roles.

## Remove

- Any claim that the packaged roots are current-format roots.
- The generic source task-definition path.
- Digest translation or aliasing between original, packaged, and reconstructed
  revisions.
- Qualification from an outcome without current-validator field
  correspondence.

## Required correction

The work order must specify:

1. deterministic packaged-case to current-format reconstruction;
2. original logical, packaged execution, and reconstructed frozen revisions;
3. exact repaired C06 package selection;
4. field-by-field correspondence to current experiment and result validators;
5. private reconstruction and projection separation; and
6. refusal when a required field cannot be mapped exactly.

## Authority and coordination

The user authorized a one-time migration and qualification when sufficient
evidence exists. Deliberate owner grants for bounded private source reads and
new migration output are allowed. No stricter external policy is evidenced.
Privacy controls govern owner-approved projection; identity controls prevent
untrusted or accidental substitution.

There is one evidenced migration writer, so no additional coordination,
locking, or shared-state mechanism is justified.

## Smallest next step

Correct the work order around the repaired C06 package and current validator
fields, then run one focused reconciliation against that exact bounded action.

---

# Focused reconciliation

**Record:** `skill-evaluation-ui-one-time-migration-reconciliation-r1`
**Decision:** `NARROW`
**Gate status:** `CLEARED_FOR_DESIGN_REVIEW`

The corrected bounded action is cleared after two contract edits:

1. `h01` is the evaluated candidate, not a selected, winning, published, or
   released skill. The migration emits no historical selection event.
2. The reconstructed frozen revision is recorded only in the immutable output
   receipt. It is not an input-manifest field and cannot mutate the manifest
   after reconstruction.

The design now provides exact private reconstruction, non-aliased revision
identities, repaired C06 selection, current-validator field correspondence,
history-only refusal for missing mandatory identity, projection privacy, and
one-writer operation. Two-family design review may start.

---

# Post-review reconciliation

**Record:** `skill-evaluation-ui-one-time-migration-post-review-r1`
**Decision:** `CONTINUE`
**Gate status:** `CLEAR`

Round 1 established that exact-population qualification requires a selected
project-lineage snapshot. The corrected design emits one current
`lineage_declared` event with role `integrated` for the evaluated candidate.
This is an honest current migration fact, not a historical selection:

- no `experiment_selection_recorded` event is emitted;
- no winner, published, or released role is assigned;
- the record identifies migration provenance; and
- the existing lineage owner remains authoritative.

The source-backed per-task threshold, same-root no-write idempotence contract,
and receipt-owned rollback under existing locks are also the smallest
supported mechanisms. One writer remains evidenced. No new authority,
coordination service, or general unregister facility is justified.

The gate remains clear for dual-review round 2.

---

# Implementation-triggered source identity reconciliation

**Record:** `skill-evaluation-ui-one-time-migration-source-identity-r1`
**Decision:** `CONTINUE`
**Gate status:** `CLEAR`

Real package inspection showed that the unchanged authoring
`repository_task.source_revision` and the packaged
`candidateSources[].commit` are distinct for supported tasks. The design now
preserves authoring revision, packaged repository ID, commit, tree, bundle
path, and bundle digest in separate namespaces without asserting equality.

Removing the unsupported equality does not weaken admission. Package bytes,
manifests, hidden authority, and both identities remain independently
digest-verified. No qualification, privacy, immutable-evidence, or security
boundary changes. Implementation may proceed.

---

# Implementation-triggered pre-judge failure reconciliation

**Record:** `skill-evaluation-ui-one-time-migration-pre-judge-fail-r1`
**Decision:** `CONTINUE`
**Gate status:** `CLEAR`

Two verified terminal FAIL attempts ended before independent judges ran.
Inventing judge verdicts would corrupt evidence, while omitting the terminal
results would corrupt the fixed population. The current result contract may
therefore accept an empty independent-verdict list only for terminal FAIL when
at least one deterministic target, regression, or product outcome is exactly
false. Empty is never unanimous PASS and never judge disagreement. All other
terminal results continue to require a nonempty PASS/FAIL verdict list.

This is a bounded additive evidence shape. It changes no result authority,
qualification rule, experiment identity, privacy boundary, or projection
authority. Implementation may proceed.

---

# Implementation-triggered source alias reconciliation

**Record:** `skill-evaluation-ui-one-time-migration-source-alias-r1`
**Decision:** `NARROW`
**Gate status:** `CLEAR_FOR_BOUNDED_RECONSTRUCTION`

Four packaged source bundles contain only three bounded internal aliases:
`.claude/skills`, `.codex/skills`, and `.github/skills`, each targeting
`../skills`. Current repository-task freezing accepts ordinary files only.
The migration may materialize these exact aliases as directory copies when it
records both tree manifests and proves identical paths, bytes, and executable
modes. Every other link form remains refused.

Qualification additionally requires digest-admitted execution proof that no
completed attempt observed link identity or wrote through an alias or its
target, plus zero hidden-grader references. The retained candidate JSONL
traces, receipt-bound log digests, exact status records, and hidden authority
inventories provide that proof for C01, C03, and C05. C02 independently records
ordinary-file source semantics. Missing or conflicting trace, receipt, status,
grader, or tree evidence refuses qualification.
