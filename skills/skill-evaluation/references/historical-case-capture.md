# Historical case capture

Use this procedure to turn an agent conversation and its related artifacts into
a reproducible evaluation case. Capture first, select evidence second. Do not
construct the candidate packet while searching, because later corrections can
leak into an earlier blind phase.

## 1. Define the event boundary

Write the question the case tests, the actor whose session is authoritative,
the approximate time window, and the observable correction or accepted outcome
that will judge the candidate.

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

## 7. Audit completeness and leakage

Before freezing, verify:

- the stable session and artifact identifiers resolve to the captured sources;
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
