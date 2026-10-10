# Local Skill Evaluation UI

**Status:** Proposed work order
**Lane:** Critical
**Decision record:** `design/skill-evaluation-ui-decisions.json`
**Sealed evidence packet:** `design/skill-evaluation-ui-evidence.json`
**Evidence revision:** `skill-evaluation-ui-evidence-r1`
**Constraint challenge:** `design/skill-evaluation-ui-constraint-challenge.md`
**Reframe status:** `CLEAR`

## Objective

Add the local read-only dashboard foundation that lets every skill-evaluation
session show truthful completed history, active local sessions and attempts,
covered cost, and source authority without exposing hidden evaluation evidence
or becoming a second execution authority.

## User outcome

When a session begins or resumes skill-evaluation work, it registers with one
local dashboard service and opens its focused campaign route once. For the
foundation, the user can immediately answer:

- Which campaigns and sessions are active?
- Which tasks pass for each exact observed skill or skill-set revision?
- Why is each remaining task still red, and what evidence shows movement?
- Which local attempts are running, blocked, or complete?
- How much candidate, evaluator, retry, invalid, and unsuccessful work cost?
- What safe authority and source supports each visible claim?

Every displayed claim identifies its authority, freshness, and completeness.

The requested program also needs published/integrated/passing/ablated lineage,
experiment and cloud activity, ablation progress, and justified evidence
drill-down. Those outcomes remain recorded in Deferred Slices 3 through 6 and
are not completion criteria or implementation authority for this foundation.

## Non-goals

- Do not launch, retry, cancel, configure, edit, promote, publish, merge, or
  delete evaluation work from the UI.
- Do not replace `skill_eval.py`, immutable run directories,
  `evaluation_history.py`, distributed campaign receipts, or exact known-run
  observation.
- Do not add general GitHub Actions discovery, cloud scheduling, provider
  credentials, a workflow control plane, or remote access.
- Do not infer task success from process liveness, workflow color, candidate
  completion, instruction uptake, or a judge subset.
- Do not pool passes from different skill, plugin, case, treatment, model,
  harness, adapter, or evaluation revisions.
- Do not copy completed evaluator results into a mutable dashboard database.
- Do not expose hidden judge references, criteria, graders, private packets,
  or arbitrary corpus files.
- Do not make raw model transcripts the primary progress model.
- Do not add accounts, multi-user authorization, public hosting, mobile
  clients, notifications, or remote collaboration.
- Do not require existing corpora to migrate before their completed history
  can be viewed.

## Lane

This is **critical** because a new same-machine network service could otherwise
let candidate-controlled code read candidate-inaccessible judge material and
invalidate evaluations. It is also systemic because it introduces a reusable
campaign/session status contract, a shared local process, and new cross-run
views.

The design must fail closed: an unauthenticated request receives no evaluation
data, an unrecognized or malformed artifact is omitted with an explicit error,
and the projection has no operation that resolves arbitrary paths or reads
`cases/`, frozen judge packets, `judge-reference/`, criteria, graders, or
private package payloads.

Rollback disables dashboard registration and startup, stops the local service,
and leaves dashboard state inert. Existing evaluator commands, corpora, run
artifacts, reports, and history remain readable and unchanged.

## Caller and authority classification

Trusted deterministic owners:

- `skill_eval.py` owns frozen case validation, run identity, candidate
  execution, judgments, receipts, and completed outcomes.
- `evaluation_history.py` owns reconstruction of completed local history and
  exact versus observed accounting.
- `observe_campaign_runs.py` owns bounded read-only snapshots of exact known
  Actions run bindings.
- The dashboard projection owns only safe presentation of explicitly
  allowlisted fields from those authorities.
- A skill-evaluation session owns its session registration and may publish
  non-final campaign progress facts.

Untrusted actors:

- candidate/model-controlled code and tools;
- candidate-authored output, patches, and treatment output;
- live progress text supplied by a session; and
- workflow status that has not reconciled to evaluator receipts.

A trusted session may intentionally publish a hypothesis, assignment, or
failure-frontier observation. An untrusted actor must never add a completed
PASS, change immutable identity, read another campaign's protected data, or
address hidden evidence through the service.

## Constraint provenance

| Constraint | Provenance | Binding evidence | Protected outcome | Revisit condition |
| --- | --- | --- | --- | --- |
| Version 1 is read-only | User decision | `ui-authority-2026-10-10-001`: `"read only"` | UI cannot mutate evaluation state or acquire execution authority | User explicitly requests a separately designed control plane |
| One local service with focused routes | User decision | `ui-lifecycle-2026-10-10-001`: `"ok"` | Many sessions avoid duplicate scanners and port collisions | The shared service proves less reliable than isolated viewers |
| Campaign-first plus many active sessions | User decision | `ui-primary-scope-2026-10-10-001`: `"yes but there could be many active session"` | Focused work remains primary while concurrent work stays visible | User changes the primary workflow |
| Sessions contribute to durable campaigns | User decision | `ui-session-campaign-identity-2026-10-10-001`: `"sure"` | Parallel sessions aggregate without becoming separate histories | Evaluation ownership changes to session-isolated campaigns |
| Credits have a user-directed cents display transform | User decision | `ui-cost-units-2026-10-10-001`: `"credits are cents but agreed"` | User can read a familiar cost while evaluator-native accounting remains intact | User changes the transform or an authoritative billing price replaces it |
| Safe structured drill-down | User decision and frozen case contract | `ui-evidence-depth-2026-10-10-001`; `references/case-contract.md` | Useful diagnosis without hidden evidence leakage | Candidate and judge environments become physically isolated from the host UI |
| Add a canonical live contract | User decision and observed artifact gap | `ui-progress-contract-2026-10-10-001`; suite result is written at completion | Live status is explicit rather than inferred | Existing evaluator artifacts gain equivalent live records |
| Open once per session | User decision | `ui-auto-open-2026-10-10-001`: `"sure"` | Immediate visibility without repeated focus stealing | CLI gains a native non-disruptive dashboard surface |
| Land vertical slices independently | User decision | `ui-incremental-delivery-2026-10-10-001` | Every merge is usable, reviewable, and rollback-safe | A slice cannot remain compatible without an atomic migration |
| No hard refresh, stale, retention, or port number is architectural | No measured demand or policy | Pass-1 challenge | Avoid preserving implementation defaults as requirements | Measured UX or platform evidence establishes a bound |

## Reframe gate

Return to this work order before adding another component when:

- a slice requires the UI to mutate evaluator or campaign state beyond its
  own registration and progress records;
- the service needs arbitrary filesystem access or starts reading candidate
  and judge packet trees directly;
- completed results must be copied into a dashboard-owned database;
- correct joins require fuzzy path, name, timestamp, or process matching;
- cloud status requires broad workflow discovery instead of exact bindings;
- a new transport, framework, package manager, database, or background agent is
  proposed mainly to preserve the first implementation;
- candidate isolation cannot prevent access to the dashboard capability token;
- repeated fixes move leakage or stale-state failures between internal layers;
  or
- a proven Copilot-native canvas or artifact surface satisfies the complete
  caller outcome with fewer trusted components.

**Current status: `CLEAR`.** The proposal uses the existing Python evaluator,
standard-library HTTP and browser support, immutable evaluator artifacts,
write-once event envelopes, and session-owned atomic registration files. It
adds no database, frontend build system, cloud API client, or execution
control.

## Reuse contract

### Reused unchanged

- `load_corpus`, frozen case manifests, and case revision identities.
- Run, suite, treatment, plugin, skill, harness, timing, accounting, quality,
  and judgment artifacts.
- `evaluation_history.history()` and its population separation.
- `observe_campaign_runs.py` exact binding and refusal semantics.
- Distributed attempt IDs, matrices, stage receipts, and effective-result
  maps.
- Existing skill snapshots under retained run and suite directories.
- Python's standard library and the repository's existing unittest pattern.

### Extended

1. `skill_eval.py` gains dashboard subcommands that initialize campaign state,
   publish validated progress events, register sessions, ensure/open the
   service, and render a safe projection.
2. Run and suite execution publish non-final lifecycle events before the
   existing immutable final artifacts appear.
3. `skill-evaluation/SKILL.md` requires session registration at workflow start
   and refreshes it on resumption without repeatedly opening the browser.
4. Existing history projection gains reusable safe case and population helpers
   rather than a separate dashboard interpretation of correctness and cost.

### Newly required

- A local state root for service identity, capability token, registered
  campaigns, and session leases.
- A per-campaign write-once event directory and session-owned atomic status
  files.
- A static HTML/CSS/JavaScript application served entirely from the plugin.
- A safe projection module that has no arbitrary-path API.

No third-party package, database, cloud credential, or frontend build step is
required.

## Architecture

### Components

| Component | Responsibility | Trust |
| --- | --- | --- |
| `dashboard_state.py` | Validate IDs and events; create campaigns; atomically replace one session-owned status file; write event envelopes with exclusive creation | Trusted deterministic writer |
| `dashboard_projection.py` | Join registered campaigns to allowlisted immutable artifacts and safe live records; calculate completeness, cost, and foundation display states | Trusted read-only authority adapter |
| `dashboard_server.py` | Bind loopback, authenticate API requests, serve static assets and projection JSON, manage one service receipt | Trusted presentation process |
| `dashboard_cli.py` | `init`, `register`, `event`, `serve`, `ensure`, `open`, `status`, and `stop`; call root-authenticated control-only endpoints and pass a minted capability directly to the OS browser launcher | Trusted local operator adapter |
| Static web application | Render foundation overview, campaign, task, and run views | Untrusted display consumer of safe JSON |
| Skill instructions | Ensure registration and publish workflow progress at required phase boundaries | Trusted session procedure; event prose remains non-final |

These may remain modules under
`skills/skill-evaluation/scripts/`; separate packages or processes are not
required.

### Service lifecycle

`dashboard_cli.py ensure`:

1. opens the local state root with owner-only permissions;
2. takes an exclusive startup lock;
3. validates a live service receipt by service generation, process identity,
   loopback address, and authenticated health response;
4. starts `dashboard_server.py` only when no valid service exists;
5. writes the receipt atomically after the authenticated health route responds;
6. registers a Slice-1 corpus using a create-once campaign identity; and
7. returns a token-free focused URL plus an `opened: true|false` receipt.

Slice 2 extends `ensure` to register the exact session and refresh its lease.
It adopts the create-once Slice-1 campaign identity; it never rewrites or
migrates that identity.

The service persists until an authenticated owner-local `stop`, process exit,
or invalid health check. It has no idle timeout in the foundation because no
measured demand justifies one. Session leases may become stale, but stale
sessions remain visible as `stale` or `unknown`; they are never deleted or
relabeled completed by the service. Missing or moved corpus roots remain
registered as `unavailable`, and replacement paths are never guessed.

`stop` validates the owner-local service receipt and terminates only its exact
generation. A replacement service uses a new generation and capabilities. It
reuses the released prior port when available so an old browser receives
`401 generation_replaced` and an instruction to invoke `dashboard_cli.py open`;
it receives no data from the replacement. If another process owns that port,
the replacement chooses a new loopback port and the old browser reports the
service unavailable. Service replacement cannot add registered roots or change
result authority.

### Capability policy

Each service generation creates a cryptographically random 256-bit root secret
using the operating system CSPRNG. Each browser open creates a
cryptographically random bearer capability in the service process. A
capability:

- is scoped to one service generation and one campaign, or to the explicit
  global overview;
- is retained in service memory, passes transiently through
  `dashboard_cli.py` memory and the OS browser-launch call, and is then retained
  only in service and browser memory;
- is revoked on service replacement, stop, or explicit browser-session
  revocation;
- is sent to the browser only in the URL fragment;
- is moved by JavaScript into an `Authorization: Bearer` header;
- is removed from the address bar immediately with `history.replaceState`
  before the application loads data;
- never appears in CLI stdout, session output, query strings, cookies, server
  access logs, diagnostics, error bodies, generated HTML, or persisted browser
  state;
- is protected by `Referrer-Policy: no-referrer`, a restrictive
  `Content-Security-Policy`, and same-origin static assets; and
- is compared in constant time before any evaluation projection runs.

The root secret is stored in one owner-readable regular file with mode `0600`
beneath an owner-only `0700` state root and is never exposed to the browser.
It rotates on every service replacement and is removed on stop.

The static shell contains no evaluation data. Any API request with a missing,
wrong, stale-generation, or malformed token returns no campaign metadata.

`dashboard_cli.py open` sends the fragment-bearing URL directly to the browser
and returns only the token-free URL and open receipt. If browser opening fails,
the CLI prints `Run dashboard open again`; it never prints the capability.

`GET /_control/health` and `POST /_control/open` are the only root-secret HTTP
endpoints. They bind only on the same loopback listener, require the root secret
in an authorization header, never serve projection data, never log request
headers, and are called only by `dashboard_cli.py`. Browser static and
projection routes reject the root secret. `POST /_control/open` returns the
minted browser capability only to the authenticated CLI caller.

Capability possession is a deliberate owner grant. Repository-task candidates
remain unable to address host state. Prose candidates run as the same local
user but the evaluator gives them exactly `skill` and `view`; it supplies no
shell, browser, HTTP, or MCP tool. The bearer capability exists only in service
and browser memory, so the candidate has no operation that can exercise it.

The root secret is not a browser capability, is persisted only in its
owner-readable file, and is accepted only by the two control endpoints above.
`dashboard_cli.py open` is the only minting caller. A prose candidate that
attempts an absolute `view` outside its staged workdir fails the existing
tool-boundary audit. If that audit touches the dashboard state root, the
evaluator also rotates the service generation before accepting or judging the
candidate output, invalidating the exposed root secret. If a supported
candidate path gains shell, browser, HTTP, unaudited filesystem, or MCP access,
automatic dashboard exposure is blocked and this design returns to the reframe
gate.

### State layout

```text
~/.copilot/skill-evaluation-ui/
  root-secret                  # 256-bit, owner-readable, one generation
  service.json                 # immutable generation, pid, port, started_at
  startup.lock
  campaigns/
    <campaign-id>.json         # atomic registration, immutable root identity

CORPUS/.skill-evaluation-ui/
  campaign.json                # create-once identity and target skills
  sessions/
    <session-id>.json          # one writer, atomic replace
  events/
    <writer-id>/
      <event-id>.json          # write once
      conflicts/
        <event-id>-<digest>.json
```

`campaign.json` is immutable after exclusive creation. A registration file may
refresh display metadata but cannot change campaign ID, corpus root identity,
or target skill names.

The foundation does not copy skill source, cloud observations, candidate
output, or logs into dashboard state. The corpus state directory contains only
typed dashboard-safe records and never hidden criteria, grader inputs, private
packages, or arbitrary copied files.

### Identity contract

All IDs are opaque lowercase UUID or lowercase digest strings validated before
path construction.

| Aggregate | Minimum identity tuple |
| --- | --- |
| Campaign registration | `campaign_id`, corpus root identity, immutable target skill names |
| Session status | `campaign_id`, exact Copilot `session_id`, writer generation |
| Case row | `campaign_id`, `case_id`, immutable `case_revision` |
| Attempt row | case tuple plus run path or suite path and ordinal, treatment identity, model, harness identity |
| Population aggregate | case revision, arm, treatment identity, runner, adapter, entry skill, compatibility, skill identity, plugin identity, harness identity, model, effort, timeout, retry budget, image, quality configuration, evaluator models |
| Cost aggregate | exact population identity plus evaluator-owned session IDs and accounting coverage |
| Live assignment | campaign, session, writer generation, case ID, case revision, optional exact skill identity |
| Event | campaign, writer kind/ID/generation, unique event ID, typed entity tuple |

No join uses display names, timestamps, branch names, PIDs, process listings,
or path similarity. When an artifact lacks any required tuple member, that row
is `identity_incomplete` and excluded from aggregates rather than pooled.

### Live event contract

Slice 2 has two writer classes with non-overlapping ownership:

- a session owns only its session status plus assignment events;
- a local evaluator owns only attempt lifecycle and artifact-availability
  events; and
- cloud observation is deferred and has no foundation event type.

Every event envelope contains:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "event_type": "assignment_started",
  "campaign_id": "uuid",
  "writer": {
    "kind": "session",
    "id": "copilot-session-uuid",
    "generation": "opaque"
  },
  "emitted_at": "ISO-8601 writer clock",
  "recorded_at": "ISO-8601 local state writer clock",
  "entity": {
    "case_id": "case-id",
    "case_revision": "sha256"
  },
  "payload": {}
}
```

Allowed event types:

- `assignment_started`, `assignment_blocked`, `assignment_completed`;
- `attempt_planned`, `attempt_started`, `attempt_artifact_available`.

Session state is not an event stream. The session's one atomic status file has
`registered_at`, `heartbeat_at`, `state`, optional current case/revision, and
the last successful event ID. Only that session generation may replace it.

Each event type has a strict payload:

- assignment events: case ID/revision, optional exact skill identity, state,
  and a short non-final summary;
- `attempt_planned`: case ID/revision, model, effort, arm, treatment identity,
  and optional suite ownership;
- `attempt_started`: planned event ID plus exact run path after `attempt.json`
  exists; and
- `attempt_artifact_available`: exact run path plus the name and digest of one
  allowlisted immutable artifact.

The schema rejects unknown fields. Payloads cannot contain final correctness,
behavioral verdict, exact total cost, hidden evidence, instruction-uptake
verdicts, product-movement classification, or failure-frontier conclusions.
Those future observations require their own reviewed slice and cannot feed
foundation aggregates.

Each evaluator invocation uses a unique writer ID stored in `attempt.json`;
parallel suite threads and separate run processes therefore never share a
writer. Session event emission is serialized by one per-session-generation
exclusive lock around status validation, event creation, and status replace.

An event is idempotent by `event_id`. Same ID and identical bytes succeeds.
Same ID and different bytes is rejected, both byte identities are retained in
the writer's `conflicts/` directory, and the writer stream becomes
`conflicted`. Event completeness does not depend on sequence numbers.
Cross-writer display order may use `recorded_at`; no semantic decision depends
on clock order. Immutable artifacts supersede live state.

### Authority and reconciliation

For every field the projection uses the first available source in this order:

1. immutable evaluator result or receipt;
2. validated live event or session-owned status;
3. explicit `unknown` or `unavailable`.

Live state cannot upgrade correctness. A workflow conclusion cannot upgrade
product status. A retry cannot replace a first outcome. A revision's corpus
score includes only attempts with the same exact revision and evaluation
contract.

The accounting authority remains evaluator-native AI credits and premium
requests. The UI always shows raw exact or observed credits first. It may also
show a clearly labeled user-convention transform of `1 credit = 1 cent`; that
derived value is not evaluator billing evidence or a currency price.
Premium-request-only usage remains a separate unconverted unit and cannot
produce a credit or currency total. History parity compares raw credits and
coverage before applying the display transform.

Every material projected value includes:

```json
{
  "value": "...",
  "authority": "immutable_artifact | live_event | unavailable",
  "source": "safe corpus-relative artifact identifier",
  "observed_at": "ISO-8601 or null",
  "complete": true
}
```

The source is an opaque safe identifier produced by the projection, never a
caller-supplied path.

### Safe artifact projection

The server calls typed readers. It never accepts a filesystem path from an HTTP
request.

Allowed completed sources:

- `corpus.json`;
- frozen current pointers and case manifests, excluding packet content;
- `runs/*/*/{attempt,run-context,execution-result,repository-result,skill-identity,plugin-identity,treatment-identity,compatibility,accounting,timing}.json`;
- judgment verdict records with only verdict, confidence, and generalized
  defect fields;
- quality assessments with only status, judgment, severity counts, and cited
  candidate file locations;
- `suite-runs/*/suite-result.json`;
- dashboard campaign, session, and Slice-2 event schemas under
  `.skill-evaluation-ui/`.

Denied by construction:

- authoring `cases/` contents;
- candidate evidence packet content;
- `judge-reference/`, `criteria.md`, judge prompts, hidden graders, reference
  patches, private package archives, credentials, and arbitrary raw files;
- any symlink, special file, path escape, unexpected schema, or unknown
  artifact version.

Quality candidate-file citations are normalized relative paths validated
against the retained candidate patch inventory. They are labels only; no HTTP
route opens their paths.

Candidate output and raw logs are not in the foundation scope. A future slice
must define named bounded readers and a separate adversarial contract before
serving either.

## UI information architecture

### Global overview

- registered campaigns and exact target skills;
- active, stale, blocked, and completed sessions;
- active local attempt counts by task and known skill identity;
- raw exact or observed AI credits, the separately labeled user-convention
  cents transform when credits are known, premium requests, and coverage
  badges;
- attention queue for identity conflicts, stale sessions, incomplete
  accounting, judge disagreement, blocked cases, and unavailable roots;
- freshness and source indicators; and
- links to focused campaign routes.

### Campaign overview

- corpus scorecards grouped by exact observed skill identity, with no
  foundation claim that one identity is current or integrated;
- separate first-attempt, eventual, retry-assisted, executable, behavioral,
  quality, and qualification states;
- task rows showing maintained/development/transfer cohort, latest result,
  current owner, and running attempts;
- active work table grouped by session, task, treatment, model, platform, and
  location;
- spend cards for candidate, evaluation, retry, invalid, unsuccessful, and
  total work, always with coverage; and
- timeline of immutable outcomes and non-final progress events.

### Task detail

- exact case and revision;
- matched comparison populations;
- every retained attempt, including failures and retries;
- deterministic, behavioral, quality, and post-environment results separated;
- source artifact links limited to safe projection; and
- exact skill identity tested against the task.

Skill lineage, experiment qualification, cloud/distributed activity, ablation,
and raw evidence drill-down remain requested program outcomes but are not
approved by this foundation work order.

## Failure model

| Failure | Required behavior |
| --- | --- |
| Service dies | `ensure` replaces it from durable registrations; no evaluator state changes |
| Port collision | Bind an available loopback port and publish it only after authenticated health succeeds |
| Stale receipt or PID reuse | Generation and authenticated health mismatch invalidate the receipt |
| Concurrent startup | One startup lock wins; losers re-read the validated receipt |
| Partial event write | Exclusive temporary file plus fsync and rename, or exclusive final creation; malformed files are rejected |
| Duplicate event | Same `event_id` and bytes is idempotent; different bytes is a visible conflict |
| Session disappears | Show stale/unknown after the configurable lease policy; never mark completed without an event or receipt |
| Artifact is still being written | Refuse or retry the typed read; never parse partial JSON as a result |
| Unknown schema | Show unsupported artifact and exclude it from aggregates |
| Accounting incomplete | Show observed subtotal and incomplete coverage; no exact currency total |
| Run fails after candidate launch | Preserve first candidate outcome and downstream failure stage |
| Capability missing | API returns no data; static shell remains empty |
| Candidate views dashboard state outside its workdir | Fail the tool-boundary audit, rotate the service generation, and do not accept or judge the output |
| Candidate gains shell, browser, HTTP, unaudited filesystem, or MCP access | Block automatic exposure and return to the reframe gate |
| Registered corpus moved or removed | Mark unavailable; do not follow replacement symlinks or guess a new location |
| Browser open fails | Return a token-free URL and print the `dashboard open` retry command; evaluation work continues |

## Delivery slices

The current review approves two independently useful foundation pull requests.
Each starts from the merged predecessor, passes its own product proof and dual
review, is committed, pushed, and merged before the next begins. No slice may
leave main dependent on unmerged follow-up work.

### Slice 1: Completed corpus dashboard

Deliver:

- token-gated loopback service and static shell;
- safe typed projection of corpus cases, completed local runs, suite results,
  exact skill identities, outcomes, timing, and accounting;
- global registration of multiple corpora;
- campaign and task scorecards;
- raw exact/observed credit display plus the labeled user-convention cents
  transform; and
- manual `ensure`, `open`, `status`, and `stop` commands.

User value: open a corpus and understand completed task status, matched
populations, exact skill revision, outcomes, and spend.

Explicitly unavailable: live sessions, live attempts, cloud status, rich
lineage, experiments, and ablation.

### Slice 2: Live local sessions and attempts

Deliver:

- campaign identity, session registration, heartbeat, and write-once events;
- local evaluator lifecycle events;
- active/stale/blocked session and attempt views;
- campaign-first session routes;
- one-time automatic opening from `skill-evaluation/SKILL.md`; and
- explicit reconciliation where final artifacts supersede live state.

User value: see what every local session is doing now and against which task
and skill revision.

## Deferred requested slices

The following outcomes remain in the user-approved program, but this work order
does not authorize their implementation. After Slice 2 merges, each returns to
`design-doc` with current evidence, a focused constraint challenge, and its own
observable Definition of Done.

### Deferred Slice 3: Skill lineage and task-progress evidence

Deliver:

- safe skill-set snapshots and lineage roles;
- published/original/integrated/experimental/passing/released relationships;
- exact diffs and size metrics;
- earliest failure frontier, failure classification, instruction uptake, and
  product movement;
- task detail and attention queue.

User value: understand what changed, whether behavior moved, and what remains
blocked without reading raw directories.

Entry condition: exact safe revision-manifest and diff semantics are designed
without copying arbitrary plugin trees.

### Deferred Slice 4: Experiments and cloud/distributed activity

Deliver:

- treatment hypotheses, controls, repetitions, and selection rules;
- exact known Actions observation references;
- distributed attempt/stage/effective-result projection;
- active local/cloud counts by task, skill revision, treatment, model, and
  platform;
- complete first outcomes and recovery lineage.

User value: monitor parallel experiments and distinguish transport activity
from evaluator results.

Entry condition: writer ownership and exact known cloud/distributed binding
contracts are independently reviewed.

### Deferred Slice 5: Ablation workspace

Deliver:

- delta and full neutral/lean/full campaign models;
- discriminating-case and corpus progress;
- rule removal/retention/restoration evidence;
- original versus passing versus current/final ablated comparisons;
- final qualified size reduction and retry dependence.

User value: track whether the skill is genuinely getting smaller without
losing maintained wins.

Entry condition: ablation qualification authority, maintained-win joins, and
size comparison semantics are specified independently of UI shape.

### Deferred Slice 6: Safe evidence drill-down and release qualification

Deliver:

- a separately reviewed decision on whether bounded candidate output or
  non-hidden log readers are necessary;
- keyboard and screen-reader navigation;
- responsive dense layouts and large-corpus virtualization or pagination when
  measured demand requires it;
- full hidden-boundary adversarial suite;
- installed-plugin end-to-end proof across two local sessions, one completed
  corpus, one active local run, one exact cloud observation, one treatment
  experiment, and one ablation campaign; and
- final release documentation.

User value: inspect source evidence and operate the complete dashboard with
confidence.

Entry condition: a focused work order proves any raw reader is necessary and
cannot reconstruct hidden or cross-attempt evidence.

## Acceptance criteria

1. Starting the dashboard for a corpus returns an authenticated focused URL and
   exposes no evaluation JSON without the capability.
2. A completed corpus renders every indexed task and preserves exact case,
   skill, treatment, model, harness, and attempt identities.
3. PASS, FAIL, UNANSWERABLE, INVALID, BLOCKED, and quality states remain
   distinct.
4. Raw exact or observed AI credits and premium requests preserve evaluator
   semantics; the user-convention cents transform appears only for known
   credits, is labeled as derived, and partial observations remain visibly
   incomplete rather than zero.
5. Concurrent session and evaluator writers cannot overwrite one another or
   produce false gaps; duplicate event IDs are idempotent or visibly
   conflicted.
6. Live progress cannot upgrade completed correctness and final artifacts
    supersede live state.
7. Multiple active sessions appear under one campaign with exact current task,
    skill revision, treatment, and location when those facts are known.
8. Every aggregate uses its complete minimum identity tuple; incomplete
    identities remain unavailable instead of pooling.
9. Every material claim identifies immutable-artifact, live-event, or
    unavailable authority and a safe source identifier.
10. Older corpora without dashboard state show completed history and mark live
    sections unavailable.
11. No authenticated or unauthenticated route can read hidden judge references,
    criteria, graders, private packages, credentials, arbitrary paths, symlinks,
    or unsupported artifacts.
12. The first invocation opens once; later invocation or resumption refreshes
    registration without repeated focus stealing.
13. Root-secret and capability generation, scope, memory/file placement,
    rotation, revocation, stdout/log/referrer behavior, fragment removal, and
    stale-generation behavior match the capability policy.
14. Service replacement, stale sessions, moved roots, and old browsers produce
    explicit stale, unavailable, or generation-replaced states without changing
    evaluator results.
15. A prose candidate has no tool that can exercise a bearer capability;
    an out-of-workdir dashboard-state read fails the attempt and rotates the
    service generation before candidate output is accepted or judged.
16. Each committed foundation slice is independently usable, validated, reviewed,
    committed, pushed, and merged before the next slice starts.

## Check contract

| Check | Protects | Setup/input | Pass signal | Failure proves |
| --- | --- | --- | --- | --- |
| Safe projection unit suite | Criteria 2-10 | Synthetic corpus with valid, malformed, conflicting, partial, legacy, identity-incomplete, and hidden fixtures | Exact JSON projection matches authority and unavailable states | Projection can misstate results, pool identities, or leak denied data |
| Hidden-path refusal guard | Criteria 1 and 11 | Attempt every denied path class, traversal, symlink, special file, and unknown schema through all typed readers and HTTP routes | Every request is refused and no hidden marker reaches output | The critical evidence boundary fails open |
| Capability boundary integration | Criteria 1, 11, and 13 | Start, open, replace, and stop service; call control endpoints with missing, wrong, and correct root secrets; call browser routes with missing, wrong, prior-generation, root-secret, and correct browser capabilities; inspect CLI output, process arguments, session logs, server logs, referrers, and browser history | Only control endpoints accept the root secret and never return projection data; only a current scoped browser capability receives safe JSON; the root secret is persisted only in its owner file; browser capabilities are transient in CLI launch memory, retained only in service/browser memory, and stripped from browser history | Loopback callers can read data or capability lifecycle leaks authority |
| History parity test | Criteria 2-4 and 10 | Compare raw dashboard credits, premium requests, populations, outcomes, and coverage with `evaluation_history.history()`; include premium-only and partial fixtures before applying the optional display transform | Raw outcomes, populations, units, and coverage agree | UI has become a second correctness/accounting interpreter or invented a currency total |
| Concurrent writer test | Criteria 5 | Many processes write distinct session files and event envelopes, including same-session concurrent emits, evaluator threads, duplicate IDs, and interrupted writes | No lost events or false conflicts; differing duplicate IDs conflict deterministically | Shared state is unsafe under the required session concurrency |
| Reconciliation test | Criteria 3 and 5-9 | Publish local live events, retries, conflicts, and then immutable results | Authority order, complete identity tuples, and first outcomes remain intact | Live metadata can rewrite evaluator truth |
| Service lifecycle test | Criteria 13-14 | Concurrent ensure, stop, crash replacement on the released port, occupied-port fallback, PID reuse, stale sessions, moved roots, old browser token | Exactly one current service; an old token on a reused port receives `generation_replaced`; occupied-port fallback and stale/unavailable states are explicit | Shared lifecycle can broaden roots, retain authority, or fabricate state |
| Candidate tool-boundary integration | Criteria 1, 11, 13, and 15 | Launch a prose candidate with the exact `skill,view` tool contract; attempt dashboard API access and an absolute view of the root secret; inspect tool audit, service generation, and judgment admission | No network operation exists; the out-of-boundary view fails the attempt; the generation rotates before output admission; no dashboard JSON reaches the candidate | The new service creates candidate authority beyond the evaluator's existing boundary |
| Browser behavior test | Criteria 7, 10, 12, and 14 | First start, repeat invocation, resume, replacement, fragment stripping, and browser-open failure | Open occurs once; later calls return only token-free URLs or retry commands; legacy and replaced states are explicit | Session entry leaks capability material, is disruptive, or reports unavailable state dishonestly |
| Slice-1 installed-plugin proof | Slice-1 criteria only | Installed plugin, completed corpus, legacy corpus, manual ensure/open/status/stop, service replacement, token refusal | Completed-history journey works independently before any session/event schema exists | Slice 1 is not independently useful or relies on Slice 2 |
| Slice-2 installed-plugin proof | All foundation criteria | Installed plugin after Slice 1, two sessions, active isolated run, active prose run with the exact `skill,view` tool boundary, boundary-violation rotation, timeout recovery, and completed artifacts | Live-local journey works and final artifacts supersede live state without exposing protected data or expanding candidate authority | Slice 2 does not safely add live status to the merged Slice-1 foundation |
| Dual review per slice | Criterion 16 | Exact slice diff, tests, live proof, work order, and prior findings | Both model families complete with no must-fix finding | Slice is not independently ready to merge |

The **hidden-path refusal guard** is written before the server implementation
in Slice 1 because it constrains the critical architecture. All other checks
are written with the slice that introduces the behavior.

## Migration and rollback

There is no corpus rewrite. Dashboard state is additive under
`.skill-evaluation-ui/`. Existing commands ignore it.

Schema changes create a new versioned reader and retain old readers while old
state exists. Unknown future versions are unavailable, not guessed.

Per-slice rollback:

1. stop dashboard auto-registration and service startup;
2. stop the service using its authenticated local receipt;
3. revert the slice while retaining readers needed for any state already
   emitted by merged predecessors;
4. leave immutable evaluator artifacts untouched; and
5. mark dashboard-only state unsupported rather than deleting it.

The full rollback is complete when ordinary evaluator runs, suites, reports,
history, distributed tooling, and skill invocation work without the service.

## Delivery and landing policy

- Use one branch and pull request per delivery slice.
- Base each slice on the merged predecessor.
- Keep commits scoped to one complete vertical behavior.
- Include the required co-author trailer.
- Run targeted checks, installed-plugin proof, constraint challenge when a
  reframe trigger fires, and dual review before merge.
- Merge only when the slice's user value works end to end and no must-fix
  finding remains.
- Do not keep an unmerged stack of dependent slices.

## Current baton

- **Phase:** Foundation Slice 1 landing.
- **Workspace:** isolated worktree for
  `dfrysinger/skill-eval-ui-slice1`, based on merged design commit
  `fc8cb1d268d3b80320f0fa9dc00a48dd80158207`.
- **Decision record:** complete; no unresolved user event.
- **Pass-1 challenge:** `NARROW`, incorporated in this proposal.
- **Pass-2 challenge:** `NARROW`; ten required edits are incorporated in the
  current revision.
- **Challenge closure:** focused trust-boundary refresh is `CONTINUE`,
  `CLEAR`; the candidate-shell premise was disproved against the exact runner,
  and capability rotation on audited boundary violations is specified.
- **Dual design review:** complete; both model families applied the design
  scope lens and closed every material finding.
- **Slice 1 evidence:** 315 deterministic tests pass; installed lifecycle,
  completed-history, and browser receipts pass against candidate fingerprint
  `sha256:d3e3b7d78753f52b854663451d92712804df4c20b15a56b7bdde44cd6c1bb421`.
  Light, dark, mobile, overview, missing-capability, and legacy-unknown states
  were inspected. Round-2 dual review closed all findings with no remaining
  must-fix or follow-up.
- **Next action:** commit, push, review the pull request checks, and merge
  Slice 1 before creating the Slice 2 worktree from merged `main`.
- **Open revisit condition:** none.
- **Observed mechanism correction:** live proof showed that a new-port
  replacement cannot answer an old-port browser with `generation_replaced`.
  Slice 1 therefore reuses the released prior port when available and reports
  unavailable when another process owns it.

## Definition of Done: Skill Evaluation UI Foundation

- The reviewed work order and exact check contract are merged.
- Foundation Slices 1 and 2 are independently merged after their own
  validation, live browser proof, and dual review.
- Invoking skill-evaluation starts or reuses the loopback service, registers the
  current session and campaign, and opens the focused route once.
- The foundation UI truthfully shows completed and active local task progress,
  exact attempt and skill identities, covered cost, and source authority.
- The installed-plugin foundation scenario proves two concurrent sessions,
  completed and active local work, the exact prose candidate tool boundary, a
  legacy corpus, and service replacement.
- Hidden evidence remains unreachable through every route and reader under the
  adversarial guard.
- Existing evaluator behavior and historical corpora remain compatible.
- Deferred requested Slices 3 through 6 each have a recorded entry condition
  and no implementation authorization from this foundation design. They remain
  the next requested program work after this run stops.
- Every live schedule created for the unattended run is stopped and verified
  absent.
