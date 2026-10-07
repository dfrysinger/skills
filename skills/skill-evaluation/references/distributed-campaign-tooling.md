# Distributed campaign tooling

The skill includes reusable tooling for evaluations that need native runners,
full repositories, container graders, or many parallel attempts:

- `scripts/package_distributed_campaign.py` creates deterministic full and
  candidate-safe archives plus a completion manifest.
- `scripts/distributed_campaign.py` validates the frozen matrix, routes work by
  platform, executes or resumes stages, verifies artifact lineage, and retains
  checksum-addressed evidence.
- `scripts/observe_campaign_runs.py` retrieves bounded, projected Actions run
  metadata for exact known bindings with checked direct fallback.
- `templates/distributed-campaign.yml` is a GitHub Actions workflow template.
- `templates/distributed-eval-images.example.json` and
  `templates/distributed-eval-dependencies.example.json` document the external
  image and dependency manifest shapes.

These files are infrastructure, not a bundled corpus. Candidate repositories,
hidden graders, reference answers, package archives, dependency archives, and
result artifacts remain in the operator's private evaluation repository or
private release.

## Observe known attempts

Use [`run-observation.md`](run-observation.md) to prepare exact run bindings and
collect one read-only snapshot. Batching can replace individual metadata GETs
when the requested runs share a small repository listing. Older runs missing
from a complete listing use direct GETs; an incomplete or mismatched listing
fails explicitly instead of proving absence.

Record the tool's call count, projected bytes and elapsed time against the
individual-read baseline before choosing it for a large repository. Listing
every run can cost more than a few direct reads. The snapshot is non-atomic and
does not grant dispatch capacity or turn workflow success into product PASS.

## Prepare the carrier repository

Copy the workflow template to
`.github/workflows/distributed-campaign.yml`. Keep the skill directory at
`skills/skill-evaluation/`, or update every script path in the copied workflow.
Create image and dependency manifests from the examples. An empty `assets` or
`dependencies` list is valid when the campaign does not use that resource
class.

Configure the repository secret `COPILOT_GITHUB_TOKEN`. The workflow maps it
only into candidate and judge subprocesses. Do not put a token value in a
workflow input, manifest, package, log, or committed environment file.

The workflow accepts the GitHub CLI host as an input and otherwise derives
repository identity from the Actions environment. It does not contain an
organization, repository, username, private release name, or credential value.

## Build split payloads

Start with one prepared package containing:

- `package-manifest.json`;
- `execution-matrix.json`;
- candidate-visible source and task material;
- treatment plugins or adapters;
- a package-local runtime at `runtime/run-attempt.py` implementing the case
  contract; and
- hidden graders, fixtures, and judge evidence under paths selected for
  removal.

Create deterministic payloads:

```sh
python3 skills/skill-evaluation/scripts/package_distributed_campaign.py \
  --source prepared-package \
  --full-root build/full \
  --candidate-root build/candidate \
  --full-archive build/full.tar.gz \
  --candidate-archive build/candidate.tar.gz \
  --receipt build/package-receipt.json \
  --completion build/completion.json \
  --hidden-pattern 'cases/*/*/hidden'
```

The command refuses existing outputs, requires at least one removed hidden
path, preserves one package manifest across both payloads, and records archive,
inventory, and tree digests.

For large packages, `--hash-workers 4` schedules independent file reads in
parallel while retaining sorted inventory and tree records. The default is one
worker; the accepted range is 1 through 32. Worker count is recorded in the
packaging receipt, not in either payload, so changing it does not change archive
bytes or completion identities for unchanged inputs. Hash-read errors still
fail packaging. Keep source inputs unchanged during packaging.

Choose the worker count with a representative local comparison. Concurrent
hashing can shorten the file-reading stage, but small files, slow storage or
contention can make it slower. This option does not parallelize compression,
upload or model work, and does not establish a full-feedback or cost saving.

Publish both archives and `completion.json` as private release assets. Supply
their exact SHA-256 values when dispatching the workflow.

## Candidate isolation

Split packages support macOS-native candidate attempts whose product proof does
not require an external dependency archive. The planner rejects split
Linux-native attempts and split attempts with dependency archives. Use an
unsplit package for those routes, or extend the workflow with a separate
candidate job and dependency reprovisioning before enabling them.

For supported split campaigns, candidate execution and hidden product
evaluation run in different GitHub Actions jobs:

1. The candidate job downloads only the candidate-safe archive.
2. After materialization and treatment staging, the carrier deletes the
   extracted package before starting Copilot.
3. The job retains candidate patches, status, transcript, and receipts, but not
   the live worktree or package.
4. A fresh product job downloads the retained candidate evidence and the full
   hidden archive.
5. The product job reconstructs each repository from its baseline and captured
   patch, requires the reconstructed Git tree to match the candidate receipt,
   then runs product proof.
6. Linux finalization revalidates the candidate archive, full archive, package
   manifest, attempt tuple, source run, source revision, and retained artifact.

Process cleanup and transcript auditing remain defense-in-depth. The job
boundary is the control that prevents candidate-created processes from
observing hidden bytes.

## Check retained stages before provisioning

The Linux finalization job runs `preflight-finalize` after verifying and
extracting its macOS artifact and sealed package, but before changing Docker,
downloading a grading image or installing the judge CLI. It uses the same
stage, package, attempt, dispatch-lineage and product-evidence checks that
finalization repeats before grading.

A complete primary stage receipt takes precedence over an obsolete candidate
receipt. When the primary receipt is missing, the existing split product-stage
recovery rules still apply: a valid candidate receipt, empty dependency runtime
and completed product evidence can reconstruct it without another candidate
model call. Missing or mismatched evidence stops the job before provisioning.

The preflight requires no model token and does not grade the attempt. A valid
failed product result remains eligible for finalization and is not relabeled
as success. `READY_FOR_FINALIZATION` means only that retained inputs passed
these checks; product success and skill qualification remain separate.
Preflight recovery may write the derived `macos-stage-receipt.json` inside the
owned retained run directory. No live candidate source is changed.

## Package runtime contract

The carrier intentionally does not encode a product or skill. The package owns
candidate materialization, candidate invocation, product exercise,
deterministic grading, and judge inputs through its runtime module and case
manifests. The carrier requires:

- immutable attempt IDs and identity tuples;
- one `arm64` platform (`macos` or `linux`) per case;
- explicit candidate timeouts;
- content-addressed source bundles, images, and dependency archives;
- candidate source capture as binary Git patches plus status files;
- product evidence with file digests;
- deterministic target and regression receipts; and
- structured judge JSON.

When a hidden scaffold provides a sealed Cargo Git checkout but a fresh macOS
runner has no ambient Cargo registry, the carrier runs credential-stripped
`cargo fetch --locked` from a separately materialized owner-sealed baseline,
not the candidate's modified workspace. The fetch uses an allowlisted
environment with a throwaway home and records the manifest, lock, command, and
log digests. The product command then runs with the resulting cache and its own
offline controls.

Keep package-specific builders and adapters with the private corpus unless they
are independently generalized. Do not publish historical cases, hidden
criteria, reference patches, private repository names, release names, or
retained model output.

The optional Linux resume route accepts only a structured source failure with
`resumableBoundary: "candidate-setup"`. A package runtime may set that value on
an exception as `resumable_boundary = "candidate-setup"` only when the failure
occurred before model launch. Human-readable error text is not used to authorize
a resumed attempt.

## Validate before use

Run:

```sh
PYTHONPATH=skills/skill-evaluation/scripts python3 -B -m unittest \
  skills/skill-evaluation/scripts/test_skill_eval.py \
  skills/skill-evaluation/scripts/test_distributed_campaign.py \
  skills/skill-evaluation/scripts/test_package_distributed_campaign.py \
  skills/skill-evaluation/scripts/test_observe_campaign_runs.py
```

Before a full fan-out, dispatch one attempt and verify that the candidate
artifact contains no package or live worktree, the product job reconstructs
the recorded tree, and the final retained receipt contains both archive
identities.
