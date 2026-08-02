# Live curator transactions

`scripts/curator-run.py` is the mutation boundary for an approved `--live`
pass. It uses the same SQLite writer lease as dreaming and records an atomic
manifest under
`~/.copilot/skill-state/skill-review/curator-runs/<run-id>.json`.

## Plan

Before the first edit, write one JSON plan in the exact order mutations will
run:

```json
{
  "operations": [
    {
      "kind": "commit",
      "action": "patch",
      "root": "public",
      "skill": "umbrella",
      "paths": [
        "skills/umbrella/SKILL.md",
        "skills/umbrella/references/narrow-sibling.md"
      ]
    },
    {
      "kind": "archive",
      "skill": "narrow-sibling",
      "absorbed_into": "umbrella"
    }
  ]
}
```

`kind=commit` supports `action=patch|create`, an owning `root=public|local`,
and exact root-relative **file** paths. Directory scopes are not accepted:
every file the edit may add, modify, or remove must be enumerated. Public
registry files must be listed when a create changes them. `kind=archive`
resolves its root and registry paths from the frozen inventory.

Begin before mutation:

```bash
RUN_ID=$(scripts/curator-run.py begin \
  --plan /path/to/approved-plan.json \
  --report ~/.copilot/skill-state/reports/<approved>-curator-report.md)
```

`begin` acquires the shared writer lease, validates both git identities,
records starting commits and exact unrelated dirty state, rejects path
overlap, and freezes scheduled-dependency results for every planned archive.

## Patch or create

Record intent before editing:

```bash
OP_ID=$(scripts/curator-run.py intent \
  --run "$RUN_ID" --kind commit --root public --action patch \
  --skill umbrella --paths \
    skills/umbrella/SKILL.md \
    skills/umbrella/references/narrow-sibling.md)
```

Make the declared edit, validate it, evaluate behavioral changes, and run the
required reviews. Then use the scoped commit wrapper:

```bash
scripts/curator-run.py commit \
  --run "$RUN_ID" --op "$OP_ID" --message-file /path/to/message.txt
```

It commits only declared paths and records the commit plus exact ledger/state
effects. Never use a broad `git add -A` or a separate commit during a live run.

## Archive

`archive-skill.sh` records intent and completion itself when the run id is in
the environment:

```bash
SKILLS_CURATOR_RUN_ID="$RUN_ID" \
  skills/skill-manage/scripts/archive-skill.sh narrow-sibling \
    --absorbed-into umbrella
```

The archive still performs a current scheduled-dependency check immediately
before intent. The begin-time freeze prevents a partial run from discovering
an unsafe archive only after earlier mutations have landed.

## Finish or rollback

Renew the lease before/after long model or evaluation work:

```bash
scripts/curator-run.py renew --run "$RUN_ID"
```

After every planned operation completes:

```bash
scripts/curator-run.py finish --run "$RUN_ID"
```

On any failure, reverse the whole run:

```bash
scripts/curator-run.py rollback --run "$RUN_ID"
```

Rollback proceeds in global reverse operation order across both roots. It uses
`restore-skill.sh` for archives and `git revert` for patch/create commits,
removes only exact recorded ledger effects under an exclusive file lock, and
restores prior retirement/tombstone bytes. It refuses changed unrelated dirty
files, undeclared dirty paths, missing or rewritten commits, changed state
effects, or ambiguous root identities. An interrupted intent is recovered:
uncommitted declared paths are reset, while a single committed-but-unrecorded
archive is inferred and restored.
