# Historical case capture

Use this procedure to turn an agent conversation and its related artifacts into
a reproducible evaluation case. Capture first, select evidence second. Do not
construct the candidate packet while searching, because later corrections can
leak into an earlier blind phase.

## Source-bound native context setup

The existing `_run_native_context_calibration` coordinator accepts an owner-only
historical fixture with `schema_version: 2` and
`provenance: "source-bound-historical"`. This selects the
`native-historical-context` helper profile. It prepares context only and refuses
`model_send=True` and the helper's `candidate` operation. A successful setup
receipt does not admit a historical behavioral run.

The fixture contains:

- `records`: the public semantic header and root messages, requests and results.
  The header's `createdAt` is the original creation timestamp.
- `source_mapping`: ordered source event groups with `event_id`, `native_type`
  and `record_indices`. Indices include the header at zero; each conversation
  record appears exactly once. One assistant group may contain its message and
  several tool requests.
- `summary` and `summary_timestamp`: separate native summary content and time,
  never an invented user or assistant turn.
- `skill_events`: recorded `source_event`, `actor_scope`, `position` and
  `body_sha256`. Six root events precede the summary. One root event has
  `position: "post-compaction"` and `records_before` equal to the last record
  index of its preceding source group. Child events remain provenance only.
  Optional `relocated_path` changes only the staged path, not the loaded body.
- `snapshot`: `schemas`, explicit `rows`, and four `queries`. Table names are
  `todos`, `todo_deps` and `live_proof_receipts`. Every row supplies every column,
  including NULLs and timestamps. Each query supplies `query`, `expected_text`
  and `expected_rows`; the text binds the source SQL tool's
  `textResultForLlm`, not a newly rendered answer.
- `restoration`: `source_session_id`, excluded `cutoff_event_id` and
  `skill_context: "recorded-target-context"`.
- `required_tools`: `skill`, `view`, `sql`, `manage_schedule`, `bash`,
  `apply_patch`, `rg`, `task` and `task_complete`.
- `personal_instructions`, `candidate_permissions` and nonempty `limitations`.
  Permissions use the existing literal write-path and shell-command contract.

The public importer exits before the native stager writes any events. The
stager compares the generated root groups, maps source calls to native call
IDs, preserves failed results and their error messages, and inserts only
source-bound summary and skill events. It refuses unknown layouts or ambiguous
insertion boundaries.

The connected helper checks empty state and actual table schemas, creates the
source receipt table, and installs one transaction through the existing SQL
tool. It selects autopilot mode without creating a goal or schedules. Warm and
cold checks compare explicit rows and insertion order, all four source queries,
summary and root event identity, loaded skill bodies before and after definition
reload, catalog visibility, tool metadata and initialized context readers.
The existing zero-send preflight retains normal permission checks.

Retain the input hashes, importer receipt, staged journal, source-to-native
mapping, helper calls, first error and shutdown results outside candidate
evidence. Cleanup stops only the owned producer and leaves the isolated
historical namespace available for inspection. Memory SQL checks and mocked
SDK tests establish source contracts only. Native schema and reader
compatibility, required-operation permissions, source counts and behavioral
environment fit still need their own acceptance evidence. Do not infer goals,
timers, unknown effort, other tables or live filesystem availability.

## 1. Define the event boundary

Write the question the case tests, the actor whose session is authoritative,
the approximate time window, and the observable correction or accepted outcome
that will judge the candidate.

Use the playbook's [replay starting-point procedure](evaluation-playbook.md#choose-the-replay-starting-point)
to distinguish prevention from unaided or guided recovery. Record the causal
decision, supported trigger, instruction exposure, matching state and observation
horizon in the existing trace ledger and decision record before freezing.

Identify:

- the last event visible to the candidate;
- the first event reserved for the hidden judge;
- any later event that changes, supersedes, or confirms the correction; and
- the repositories, worktrees, pull requests, commits, files, commands, or
  generated outputs connected to those events.

Do not choose a session from display name alone. Resolve its stable session ID,
repository, branch, timestamps, and surrounding user turns.

Apply the sensitive-content boundary before writing anything under `capture/`.
Never retain or freeze credentials, tokens, authentication headers, protected
environment values, private attachments, or sensitive tool arguments and
results. Omit the protected field or span, label the omission, and record the
resulting evidence limitation. A redacted record is not an exact quotation and
cannot serve as exact authority. Do not move an unredacted copy elsewhere.

## 2. Preserve the discovery queries

Create `cases/<case-id>/capture/queries/`. Save each query or command exactly as
run when it contains no protected value. Otherwise preserve the parameterized
form with a labeled omission, never the sensitive value. Record:

- the source store or repository;
- execution timestamp;
- returned row or item count;
- stable session, pull-request, issue, or commit identifiers; and
- the output file containing the result.

When a structured session store is available, find candidate sessions through
its session index with a bounded time range. After selecting one session ID,
query its turns, checkpoints, references, changed-file records, attachments,
tool requests, tool completions, and usage metadata by that exact ID. Keep the
time or session filter and a finite result limit on every query.

If only a transcript export is available, preserve the unmodified export and
record the command, API request, or UI export operation that produced it.
Never reconstruct inaccessible or content-excluded records through another
tool.

## 3. Export exact conversation evidence

Under `capture/transcript/`, preserve:

- session metadata;
- exact user and assistant turns with turn indexes and timestamps;
- checkpoints or compaction summaries, labeled as summaries;
- tool invocation and completion events needed to understand the correction;
  and
- references linking the session to commits, pull requests, issues, or files.

Keep screened raw exports byte-for-byte. Derived timelines and summaries go in
separate files and cite the exact session ID and event or turn IDs they summarize.
Formatting damage, truncation, missing events, or uncertain speaker identity is
recorded as missing evidence, not repaired through paraphrase.

## 4. Trace and capture artifacts

Build `capture/artifact-ledger.json`. Give every material artifact a stable
ledger ID and record:

- repository and remote identity;
- branch, worktree, pull request, issue, commit, or run identifier;
- file path or artifact name;
- how the transcript refers to it;
- whether it was created, edited, executed, reviewed, accepted, rejected, or
  merely mentioned;
- the exact source revision;
- capture command or query receipt;
- SHA-256 of the captured bytes; and
- whether the artifact is candidate-visible, judge-only, or contextual.

Start from session references and changed-file records, then inspect the
relevant tool events to find commands, generated outputs, test results, and
commit lineage. Capture committed files from the named revision, not from a
later worktree. Capture an uncommitted file only when it is itself necessary
evidence, and label its worktree state and capture time explicitly.

For skill repositories, use the playbook's
[Git restoration recipe](evaluation-playbook.md#restore-historical-skills-from-git)
to recover the cutoff-specific collection and reconcile recorded skill loads.

Preserve the smallest artifact slice that proves the behavior. Include complete
files or command outputs when omitted context could change their meaning.
Exclude credentials, tokens, unrelated private data, caches, dependencies, and
large generated trees that do not bear on the claim.

## 5. Reconstruct the correction sequence

Create `capture/trace-ledger.md` with one row per material event:

| Event | Exact source | What changed | Connected artifacts | Visibility |
| --- | --- | --- | --- | --- |

The sequence must show:

1. the proposal or behavior before correction;
2. the evidence available at the candidate cutoff;
3. the exact correction or accepted outcome;
4. the resulting design, implementation, or decision when one exists; and
5. later confirmation or supersession that affects the expected behavior.

Implementation volume, a merged commit, successful tests, or an author's
summary proves only what happened. It does not replace the user decision or
other authority that establishes what should have happened.

## 6. Select candidate and judge packets

Copy exact source files from `capture/` into the phase evidence directories and
`judge-reference/`.

Candidate phases receive only information available by their named cutoff. A
later phase may receive additional proposal or implementation evidence while
retaining the earlier phase's conversational conclusions through session
resume. The hidden packet receives the correction, accepted outcome, authority
mapping, and any later artifacts needed to judge preservation or
overcorrection.

Do not put a full transcript into an early phase when it contains later turns.
Split it into exact bounded exports. Do not replace exact turns with a summary
merely to hide later content.

For every hidden criterion, record the exact ledger ID, session event or turn
ID, and quoted or byte-addressed source that establishes it. For every selected
artifact, retain its ledger entry and digest in the same packet or in a
packet-visible provenance file.

## 7. Audit the candidate text packet

Render the exact task the candidate will receive and create
`capture/candidate-text-audit.md`. Keep three kinds of text visibly separate:

| Layer | Allowed content | Required authority |
| --- | --- | --- |
| Original request | Verbatim user turns or clearly bounded exact excerpts | Session ID, turn or event ID, timestamp |
| Restored context | Context the original agent had but the reproduction lacks | Source event or artifact available by the candidate cutoff |
| Evaluation operation | Offline limitations, workspace locations, commands, and evidence delivery | Harness or package contract |

Preserve the user's wording, sequence, ambiguity, and mistakes. When one turn
contains an unrelated request, retain the complete turn when safe, or mark the
exact excerpt boundary and omission instead of presenting the excerpt as the
complete request. A summary may introduce the evidence but cannot replace it.

For every sentence not copied from the original request, record:

- its layer;
- why the candidate needs it;
- the exact source proving the original agent had it, or the harness contract
  that requires it; and
- whether it changes, narrows, expands, or merely explains the requested
  outcome.

Reject an addition that names a state, mechanism, implementation, edge case, or
success condition solely because the hidden answer uses it. Also reject an
addition that narrows a broad user-visible outcome to the subset exercised by a
convenient fixture. A focused fixture may remain candidate-visible, but label
it as one proof path rather than the complete acceptance boundary unless it
actually reproduces the whole claim.

After staging or freezing, read the rendered task and every path it names
through the same candidate filesystem and permission boundary. Missing,
mislocated, denied, or differently worded evidence fails the audit. Compare the
staged bytes with the text-audit ledger before allowing a run.

## 8. Audit completeness and leakage

Before freezing, verify:

- the stable session and artifact identifiers resolve to the captured sources;
- `capture/candidate-text-audit.md` accounts for every candidate-task sentence
  that is not an exact user quote;
- the staged original request matches its captured bytes or declares exact
  excerpt boundaries and omissions;
- every candidate-visible file named by the task exists and is readable from
  the candidate boundary;
- every selected byte has a digest and capture receipt and has passed the
  sensitive-content boundary;
- every historical criterion maps to exact authority;
- every candidate phase stops at its declared event boundary;
- no candidate file, filename, prompt, summary, or provenance entry reveals a
  later correction;
- no hidden requirement depends only on an author's interpretation;
- missing or truncated evidence is labeled and reflected in the
  `UNANSWERABLE` rule; and
- the artifact ledger accounts for each material file, commit, command output,
  and receipt used to reconstruct the correction.

Freeze only the selected packets. Retain `capture/` as the authoring record, but
do not treat unfrozen capture files as evidence a run received.
