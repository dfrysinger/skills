# Skill evaluation cases

Create `.skill-evaluation-cases.json` at the candidate skill root. It is local
evaluation input, not part of the public skill.

```json
{
  "schema_version": 1,
  "source": {
    "task_id": "source:unique-task-id",
    "prompt": "A representative task the skill should improve.",
    "required_regex": [
      {"id": "required-outcome", "pattern": "(?i)observable result"}
    ],
    "forbidden_regex": [
      {"id": "harmful-action", "pattern": "(?i)unsafe shortcut"}
    ],
    "friction_regex": [
      {"id": "unnecessary-step", "pattern": "(?i)redundant step"}
    ]
  },
  "sibling": {
    "task_id": "sibling:distinct-task-id",
    "prompt": "A related task where an overfitted rule would be harmful.",
    "required_regex": [
      {"id": "preserved-outcome", "pattern": "(?i)correct sibling result"}
    ],
    "forbidden_regex": [],
    "friction_regex": []
  }
}
```

Assertions are never sent to the model. The runner executes each prompt in an
empty working directory and isolated `COPILOT_HOME`, once with no candidate
plugin and once with the candidate loaded as the only non-builtin skill. Only
the `skill` and `view` tools are exposed. Candidate runs are invalid unless the
model actually loads the named skill.

The gate passes only when the candidate makes a required source outcome newly
pass, while a passing sibling baseline continues to pass without added
friction. A friction-only delta from one sample is marginal and remains
`inconclusive`; malformed evidence is also `inconclusive`. A failed candidate
source or sibling regression is `regression`.

Run:

```bash
skill-review/scripts/run-skill-evaluation.sh <skill-dir> --model <exact-model>
skill-review/scripts/skill-evaluation.py gate <skill-dir>
```

Receipts are content-addressed under
`~/.copilot/skill-state/skill-review/evaluations/`. They bind the candidate
inventory, case manifest, exact model, Copilot CLI version, runner, prompt,
comparator, and flags. Any candidate or case edit makes the gate stale.
