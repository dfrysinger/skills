# Read-only Actions run observation

`scripts/observe_campaign_runs.py` records GitHub Actions metadata for exact
known run bindings. It uses the normal GitHub CLI authentication configuration
and only `gh api --method GET`. It does not read or print tokens, dispatch runs,
upload artifacts, cancel work, or change remote state. Python's standard
library and an authenticated `gh` executable are the only dependencies.

## Input and invocation

Create a JSON array of the runs to observe. Each entry requires these fields:

```json
[
  {
    "id": 123,
    "workflow_id": 456,
    "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "head_branch": "main",
    "run_attempt": 1,
    "event": "workflow_dispatch",
    "repository": {
      "id": 789,
      "full_name": "example/evaluation",
      "private": false
    }
  }
]
```

Use actual known bindings, not the illustrative values above. IDs and attempts
must be positive integers, not booleans. The SHA must be exactly 40 hexadecimal
characters. Branch and event must be nonempty strings without control
characters. Repository records must contain a positive ID, an exact
`full_name` matching `--repository`, and a boolean `private` flag. Public and
private repositories are supported; all requested records must agree.
Duplicate run IDs, duplicate JSON object keys, empty arrays, extra input fields,
invalid bounds, and URL/path-shaped repository or host arguments are refused
before any API call.

```sh
python3 skills/skill-evaluation/scripts/observe_campaign_runs.py \
  --repository example/evaluation \
  --runs known-runs.json \
  --output run-observation.json \
  --max-pages 10 \
  --max-calls 20 \
  --timeout 30
```

`--host` defaults to `github.com` and accepts a DNS hostname without a scheme,
port or path. It is passed explicitly to `gh`, independent of `GH_HOST`.
`--timeout` is the per-call subprocess timeout in seconds, from 1 through 300.
`--max-pages` accepts 1 through 1000; `--max-calls` accepts 1 through 10000.
These are resource bounds, not quota or model assumptions. Calls are sequential
and never automatically retried.

The output's parent directory must already exist. Output creation is exclusive:
an existing file or symlink is refused, and a racing creator cannot be
overwritten. No output is created until every requested run has been verified.
Errors return a nonzero exit code and an explicit refusal on stderr, not a
success-shaped fallback. GitHub CLI error output is not relayed.

## Retrieval and identity

The observer enumerates repository runs in pages of 100, projecting only
`id`, `workflow_id`, `path`, `event`, `head_sha`, `head_branch`, `run_attempt`,
`status`, `conclusion`, and repository `id`, `full_name`, `private`. Actor and
avatar URLs are not requested in the projection or retained in the output.
The byte measurement covers projected CLI stdout, not full HTTP response bytes.

Every page must have a typed nonnegative `total_count`, the expected page
length, unique positive run IDs, complete valid records, and the same declared
count. Enumeration continues to the declared membership even if all requested
runs were found earlier. Count drift, malformed data, and incomplete membership
are refusals. If the declared listing exceeds `--max-pages`, observation stops
with an error; it does not treat a truncated list as absence or spend additional
calls on direct fallback.

Only exact requested bindings become observations. A listed requested ID with
a different attempt, SHA, workflow, branch, event, or repository record is a
refusal. A similar run with another ID cannot replace an original. Requested
IDs missing from a complete listing are fetched by exact ID, within the
remaining call budget, and must satisfy the same binding checks. Missing,
failed, timed-out, or mismatched direct responses mean UNKNOWN/refusal, never
completion. A later rerun of the same ID is not relabeled as the original
attempt.

Known statuses are `queued`, `in_progress`, `completed`, `waiting`, `requested`,
and `pending`. `completed` requires a nonempty string conclusion; all other
statuses require a null conclusion. Nonterminal runs can be successfully
observed without being completed. A `failure` conclusion is also a valid
metadata observation.

## Reading the snapshot

The JSON contains the requested observations in input order, each with list
page or direct-GET provenance and a one-based call index. It also records call
endpoints, call count, projected response bytes, monotonic client wall seconds,
and `non_atomic: true`. Pages and direct reads happen at different instants.
Stable counts do not establish an atomic snapshot or guarantee unchanged
membership between reads.

Exit code zero means every requested binding was observed, not that its
workflow succeeded. A successful workflow is not skill or product PASS.
This snapshot provides no whole-repository capacity, available-slot, quota,
model, selection, or efficacy inference. It is not permission to reuse
evaluation proof. Keep model and user scopes separate in the evaluation
consumer.

## Offline checks

```sh
cd skills/skill-evaluation/scripts
python3 -m unittest test_observe_campaign_runs
```

The tests invoke the actual CLI with a local `gh` substitute that records
arguments and serves synthetic JSON. They make no network or model calls and
cover batched listing, direct fallback, identity mismatches, malformed
membership, changing counts, budgets, nonterminal states, and refusal paths.
Live host/authentication behavior requires a separate read-only canary.
