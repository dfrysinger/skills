# Live-proof receipt

Use this receipt for user-visible or externally observable runtime changes. It
is a gate record, not prose evidence: the validator must accept it before
review, PR work, landing, or a success claim.

Keep the JSON outside the product repository unless the repository already has
an evidence-artifact convention. In Copilot CLI, also mirror its current state
into `live_proof_receipts` so compaction, rotation, and scheduled turns retain
the open gate.

## 1. Choose the claim boundary

Use one receipt for one independently observable boundary or claim. Keep the
dependent checkpoints of one sequential user journey together. Split unrelated
systems, independent refusal paths, bootstrap boundaries, and tamper lanes into
separate receipts so an iterative repair reopens only the proof it can reach.

Before rerunning after candidate movement, write a change-to-claim impact map
that names every changed runtime input, the path it reaches, affected receipt
ids, and any shared dependency that broadens the set. A lane label or new
commit hash does not establish reach.

Direct validation remains fingerprint-strict. An unaffected receipt from an
earlier execution needs an explicit checked correspondence record to establish
current applicability. Final acceptance requires all claims to apply to one
exact target fingerprint, including any eligible reused evidence. Per-claim
scope hashes are checked separately and do not replace that complete identity.

## 2. Freeze the candidate

Designate evidence and test-output paths before proof. They must be untracked
and unable to affect the build or runtime. Then generate the candidate object:

```bash
SKILL_DIR="<resolved development-loop skill directory>"
RECEIPT="$HOME/.copilot/session-state/<session>/files/live-proof.json"

python3 "$SKILL_DIR/scripts/validate-live-proof.py" fingerprint \
  --worktree "$PWD" \
  --exclude .live-proof-output \
  > /tmp/live-proof-candidate.json
```

Use `--additional-input <relative-path>` for ignored configuration or generated
inputs that affect the candidate. The helper records their hashes without
recording their contents. Never exclude a tracked file; the helper rejects it.

Copy the returned candidate object into the receipt. A later commit, tracked
change, untracked input, or named additional input changes the fingerprint.
Direct validation then fails; checked reuse below may establish applicability
without changing the execution receipt.

## 3. Record the complete flow

```json
{
  "schemaVersion": 1,
  "id": "dashboard-repair",
  "candidate": {
    "worktree": "/absolute/path/to/worktree",
    "head": "<commit>",
    "fingerprint": "sha256:<candidate fingerprint>",
    "excludedOutputs": [".live-proof-output"],
    "additionalInputs": []
  },
  "running": {
    "identity": "pid=12345 build=<runtime identity>",
    "candidateMatchEvidence": "The running process cwd and candidate-only runtime marker matched this worktree."
  },
  "scenario": {
    "trigger": "Open the saved dashboard and press Edit with Admin Assistant.",
    "terminalState": "The repaired dashboard renders after returning from chat.",
    "forbiddenOutcomes": [
      "the chat targets another enterprise",
      "the dashboard remains incompatible"
    ],
    "forbiddenOutcomeEvidence": [
      {
        "kind": "runtime",
        "source": "The final DOM snapshot contains neither forbidden state."
      }
    ],
    "checkpoints": [
      {
        "name": "repair handoff",
        "expected": "A repair chat opens for the dashboard enterprise.",
        "observed": "The chat opened for Avocado Corp with the dashboard id.",
        "evidence": [
          {"kind": "runtime", "source": "bridge snapshot checkpoint-1.json"}
        ],
        "result": "PASS"
      },
      {
        "name": "assistant mutation",
        "expected": "The assistant reads and recreates the saved dashboard.",
        "observed": "The real assistant completed both dashboard tool calls.",
        "evidence": [
          {"kind": "runtime", "source": "tool trace checkpoint-2.json"}
        ],
        "result": "PASS"
      },
      {
        "name": "terminal render",
        "expected": "The repaired dashboard renders persisted figures.",
        "observed": "The dashboard rendered all expected headline figures.",
        "evidence": [
          {"kind": "artifact", "source": "dashboard-repair-after.png"}
        ],
        "result": "PASS"
      }
    ]
  },
  "visual": {
    "required": true,
    "captures": [
      {
        "path": "dashboard-repair-after.png",
        "opened": true,
        "claim": "The dashboard shows populated seats, spend, usage, and unused-license cards.",
        "width": 1512,
        "height": 982,
        "pixelSpread": "PASS"
      }
    ]
  },
  "manualWorkaround": false,
  "unverified": [],
  "status": "PASS"
}
```

Use `visual.required: false` and an empty `captures` array only when no
acceptance criterion has a visual surface. A screenshot cannot replace the
interaction checkpoints that led to it.

Checkpoint evidence must use one of four direct kinds: `runtime`, `artifact`,
`query`, or `human-confirmation`. Test results are valuable deterministic
validation, but they are not live acceptance evidence and the validator rejects
`test` as a receipt evidence kind.

## 4. Validate the gate

```bash
python3 "$SKILL_DIR/scripts/validate-live-proof.py" validate "$RECEIPT"
```

The validator fails when:

- the candidate fingerprint changed without accepted reuse correspondence;
- the running candidate lacks identity-matching evidence;
- the flow lacks trigger and terminal checkpoints;
- any checkpoint lacks direct evidence or did not pass;
- forbidden outcomes were not checked;
- a visual capture is missing, unopened, dimensionally inconsistent, or blank;
- a manual workaround changed the supported flow;
- any acceptance criterion remains unverified;
- the terminal receipt status is not `PASS`.

The validator deliberately does not infer that a running process came from the
candidate. Project-specific skills must obtain that evidence from the process,
build, served revision, watcher, discovery file, or a candidate-only runtime
result and record it in `running`.

`FAIL`, `BLOCKED`, `STALE`, and `INCONCLUSIVE` are useful durable states, but
they do not pass this validator or open a completion gate.

## 5. Reuse unchanged-component evidence

Preserve the original execution receipt. A different commit or worktree does
not itself invalidate the observation, but accepting it for another candidate
requires explicit, checked input correspondence. Never replace its candidate,
running identity, model identity, checkpoints, or results with the new ones.

Before execution, add `--reuse-input <relative-file-or-directory>` to the
fingerprint command for every exercised executable path and relevant input.
Directory scopes include all descendants, including ignored files, so added
or removed runtime inputs are detected. File content, permissions, type, and
directory membership are hashed. Named `--additional-input` files are also
included automatically when reuse inputs are supplied. Excluded evidence
outputs are not excluded from these scopes: do not place evidence inside an
input directory. Symlinks and special files in reuse scopes are rejected
rather than treating a link's unchanged spelling as unchanged target content.

For a new execution, add `reuseCoverageEvidence` to its receipt, with all six
keys below. Each value names the relevant recorded paths and the evidence
establishing their coverage, or explains why that input class is inapplicable:

| Key | Coverage to establish |
| --- | --- |
| `executablePaths` | All exercised code, callers, loaded modules, and harness paths |
| `configuration` | Relevant flags, settings, and ignored configuration |
| `dependencies` | Actual dependency contents/identities, not only a manifest |
| `buildInputs` | Toolchain, build settings, and other artifact-producing inputs |
| `runtimeInputs` | Runtime/model identity, environment, external state, and fixture conditions |
| `generatedInputs` | Generated code, assets, and the artifacts actually loaded |

For non-file inputs, record deterministic, non-secret measurements of stable
input values (not observation timestamps or process IDs) in files included in
the scope and refresh those measurements for the target candidate.
An unchanged measurement file without a fresh check of the actual runtime,
environment, model, or external state is not correspondence evidence. If an
input cannot be identified or measured reliably, rerun the affected scenario.
Do not manufacture execution-time measurements after the fact or edit an old
receipt to add them. A legacy receipt without `reuseInputs` may instead use the
validated-source derivation below.

For the final frozen candidate, run `fingerprint` again with the same input
scopes, additional inputs, and output exclusions. Store that new candidate
object in a separate correspondence JSON:

```json
{
  "schemaVersion": 1,
  "sourceReceiptSha256": "sha256:<SHA-256 of the original receipt file>",
  "candidate": "<replace with the new fingerprint command's JSON object>",
  "checkedCorrespondenceEvidence": {
    "executablePaths": "Name the compared paths and closure/caller check.",
    "configuration": "Name the freshly compared settings and flag measurements.",
    "dependencies": "Name the compared installed dependency identities.",
    "buildInputs": "Name the compared toolchain and build-input measurements.",
    "runtimeInputs": "Name the fresh runtime, model, environment, and fixture checks.",
    "generatedInputs": "Name the compared generated assets and loaded artifacts."
  }
}
```

Replace every example value with actual evidence. Hash the original receipt
file with `shasum -a 256`; prefix the resulting digest with `sha256:`.
Then validate:

```bash
python3 "$SKILL_DIR/scripts/validate-live-proof.py" validate "$RECEIPT" \
  --reuse /path/to/correspondence.json
```

This validates the original scenario and visual requirements, checks its
receipt hash, recomputes the target's full fingerprint, and requires identical
recorded input scopes and hashes. With execution-time `reuseInputs`, the original
worktree need not still exist.
Output identifies the target fingerprint and `reusedFrom` original fingerprint
and receipt hash, not a new execution. Any relevant input change, removed scope,
missing coverage evidence, or later target mutation fails closed. Ordinary
validation without `--reuse` still requires an exact current fingerprint.

### Legacy receipts with a retained original candidate

Missing predeclared scope metadata alone does not require replay. If the
original worktree is still available at its recorded path and its full
candidate fingerprint still validates, the helper can derive a scoped baseline
now. This route does not reconstruct repositories or accept a replacement source
path. The original receipt bytes and execution identity remain unchanged.

Build the target candidate with `fingerprint --reuse-input` as above. In its
separate correspondence JSON, add:

- `"deriveLegacyBaseline": true`;
- `legacyCoverageEvidence`, an object with the same six keys as
  `checkedCorrespondenceEvidence`. Describe why the original recorded inputs
  cover the scenario, including original runtime/environment measurements, and
  explain any inapplicable input classes.

Keep `checkedCorrespondenceEvidence` for the fresh source-to-target comparison.
Coverage must come from the original fingerprint-bound files or original direct
evidence, not newly asserted old values. Relevant ignored inputs must already
appear in the old candidate's `additionalInputs`. Newly measuring an ignored
runtime, dependency, configuration, or generated input cannot establish what
the old execution used. Unknown relevant inputs keep the gate closed.

Validate and save the result separately:

```bash
python3 "$SKILL_DIR/scripts/validate-live-proof.py" validate "$RECEIPT" \
  --reuse /path/to/correspondence.json > /path/to/applicability.json
```

The helper validates the original full candidate before deriving any baseline,
rejects scoped files absent from that fingerprint's coverage, hashes the chosen
scope, and checks the original candidate again. It then requires identical
target input hashes and all ordinary receipt gates. The applicability output's
`legacyBaseline.origin` is `derived-during-validation`, with the derived input
hashes. It is not an execution-time snapshot or a new scenario run.

Every subsequent legacy validation repeats this derivation from the exact
original source; a supplied `legacyBaseline` is not trusted as input. Preserve
the original worktree until final admission. A stale, unavailable, or redirected
source, uncovered ignored/excluded inputs, or incomplete runtime correspondence
cannot use this route. Dirty and non-ignored untracked inputs are eligible when
the full original fingerprint still matches. Empty directories and other
filesystem properties not established by the original evidence must not be
treated as historical observations.

### Final-campaign identity and claim scopes

The complete candidate fingerprint covers the whole-tree identity and declared
additional inputs. `reuseInputs` records separately checked claim coverage, not
another executable candidate. Snapshots with scopes `src/a` and `src/b` therefore
share the same target fingerprint when the complete candidate is unchanged.
Changing either component still changes that complete fingerprint.

Keep each scope and its hashes intact. Validation recomputes both the complete
target identity and its scope records, then compares the scope to the original
execution's inputs. A matching target fingerprint alone is not evidence of
unchanged claim inputs. Declare relevant ignored runtime inputs as additional
inputs rather than relying on a scope to include them in the complete identity.

Maintain the complete applicable claim set outside these individual receipts:
map every final acceptance criterion to a direct receipt or to an original
receipt plus its checked correspondence record. Validate every referenced
record against the same exact frozen target fingerprint. Changed and uncovered claims
need new proof; an unchanged component's scenario need not be newly executed.
A reused receipt covers its entire original scenario, not an invented subset
that removes failing checkpoints.

The helper checks identities and required fields, not the truth of narrative
evidence, dependency-closure completeness, or the final acceptance inventory.
The proof owner and reviewer must check those. Deterministic test-result reuse
follows the same input-correspondence rule, including test code and fixtures,
but test receipts do not become live evidence through this helper. Mocks never
become actual model runs. Human review, merge, and release gates remain intact.
