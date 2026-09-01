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

## Evidence boundaries

- Candidate phases contain only evidence available at that point.
- A later phase may add evidence but cannot change bytes from an earlier frozen
  phase without creating a new case revision.
- Hidden judge evidence contains the correction, accepted outcome, or an
  independently defined synthetic oracle. Candidate prompts and workdirs never
  include it.
- `judge-reference/` contains at least one frozen file; criteria prose alone is
  not a reference packet.
- Exact quotations carry their source record and stable event identifier
  together.
- Every criterion in a historical or transcript-derived case maps to one exact
  frozen authority record and event identifier. Synthetic criteria identify
  the independently defined oracle from which they derive.
- Generated summaries identify their source artifacts and remain evidence, not
  authority.
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
