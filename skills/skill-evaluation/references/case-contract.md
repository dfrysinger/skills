# Frozen case contract

## Case layout

```text
CORPUS/
  corpus.json
  cases/<case-id>/
    case.json
    evidence/<phase-id>/
    prompts/<phase-id>.md
    judge-reference/
    criteria.md
    prompts/judge.md
    capture/                 # optional authoring evidence, never staged directly
  frozen/<case-id>/
    current.json
    revisions/<root-digest>/
      case.json
      prompts/
      <phase-id>/bundle-manifest.json
      judge-reference/bundle-manifest.json
      case-manifest.json
  runs/<timestamp>/<case-id>/
```

`corpus.json` is an index, not a provenance root. A receipt binds one immutable
`frozen/<case-id>/revisions/<root-digest>/case-manifest.json`; adding, editing,
or replacing another case therefore does not invalidate it.

An explicit `case_type: repository-task` adds a frozen repository bundle,
source modes, offline admission, and executable grading. Its authoring and
execution contract is in [repository-tasks.md](repository-tasks.md).
Missing `case_type` retains prose evaluation.

## Native historical continuation

A first candidate phase can declare `session_restore`:

```json
{
  "history_file": "history.jsonl",
  "source_session_id": "original-session-id",
  "cutoff_event_id": "first-excluded-event",
  "skill_context": "before-target-load",
  "limitations": []
}
```

The history uses native `copilot sessions import` interchange, not raw native
`events.jsonl`. It stays in the phase manifest but is excluded from the
candidate workspace. The executor imports it in an isolated candidate home
and resumes the returned session ID. Unsupported or failed imports stop the
attempt; the runner never substitutes a transcript file for restored history.

Choose the cutoff using the playbook's
[replay starting-point procedure](evaluation-playbook.md#choose-the-replay-starting-point):
prevention, unaided recovery and guided recovery require different prior state.
End the prefix before the original triggering request or supported wake event.
The phase prompt contains that exact trigger; an invented correction is not
an unsteered continuation.
Restored phases receive no evaluation announcement or forced skill invocation.
Choose the skill-context policy explicitly:

- `before-target-load`: end before target activation; recorded invocations and
  target context are rejected. Use this policy for clean skill comparisons.
- `recorded-target-context`: preserve original target invocations and loaded
  text unchanged. This supports historical behavior validation or a matched
  update-during-work experiment: both arms retain the same historical prefix,
  while the declared intervention changes future available skills. Record
  actual later loads and outcomes; this tests recovery after an update, not a
  clean replacement or prevention claim. No new invocation is guaranteed.
  Record historical body hashes separately from each arm's pinned available
  catalog, with differences in provenance and limitations.

Audit other instruction exposure and required state separately. Neither policy
proves complete restoration. Do not silently strip or replace old instructions.

Bind files, instructions and operational state to the same cutoff. For
prevention, keep the wrong response and later correction in hidden judge
evidence. Recovery cases retain earlier mistakes; guided recovery also exposes
the correction at its declared phase. Keep subsequent answers hidden. Disclose path,
tool and runtime differences. Do not dispatch when missing state prevents the
required actions or criteria.

For clean replacement, choose a real request boundary before the relevant
skill's first exposure, then let each arm load its own version naturally.
Keep earlier mistakes only when that boundary actually retains them; otherwise
the test measures prevention rather than recovery.

For an in-place update, retain the same old loaded text in both arms and
make the old or proposed catalog available before replaying the same real
trigger. Use the same supported reload/setup operation in both arms and
record its effects and any host notices. `/skills reload` refreshes availability;
it is not proof of automatic invocation or rewritten conversation history.
Verify host-specific behavior before claiming either. An extra request to
reload the target body is corrective steering unless it was the real trigger.
The existing context policy records exposure; it does not itself execute
an interactive reload or prove catalog replacement in a restored process.

Restored repository tasks also require `repository_task.candidate_permissions`:

```json
{
  "write_paths": ["src/example.py"],
  "shell_commands": ["python3 -m unittest -q"]
}
```

These are operator-approved files and literal native command rules, not a
candidate-editable policy. Wildcards, shell operators, escaping paths and
permission-changing flags are rejected. Normal path and URL checks still
apply. This mode does not expose delegation tools. Prove import/resume and the
native permission boundary without model calls before paid attempts, then use
the existing Actions runtime for actual candidate and judge execution.
Repository admission and offline grading remain required.

## Evidence boundaries

- Candidate phases contain only evidence available at that point.
- A later phase may add evidence but cannot change bytes from an earlier frozen
  phase without creating a new case revision.
- Hidden judge evidence contains the criterion authority, accepted outcome,
  or an independently defined synthetic oracle. Corrections stay hidden for
  prevention and unaided recovery; guided recovery exposes the exact correction
  only at its declared phase. All other judge-only material remains absent from
  candidate prompts and workdirs.
- `judge-reference/` contains at least one frozen file; criteria prose alone is
  not a reference packet.
- Exact quotations carry their source record and stable event identifier
  together.
- Every criterion in a historical or transcript-derived case maps to one exact
  frozen authority record and event identifier. Synthetic criteria identify
  the independently defined oracle from which they derive.
- Generated summaries identify their source artifacts and remain evidence, not
  authority.
- Candidate evidence preserves the real operating context, including natural
  ambiguity, incomplete requests, and competing repository or source guidance
  that the real agent would receive. A case is not repaired merely because
  those inputs make it harder.
- Historical candidate tasks present exact user wording before any added
  context. Exact excerpts declare their boundaries and omissions. Restored
  context and evaluation-only operating instructions are separately labeled,
  and every added sentence is accounted for in
  `capture/candidate-text-audit.md`.
- Every candidate-visible path named by the task exists and is readable through
  the staged candidate boundary. A source-tree file that is absent, moved, or
  denied after staging does not satisfy this contract.
- A packet revision requires provenance evidence that the prior revision
  omitted, misstated, invented, or gave false authority to context relative to
  the represented real situation. The revision records that mismatch; it does
  not rewrite a faithful real-world request toward the expected answer.
- A transcript-derived case keeps its raw capture and query receipts under
  `capture/`, then copies only deliberately selected exact evidence into a
  candidate phase or `judge-reference/`. The runner never stages `capture/`
  directly.

## Judgment

Judge the behavioral claim, not matching words. Criteria should state:

- behavior that must be present;
- evidence-backed boundaries that must remain;
- overcorrections or unsafe shortcuts that fail the case; and
- when missing evidence makes the case `UNANSWERABLE`.

Every material case also carries the criterion classification described in
[`judgment environment fit`](judgment-environment-fit.md). Behavioral
correctness may depend only on candidate-observable evidence and the honesty
and completeness of required handoffs. Post-environment facts such as live
capacity, deployment, authentication, production traffic, or runtime belong to
later qualification unless the candidate environment can actually observe
them.

The judges include at least one Claude and one GPT model. Each judge reads
candidate outputs, receipts, and hidden evidence, but not another judge's
result. A final `PASS` requires unanimous `PASS`; any `FAIL` yields `FAIL`; with
no `FAIL`, any `UNANSWERABLE` yields `UNANSWERABLE`.

## Revisions

Freezing writes:

- one SHA-256 for every evidence and prompt file;
- one manifest SHA-256 for every phase and the judge packet;
- one per-case root manifest containing those manifest digests; and
- the exact source-relative path for every copied file.

Replacing a frozen case is explicit and path-scoped. It creates an immutable
revision directory and atomically updates `current.json`; all prior frozen
revisions and their run receipts remain verifiable.
