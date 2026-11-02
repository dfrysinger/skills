# Shared task catalog

The catalog shares task descriptions, exact revisions, historical observations,
exposure records and suite definitions through an approved private Git
repository. It does not share transcript packets, hidden answers or raw logs.
Clone that repository to `$HOME/.copilot/skill-task-catalog`, or set
`SKILL_EVAL_CATALOG` to another checkout. Git synchronization is an explicit
operator action; catalog commands never push or launch paid evaluations.

Resolve `SKILL_DIR` to this installed skill's directory. The examples below
use a synthetic case; supply safe descriptions rather than copying answers.

```bash
CATALOG="${SKILL_EVAL_CATALOG:-$HOME/.copilot/skill-task-catalog}"
python3 "$SKILL_DIR/scripts/skill_eval.py" catalog init "$CATALOG"
python3 "$SKILL_DIR/scripts/skill_eval.py" catalog import "$CATALOG" \
  --corpus /approved/local/corpus --namespace example --case continuation \
  --family continuation-incident --title "Continue unfinished work" \
  --summary "Resume the remaining authorized task" --behavior continuation \
  --related-skill development-loop --tag recovery --include-history
python3 "$SKILL_DIR/scripts/skill_eval.py" catalog search "$CATALOG" \
  --skill unattended-run --text continuation --lineage unattended-run
python3 "$SKILL_DIR/scripts/skill_eval.py" catalog history "$CATALOG" \
  --namespace example --case continuation
```

`search` also accepts `--namespace` and `--case`; `history` accepts the same
filters. `--include-history` uses the native history reader. Each run record
retains an opaque native run identity, population identity, attempt ordinal,
outcome and available measurement. Reimporting unchanged evidence is
idempotent. Later observations of an incomplete run remain separate snapshots,
not new independent attempts or permission to pool qualification.

Import defaults to the current frozen revision; `--revision` selects a
retained older revision. A namespace and native case ID identify one task.
All its revisions must keep the same incident `--family`. Related captures
from one incident share that family across tasks. Conflicting metadata is
rejected, including conflicts introduced by merging separate checkouts.
Search reports `unbound` or `bound-but-not-verified`, never cached acceptance.

## Plan and replay exact suites

Bind a namespace to a local corpus, then copy exact revisions into a new local
output. Take the revision from search and the suite identity from plan:

```bash
python3 "$SKILL_DIR/scripts/skill_eval.py" catalog bind "$CATALOG" \
  --namespace example --corpus /approved/local/corpus
python3 "$SKILL_DIR/scripts/skill_eval.py" catalog plan "$CATALOG" \
  --member "example:continuation@$REVISION" \
  --lineage unattended-run --lineage development-loop --role regression
python3 "$SKILL_DIR/scripts/skill_eval.py" catalog materialize "$CATALOG" \
  --suite "$SUITE" --output /new/local/replay
python3 "$SKILL_DIR/scripts/skill_eval.py" verify /new/local/replay/example
```

Repeat `--member` for additional cases. Each namespace becomes a normal corpus
under the output directory, avoiding collisions between native case IDs.
Existing `run` and `run-suite` commands operate on those corpora. Original
pointers stay unchanged. Missing bindings, corrupt packets or symlinks refuse
the whole operation without publishing partial output. Output inside the
catalog or overlapping a source corpus is refused.

After running, import each selected revision again with its same descriptions,
`--include-history` and the replayed namespace corpus as `--corpus`. This does
not change the namespace binding. Local paths live only in ignored `.local`;
each machine establishes its own bindings. Publish only screened metadata
records, never materialized output or local inventory files.

## Exposure and holdouts

`development` and `regression` planning records exposure before packet delivery.
Lineages identify continuing skill families, not versions: renamed or combined
skills include their inherited keys. Any recorded development, regression,
feedback or explicit unknown exposure blocks the whole incident family for
those lineages, across revisions. Missing exposure is unknown too.

Use `catalog expose` with `--family`, repeated `--lineage`, `--kind` and
`--note`. Kinds are `unknown`, `unexposed`, `development`, `regression` and
`feedback`. Attest `unexposed` only from actual knowledge for every selected
lineage. A later clean attestation never erases a recorded use or unknown.
Record `feedback` before using a held-out result to choose another candidate.

`--role holdout` requires recorded unexposed status. Materialization rechecks
current local exposure even for an old plan. Both results name the exposure
snapshot and state its limit: **not globally verified fresh**. Separate Git
checkouts cannot see unpublished or concurrent exposure. Synchronize and
coordinate usage before making stronger claims; independently administered
freshness requires another accepted authority, not this bookkeeping.
