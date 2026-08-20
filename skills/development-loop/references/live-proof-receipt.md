# Live-proof receipt

Use this receipt for user-visible or externally observable runtime changes. It
is a gate record, not prose evidence: the validator must accept it before
review, PR work, landing, or a success claim.

Keep the JSON outside the product repository unless the repository already has
an evidence-artifact convention. In Copilot CLI, also mirror its current state
into `live_proof_receipts` so compaction, rotation, and scheduled turns retain
the open gate.

## 1. Freeze the candidate

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

Copy the returned candidate object into the receipt. Any later tracked change,
untracked runtime input, or named additional input changes the fingerprint and
makes the receipt stale.

## 2. Record the complete flow

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

## 3. Validate the gate

```bash
python3 "$SKILL_DIR/scripts/validate-live-proof.py" validate "$RECEIPT"
```

The validator fails when:

- the source candidate changed after proof;
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
