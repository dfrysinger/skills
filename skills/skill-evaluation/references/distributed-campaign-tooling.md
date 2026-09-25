# Distributed campaign tooling

The skill includes reusable tooling for evaluations that need native runners,
full repositories, container graders, or many parallel attempts:

- `scripts/package_distributed_campaign.py` creates deterministic full and
  candidate-safe archives plus a completion manifest.
- `scripts/distributed_campaign.py` validates the frozen matrix, routes work by
  platform, executes or resumes stages, verifies artifact lineage, and retains
  checksum-addressed evidence.
- `templates/distributed-campaign.yml` is a GitHub Actions workflow template.
- `templates/distributed-eval-images.example.json` and
  `templates/distributed-eval-dependencies.example.json` document the external
  image and dependency manifest shapes.

These files are infrastructure, not a bundled corpus. Candidate repositories,
hidden graders, reference answers, package archives, dependency archives, and
result artifacts remain in the operator's private evaluation repository or
private release.

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
python3 -m unittest \
  skills/skill-evaluation/scripts/test_skill_eval.py \
  skills/skill-evaluation/scripts/test_distributed_campaign.py \
  skills/skill-evaluation/scripts/test_package_distributed_campaign.py
```

Before a full fan-out, dispatch one attempt and verify that the candidate
artifact contains no package or live worktree, the product job reconstructs
the recorded tree, and the final retained receipt contains both archive
identities.
