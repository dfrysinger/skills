# Frozen Development Workflow Comparison

**Status:** Proposed work order  
**Lane:** Systemic  
**Decision record:** `design/development-workflow-comparison-decisions.json`  
**Sealed evidence packet:** `design/development-workflow-comparison-evidence.json`  
**Evidence revision:** `workflow-comparison-evidence-r1`  
**Constraint challenge:** `design/development-workflow-comparison-constraint-challenge.md`  
**Sandcastle session feasibility:** `design/sandcastle-session-allocation-feasibility.md`  
**Reframe status:** `CLEAR`

## Objective

Extend the existing skill evaluator so neutral repository tasks can identify
frozen single-skill, multi-skill, and multi-agent development treatments and
attribute every observable model session honestly, then execute the approved
comparisons in parallel on isolated VMs without pooling incompatible results.

## User outcome

The user can see whether `development-loop`, Superpowers, Compound Engineering,
Sandcastle, and Matt Pocock's focused TDD and debugging skills produce more
correct, shippable work than an unchanged no-skill baseline, how long each
takes, and what candidate and evaluator credits each consumes.

Independent attempts should run concurrently when isolation makes their results
independent. Serial execution is required only for causal gates within one
attempt, treatment admission, and final evidence aggregation.

## Non-goals

- Do not rewrite `development-loop` as part of this comparison.
- Do not change frozen upstream treatment instructions to make them score
  better or fit unsupported languages.
- Do not create a cloud-provider abstraction, VM lifecycle manager, generic
  CI service, or public campaign dashboard.
- Do not publish private benchmark fixtures, hidden graders, candidate
  transcripts, credentials, customer data, or campaign-specific VM scripts.
- Do not convert Superpowers, Compound Engineering, or Matt Pocock's catalog
  into one synthetic merged workflow.
- Do not claim that Sandcastle's TypeScript/npm results generalize across
  languages.
- Do not make workflow-specific process adherence part of cross-workflow
  executable correctness.
- Do not infer zero credits, complete cost, successful human interaction, or
  successful child execution from missing telemetry.
- Do not run reportable comparison attempts until each treatment's exact
  package and runner contract passes admission canaries.
- Do not automatically push, merge, publish, close real issues, or mutate
  public repositories from a treatment.

## Lane

This is **systemic**. It adds treatment identity and entry-skill selection to
the evaluator's reusable result contract, adds one bounded external candidate
mode, extends candidate-session accounting, and changes history grouping.

It is not critical. The evaluator handles ephemeral benchmark repositories and
caller-supplied model credentials. It must preserve the existing secret
filtering and hidden-grader boundaries, but this change adds no production
authorization, customer data, durable schema migration, or fail-closed
enterprise control.

## Caller and authority classification

The trusted evaluator owns:

- validating frozen cases and optional treatment descriptors;
- selecting the legacy direct runner or one bounded external runner;
- mounting only declared packets;
- starting and stopping candidate processes;
- collecting evaluator-owned timing and declared session telemetry;
- exporting the final patch from a stopped candidate;
- running hidden offline graders;
- running external behavioral and quality judges; and
- rendering immutable results.

Treatment prompts and candidate model output are untrusted inputs. They may
edit only the candidate repository and declared treatment output directory.
They may not select hidden graders, rewrite evaluator identities, add
undeclared sessions to exact accounting, or authorize public side effects.

The private campaign coordinator is a trusted deterministic caller. It may
provision VMs, assign immutable attempt envelopes, transfer frozen public
treatments and private cases, retrieve artifacts, and tear resources down. It
does not decide correctness or rewrite attempt evidence.

## Approved treatments

| Treatment | Frozen source | Runner | Comparison population |
| --- | --- | --- | --- |
| No-skill baseline | Evaluator revision | Direct Copilot, no plugin | Every compatible neutral case |
| Current `development-loop` | Exact `dfrysinger/skills` revision selected at freeze | Direct Copilot plugin | Every compatible neutral case |
| Superpowers SDD | `obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797` | Direct Copilot plugin, approved-plan input | Cases with a pre-approved implementation plan and green isolated branch |
| Compound Engineering `lfg` | `EveryInc/compound-engineering-plugin@082c83e0537c803ac1d927daafc2e6eb6962dedf` | Direct Copilot full plugin | Local-only cases first; remote-backed shipping is a distinct later population |
| Sandcastle sequential reviewer | `@ai-hero/sandcastle@0.12.0`, git `e99f832f26dc9d245c019a9ddd19fa5dee792427` | External orchestrator | TypeScript/npm issue-based cases only |
| Matt Pocock TDD | `mattpocock/skills@959a8e9f1edc3adbe2f7e3054bb6fbefa6696260` | Direct Copilot plugin | Cases whose frozen evidence records an already approved public seam |
| Matt Pocock diagnosing bugs | Same revision | Direct Copilot plugin | Deterministic bug cases with a fast red-capable reproduction |

Spec Kit, Addy Osmani Agent Skills, BMad, Matt Pocock's complete composable
catalog, and experimental `implement-spec` are outside this work order. They
require a later exact unattended entry-point decision.

## Constraint provenance

| Constraint | Provenance | Binding evidence | Protected outcome | Revisit condition |
| --- | --- | --- | --- | --- |
| Run all approved treatments | User outcome | `user-2026-09-16-scope` | The comparison answers whether other complete and focused methods outperform the subject | User narrows scope or a treatment cannot be represented faithfully |
| Budget does not remove treatments | User resource decision | `user-2026-09-16-budget` | Complete comparison set | A provider quota or unavailable model makes execution impossible rather than merely expensive |
| Parallelize independent attempts on separate VMs | User execution strategy | `user-2026-09-16-parallelism` | Shorter wall time without shared mutation | Measured resource contention, release instability, API throttling, or attribution collision |
| Start at four concurrent attempts | Measured prior capacity | Evidence packet `measured_prior_capacity` | Avoid the prior six-job release-asset failure mode | A complete admission wave at four has no shared-service instability; then increase one bounded step |
| Preserve Claude as independent judge | User model policy | `user-prior-sol-fast-reviewers` | Cross-family judgment remains independent of Sol Fast candidates/GPT judges | User changes model policy or a named model becomes unavailable |
| Keep VM provisioning private | Repository architecture and publication boundary | Existing evaluator docs plus handoff | Generic public evaluator remains provider-neutral; private fixture details stay local | Two independent supported public callers need the same provider-neutral attempt-envelope API |
| Preserve unknown/partial telemetry | Existing measurement contract | `references/measurement.md` | No success-shaped cost claims | Upstream supplies a verified terminal billing source with complete child-session coverage |
| One mutating attempt per VM | Isolation requirement and prior Docker-global mutation evidence | Handoff `Parallel execution` | No cross-treatment worktree, Docker, Git, or telemetry contamination | A stronger sandbox is directly proven to isolate every relevant global state surface |
| Sandcastle remains TypeScript/npm-only in the first campaign | Frozen upstream commands | Upstream template requires `npm install`, `npm run typecheck`, and `npm run test` | No false cross-language equivalence | A separately named and reviewed language port is frozen as a distinct treatment |

No hard numeric timeout or VM count beyond the initial concurrency of four is a
design invariant. Candidate timeouts remain case-specific frozen inputs.

## Reframe gate

Return to this design before implementation continues if any of these occurs:

- faithful execution requires editing an upstream normative workflow rather
  than supplying a declared host/model/fixture adapter;
- the evaluator needs provider-specific VM lifecycle code;
- a new external orchestrator cannot route every top-level model launch through
  evaluator-owned session allocation;
- a deterministic human checkpoint cannot be represented without an evaluator
  model deciding the response;
- hidden graders or reference repairs would become reachable from a candidate;
- two treatments require different task semantics but are about to be pooled;
- a new runner type, network authority, public side effect, or persistent
  service is proposed; or
- the generic implementation exceeds the needs of the seven approved
  treatments.

**Current status: `CLEAR`.** After the independent challenge, the design reuses
the legacy direct runner unchanged, adds only one bounded external runner seam
required by Sandcastle, keeps cloud lifecycle outside the repository, and
preserves incompatible populations separately. The focused Sandcastle
feasibility check proved that its public provider interface can be wrapped with
evaluator-owned session IDs without changing workflow prompts or phase order.

## Reuse contract

### Reused unchanged

- `freeze_case`, `verify_case`, and digest-addressed case revisions.
- `snapshot_plugin`'s symlink refusal and read-only plugin mount.
- Docker candidate repository/evidence separation.
- Synthetic trusted Git base and post-stop patch export.
- Admission controls, fresh offline hidden graders, and reference controls.
- Behavioral judges and source-only quality reviews.
- `measurement.collect`, exact/observed credit semantics, timeline artifacts,
  and role separation.
- Immutable attempt artifacts and history reconstruction.

### Extended

1. Add treatment ID, source revision, adapter digest, entry skill, runner kind,
   intervention policy, and narrow compatibility identity to existing attempt
   artifacts and history grouping without replacing the legacy arm path.
2. Add one external-orchestrator runner contract whose only special power is to
   start the frozen treatment command and declare its child Copilot sessions.
3. Aggregate available implementation/review child sessions under candidate
   treatment cost while retaining individual subroles and coverage.
4. Add treatment identity and compatibility fields to history grouping so
   incompatible populations cannot collapse into one row.

### Newly required

A minimal treatment descriptor is required because the current run identity
cannot represent:

- a complete plugin whose entry skill differs from a case's historical target;
- an orchestrator that owns multiple Copilot sessions; and
- treatment compatibility such as Sandcastle's TypeScript/npm boundary.

No new service, daemon, database, package dependency, or cloud API is required.

## Minimal treatment descriptor

Legacy callers continue to use `--arm baseline` or
`--arm skill --plugin-dir PATH`. New direct comparison callers may add one
immutable `--treatment-file PATH`. The evaluator copies and fingerprints that JSON file into the run. Direct
treatments continue to use the existing complete plugin snapshot, whose full
directory identity is bound to treatment admission in addition to the selected
entry-skill identity.

External execution is not a general descriptor feature. The only admitted
external variant is
`sandcastle-sequential-reviewer-copilot-outer-isolated`, supplied through
`--sandcastle-treatment-file PATH --sandcastle-adapter-dir PATH`. Validation
requires the exact frozen source revision, package version, runner command,
model, adapter digest, session topology, and allowed subroles recorded by this
work order. Every other external identity or command is rejected. Another
external runner requires a new design and constraint challenge.

The treatment descriptor schema version 1 contains only:

- `id`: stable lowercase identifier;
- `source`: repository/package, immutable commit digest or exact semantic
  version, license, and
  retrieval date;
- `runner.kind`: `direct-copilot`;
- `compatibility`: only the approved predicates consumed by a treatment;
- `entry_skill`: optional exact skill required in the direct trajectory;
- `intervention_policy`: identifier for facts or choices frozen before the
  candidate starts; and
- `adapter`: exact patch/digest and explanation for every upstream change.

Paths must remain beneath the copied descriptor or adapter snapshot. Commands
are fixed argument arrays with no shell interpolation. Unknown fields and
unsupported schema versions fail before model execution.

Direct treatments use the current one-session repository runner. Neutral case
evidence contains every pre-approved plan, seam decision, or bounded completion
choice needed before the candidate starts. If a workflow still requires new
interpretation or human input, the pair is incompatible and no model starts.

## Sandcastle external orchestrator runner

The Sandcastle runner is one named, frozen deterministic program that starts
model sessions itself. It receives:

- the same candidate repository and evidence mounts;
- the read-only treatment snapshot;
- an empty writable treatment-output directory;
- the caller-supplied token in the candidate process with the existing secret
  filtering limitations;
- no corpus root, hidden grader, reference patch, host Copilot home, or Docker
  socket.

It writes one bounded `treatment-result.json`:

```json
{
  "schema_version": 1,
  "status": "completed",
  "output_file": "final-output.md",
  "sessions": [
    {
      "session_id": "uuid",
      "role": "candidate_implementer",
      "model": "gpt-5.6-sol-fast",
      "outcome": "completed"
    },
    {
      "session_id": "uuid",
      "role": "candidate_reviewer",
      "model": "gpt-5.6-sol-fast",
      "outcome": "completed"
    }
  ]
}
```

Before launch, the evaluator validates the exact treatment ID, upstream
revision, package version, adapter digest, fixed command, Sol Fast model, one
implementer session, at most one conditional reviewer session, and the two
allowed subroles. After launch it validates UUIDs, duplicates, output paths,
and the expected session set before collecting exact
session-local event files from the stopped execution environment. A declared
session with missing telemetry remains an invocation with unknown credits. An
undeclared event file is retained as contamination evidence and prevents
complete candidate accounting.

The runner result is candidate-controlled evidence, not exhaustive launch
authority. The evaluator preallocates every possible top-level Sandcastle
session UUID, and the frozen provider wrapper uses those IDs for the
implementer and conditional reviewer launches. Exact credits require the
expected launch set derived from retained Sandcastle results and terminal
collection for every expected evaluator-owned session. Any mismatch remains
partial; absence of another observed event file never upgrades coverage.

### Sandcastle adapter

The first adapter is frozen and disclosed separately from upstream:

- substitute both `claudeCode("claude-sonnet-4-6")` calls with
  `copilot("gpt-5.6-sol-fast")`;
- wrap each published Copilot provider only to append its evaluator-owned
  `--session-id`;
- replace the nested Docker provider with `noSandbox()` because the evaluator
  container and dedicated VM already provide the outer isolation boundary;
- retain the implement/review phases, shared execution environment, prompts,
  branch strategy, and one-issue semantics, with the outer loop fixed to one;
- provide a fixture-local tracker with exactly one task and deterministic close
  state;
- retain `npm install`, `npm run typecheck`, and `npm run test`; and
- emit the bounded treatment result from the existing Sandcastle return
  objects without adding another model call.

Changing the sandbox provider is an adapter difference, not an upstream claim.
The report must label this treatment
`sandcastle-sequential-reviewer-copilot-outer-isolated`.

## Compatibility and admission

Every case declares only compatibility metadata consumed by an approved
treatment:

- language;
- package/build system;
- whether a pre-approved plan exists;
- whether a public seam is already approved;
- whether a fast deterministic reproduction exists;
- whether remote side effects are allowed.

Treatment admission rejects an incompatible pair before starting a model.

Admission for every treatment proves:

1. treatment descriptor, plugin, adapter, and license identities match their
   frozen records;
2. paths, runner kind, commands, and intervention policy validate;
3. plugin discovery and exact entry-skill invocation work where required;
4. the pinned image contains the candidate CLI and required toolchain;
5. one non-reportable candidate can edit the intended repository;
6. output and patch capture work after the candidate is stopped;
7. deterministic graders remain hidden and pass their existing controls;
8. every observed primary and child candidate session has accounting role
   `candidate` and a distinct attributable subrole;
9. unknown/partial telemetry remains explicit under a forced missing-event
   canary;
10. timeout, no-output, missing-session, duplicate-session, and undeclared
    session paths fail visibly;
11. cleanup leaves no running candidate process or writable treatment
    workspace; and
12. no candidate-authored declaration can turn incomplete child-launch
    evidence into complete accounting.

Admission evidence is never counted as a reportable comparison attempt.

## Private campaign execution

Provider-specific campaign files live under the current session's private
artifact root, not in this repository.

The coordinator freezes:

- evaluator commit and harness digest;
- treatment descriptor, plugin, and adapter digests;
- case revisions and grader digests;
- candidate and judge models/effort;
- pinned VM image and Docker image identities;
- timeout and quality-review policy; and
- an immutable attempt ledger assigning one attempt ID to one
  case/treatment/VM slot.

Each VM:

1. verifies the frozen evaluator, treatment, case, and image identities;
2. runs exactly one mutating attempt at a time;
3. uploads the complete immutable run directory under its attempt ID;
4. reports terminal state without rewriting prior artifacts; and
5. is cleaned or destroyed before reassignment when host-global state changed.

The coordinator starts with four concurrent attempts. After one full admission
wave completes without release, API, telemetry, upload, or teardown
instability, it may increase concurrency in one measured step. It must reduce
concurrency after a correlated infrastructure failure. Replacement attempts
are allowed only when retained evidence proves candidate execution did not
start or the result is `INVALID`; scored `PASS` or `FAIL` attempts are never
replaced.

Matched arms may run simultaneously. Attempt order, VM identity, start time,
image identity, and replacement lineage remain report metadata so scheduling
bias can be inspected.

## Data flow

```text
public upstream revision
        |
        v
frozen treatment inputs ----- neutral frozen case
        |                             |
        +---------- admission --------+
                      |
                      v
             immutable attempt ledger
                      |
          +-----------+-----------+
          |           |           |
        VM A        VM B        VM C ...  (one writer each)
          |           |           |
          +---- immutable run artifacts
                      |
                      v
             deterministic collection
                      |
          +-----------+-------------+
          |           |             |
     correctness   quality       accounting/time
          |           |             |
          +------ separate report populations
```

## Failure model

| Failure | Required result |
| --- | --- |
| Treatment revision or adapter digest changes | Refuse the attempt before model execution |
| Plugin entry skill is not invoked | Scored treatment output failure, not baseline execution |
| Candidate or orchestrator times out | `FAIL` when candidate execution began; retain patch/output/partial telemetry |
| VM, image, token, setup, or transfer fails before candidate start | `INVALID`; replacement allowed with lineage |
| Child session is declared but telemetry is missing | Preserve invocation with unknown credits; accounting incomplete |
| Extra model session is observed but undeclared | Mark accounting contaminated and incomplete; retain evidence |
| Hidden grader or reference becomes candidate-readable | `INVALID`; quarantine the attempt and re-admit only after repair |
| Human response would require interpretation | `BLOCKED` compatibility result; do not synthesize a model response |
| Public push, merge, publish, or issue mutation is attempted | Deny through fixture boundary and record treatment failure/blocker |
| One VM contaminates another attempt | Quarantine both affected attempts; destroy resources; do not infer outcomes |
| Judge fails after candidate result | Preserve correctness and candidate accounting; evaluator accounting/quality incomplete |
| Collection or report build fails | Preserve immutable runs; rebuild locally without rerunning candidates |

## Invariants

1. A reportable attempt binds one case revision, treatment revision, adapter
   revision, evaluator revision, image identity, model configuration, and
   attempt ID.
2. The candidate never receives hidden graders, reference patches, prior run
   outputs, or another treatment's instructions.
3. Every model session that contributes to implementation or internal review
   is candidate treatment cost.
4. Behavioral and quality judges are evaluator cost and never rewrite
   executable correctness.
5. Missing telemetry remains unknown or partial.
6. Baseline receives no external treatment plugin or prompt instructions.
7. Workflow-specific adherence never becomes a neutral executable score.
8. A TypeScript-only treatment is aggregated only with compatible
   TypeScript/npm cases.
9. One VM has at most one active mutating attempt.
10. A scored attempt is immutable and cannot be replaced to improve results.
11. Every plan, seam decision, completion choice, or deterministic intervention
    policy needed by a treatment is frozen before the candidate's first token.
12. Provider-specific VM code and private fixtures do not enter the public
    repository.

## Acceptance criteria

1. Existing `--arm baseline` and `--arm skill` repository evaluations produce
   byte-compatible semantic results apart from new additive identity fields.
2. A frozen direct-plugin treatment can select an entry skill independent of
   the case's historical `target_skill`, and the run records structured proof
   that it was invoked.
3. Frozen case evidence can record pre-approved plans, seams, and completion
   choices, while a treatment requiring new interpretation is rejected before
   model execution.
4. An external treatment can declare two candidate child sessions, preserve
   their distinct roles, and aggregate both under candidate cost.
5. Missing, duplicate, malformed, wrong-model, and undeclared child sessions
   cannot produce complete accounting.
6. Incompatible treatment/case pairs fail before model execution.
7. History groups by exact treatment, adapter, case, image, model, timeout,
   judge, and quality configuration and never pools incompatible populations.
8. A report can show executable correctness, neutral source quality, elapsed
   time, candidate credits, evaluator credits, intervention policy, and
   compatibility separately.
9. Forced candidate timeout and forced judge failure retain all completed
   evidence and do not become zero-cost or successful runs.
10. Private campaign fixtures and transcripts remain outside the public
    repository, while all generic evaluator tests and documentation pass.

## Check contract

| Check | Protects | Setup/input | Pass signal | Failure proves |
| --- | --- | --- | --- | --- |
| Treatment descriptor unit tests | Strict additive identity contract | Valid and malformed direct descriptors | Valid descriptors normalize identically; unknown/escaping/malformed fields raise | Invalid treatment state could otherwise reach execution |
| Legacy-arm compatibility tests | Existing callers | Current baseline and skill synthetic cases | Same executable/behavioral semantics and plugin isolation | New abstraction regressed predecessor behavior |
| Direct-entry invocation test | Treatment-specific controller identity | Synthetic plugin with two skills | Only configured entry skill is required and observed | Case target and treatment entry are still incorrectly coupled |
| External-session schema tests | Child attribution | Synthetic orchestrator result variants | Valid implementer/reviewer accepted; malformed variants rejected | Multi-agent cost could be undercounted or misattributed |
| Child-coverage canary | Completeness honesty | Missing event, synthetic extra event, and candidate-only declaration variants | Accounting remains partial or contaminated unless evaluator-owned launch mediation proves exhaustiveness | Exact credits could be claimed despite hidden child work |
| Compatibility test | Population validity | Sandcastle treatment plus Python and TypeScript cases | Python rejected pre-model; TypeScript admitted | Unsupported tasks could enter misleading comparison rows |
| Timeout/failure tests | Evidence preservation | Synthetic timed-out direct and external runners | FAIL/INVALID classification and partial artifacts match stage | Failures could disappear or become success-shaped |
| History grouping tests | Non-pooling | Same case with different treatment/adapter/compatibility fields | Separate rows and explicit coverage | Incompatible methods could be averaged together |
| Report projection tests | Complete user-visible result | One complete and one partial synthetic run | Correctness, quality, elapsed time, candidate credits, evaluator credits, intervention policy, and compatibility render as separate fields; missing values render unknown, never zero | Required comparison dimensions could be absent or collapsed despite passing lower-level checks |
| Docker integration canary | Real execution boundary | Local synthetic image with fake Copilot event files | Patch, output, sessions, telemetry, stop, and grading artifacts validate | Unit-only behavior does not establish the container boundary |
| Public diff scope gate | Publication boundary | Before PR creation, apply the publication allowlist and secret scan to the union of `git diff --name-only 7864d17...HEAD`, `git diff --cached --name-only`, and `git ls-files --others --exclude-standard` | Every committed, staged, or untracked intended path is generic evaluator code, tests, docs, or approved design; no private corpus, hidden grader, transcript, credential, provider script, or VM artifact is present | Private campaign material could enter the public pull request |

No guard must exist before implementation. The schema and behavioral tests are
written alongside the implementation and reviewed with it.

Private campaign admission separately proves clean-VM transfer, four-way
isolation, unique artifact destinations, and teardown. Those are not public
evaluator acceptance tests.

## Migration and rollback

The CLI remains backward compatible:

- `--arm baseline` retains the built-in baseline path;
- `--arm skill --plugin-dir PATH` retains the existing single-skill path; and
- direct comparison callers may add `--treatment-file PATH`;
- the one external variant uses `--sandcastle-treatment-file PATH` and
  `--sandcastle-adapter-dir PATH`.

Existing case files, run directories, history, and reports remain readable.
New identity fields are additive and schema-versioned.

Rollback disables the new treatment execution options but retains the
treatment-aware history and report reader for all completed artifacts. No data
migration is required. Pre-change readers are unsupported for new-format runs
because they cannot recognize treatment population identity and could pool
incompatible attempts. The rollback procedure must preserve or restore the
treatment-aware reader before reading history. A rollback compatibility test
uses two runs differing only in treatment identity and proves the retained
reader keeps them separate after new execution is disabled.

## Implementation sequence

1. Add minimal treatment descriptor validation, copied identity, compatibility,
   entry-skill selection, and legacy additive defaults.
2. Preserve direct repository execution while applying additive identity and
   configured entry-skill checks.
3. Add external-command execution and child-session collection.
4. Extend accounting and history grouping.
5. Add documentation and generic synthetic tests.
6. Build private frozen descriptors, adapters, plugins, and neutral cases
   outside the repository.
7. Run local non-model and synthetic Docker canaries.
8. Run one real non-reportable admission canary per treatment.
9. Run the private four-VM collision/admission wave.
10. Freeze reportable campaign inputs and run compatible attempts in maximum
    proven-safe parallel waves.
11. Build the deterministic report and preserve cleanup receipts.

## Definition of Done: Frozen Development Workflow Comparison

- The systemic design and check contract pass independent constraint challenge
  and two-family design review.
- Existing evaluator behavior remains compatible and focused tests pass.
- Additive treatment identity, entry-skill selection, bounded external-session
  accounting, and history behavior satisfy every acceptance criterion that
  belongs in public code.
- Exact public revisions, licenses, adapters, models, images, cases, and
  attempt assignments are frozen before reportable execution.
- Every approved treatment has a retained non-reportable admission result.
- The safe concurrency ceiling is established by a four-VM collision wave and
  adjusted only from measured evidence.
- All compatible reportable attempts complete or retain an honest terminal
  `FAIL`, `INVALID`, `BLOCKED`, or incomplete state; no scored attempt is
  discarded.
- The final report keeps correctness, neutral quality, workflow adherence,
  candidate cost, evaluator cost, elapsed time, intervention policy, and
  compatibility populations separate.
- All temporary runners, VMs, credentials, branches, containers, and schedules
  created for the campaign are removed or have an explicit retained owner and
  expiry.
- Only generic evaluator code, tests, and documentation are eligible for a
  public pull request. Private fixtures, transcripts, and campaign
  infrastructure remain local.
