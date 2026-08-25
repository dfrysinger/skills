# Private skills plugin + shared packaging infrastructure

Work order. Buildable without the conversation that produced it.

## Objective

Publish personal and machine-specific skills from a private plugin repo that
installs into Claude Code, Copilot CLI and Codex on every machine the owner
uses, and move the packaging logic those repos share into one place so a
cross-platform packaging bug is fixed once.

## Non-goals

Named explicitly, because each is something a reasonable reader would otherwise
assume is included.

- **Not merging the two general skill sets.** `~/.copilot/skills/` holds ~52
  mostly general-programming skills that overlap the public repo. Reconciling
  those is separate work and out of scope here.
- **Not a plugin SDK, CLI, or npm package.** The shared piece is manifest
  templates plus one validator. A published tool is a generalization for callers
  that do not exist.
- **Not touching the public repo's skill content.** Only its packaging files may
  change, and only to consume the shared generator.
- **Not general CI.** No test or lint workflow is added. One narrow exception is
  in scope and named in the fail-closed evidence: a repository-side enforcement
  of the secret gate, because a local hook alone cannot bind a second machine.
- **Not multi-user or org distribution.** One owner, private repos, personal
  machines.
- **Not changing how skills are authored.** `writing-great-skills` and
  `skill-create` continue to govern content.
- **Not making machine-specific skills machine-agnostic.** Skills describing
  this Mac's Home Assistant, Colima and printer stack stay specific by design;
  other machines reach this one over Tailscale SSH, so a skill describing the
  *target* is correct wherever it runs. They must name paths and services
  explicitly rather than assuming "local".
- **Not migrating `1password`, `job-hunt-mcp`, `pdf`, or
  `reading-session-transcripts`** in this change. Domain skills only; the rest
  is a later decision.

## Lane: CRITICAL

Systemic on its face — it introduces a distribution mechanism shared by three
host CLIs and two repositories. It is **critical** on privacy: the repo's whole
purpose is to hold personal and home-automation material, and the failure mode
is disclosure. A repo created public by default, or a secret committed into it,
publishes the owner's home network, device identifiers and infrastructure
layout.

This session already produced the precedent: an exported transcript carried a
printer access code, which propagated into a second location before it was
caught. Personal skills are a standing invitation to the same class of mistake.

### Rollback

Every step is reversible without data loss:

1. `claude plugin marketplace remove dfrysinger-skills-private` and delete
   `~/.claude/plugins/marketplaces/dfrysinger-skills-private/`.
2. Recovery of the skills themselves: before the step-6 deletion, the working
   copies in `~/.claude/skills/` are the source and nothing needs recovering.
   `~/.claude/skills/` is a CLI-managed directory, **not** a git repository, so
   after deletion the only recovery sources are (a) the pre-delete tarball
   required by migration step 6, and (b) `git checkout` of the skill directories
   from `skills-private`. The tarball exists because (b) depends on the private
   repo being reachable and on the move having preserved content.
3. The public repo's packaging change is a single commit; revert restores its
   hand-maintained manifests.

Rollback trigger: any host fails to load the private plugin after install, or
the validator reports drift the generator cannot fix.

### Fail-closed evidence

The boundary is "no secret and no unintended publication". Each item below names
the component that enforces it, because a rule with no owner is a report.

- **Visibility, at creation.** The repo is created with an explicit private flag;
  the creation command's own failure is the first gate.
- **Visibility, on every emission.** The **generator** — not the validator —
  refuses to emit manifests for a repo whose config declares
  `visibility: private` unless a fresh `gh repo view --json visibility` returns
  `PRIVATE`. Repos declaring `visibility: public` skip the assertion, so the
  same tooling serves the public repo unchanged. This converts invariant 1 from
  a one-time claim into a repeated one; see the residual risk below.
- **Secrets, at commit.** A `pre-commit` hook installed into `skills-private`
  rejects the commit. Not a script that must be remembered — the acceptance
  criterion is that `git commit` itself fails.
- **Secrets, on a second machine.** A local hook binds only the machine it is
  installed on. Server-side `pre-receive` hooks are GitHub Enterprise Server
  only, and push protection with custom patterns needs a paid Secret Protection
  add-on, so **github.com cannot reject this push before accepting it**. The
  honest split is therefore:
  - *Prevention* is the bootstrap step: no second machine may push until the
    hook is installed, and cloning is not enough — migration step 3 installs it
    explicitly. This is the load-bearing half.
  - *Detection* is a post-push workflow that scans the received ref and alerts.
    It runs after acceptance, so it is a report, not a gate. This is the narrow
    CI exception named in the non-goals.

Absence of a warning is not evidence. Each check must produce an explicit pass
line naming what it verified.

**Residual risk, accepted:** invariant 1 is enforced at creation and re-asserted
on every manifest emission. Between emissions the repository could be made
public by an out-of-band action (`gh repo edit`, a transfer, a fork) and nothing
would notice until the next emission. Continuous monitoring is out of scope.

**Residual risk, accepted:** a second machine that pushes before its hook is
installed lands the secret in remote history, where deleting it does not remove
it. github.com offers no pre-acceptance gate at this tier, so the exposure
window is real and bounded only by the bootstrap discipline above. Recovery is
history rewrite plus credential rotation — the same response the fail-closed
section already assumes for a leaked access code.

### Secret classes in scope

A scanner that catches only high-entropy or prefixed credentials does **not**
satisfy this, because the artefacts these skills actually carry are short and
low-entropy.

The ruleset has **two tiers**, keyed on the same declared visibility the
generator already reads. Conflating them would make the gate reject the very
content the private repo exists to hold: `bambuddy` documents the container
network by design, and its `references/networking.md` carries fourteen LAN
addresses across eight distinct hosts. A single always-reject table would block
migration step 4's own commit, and the builder's only escape — a wide exemption
invented on the spot — silently reopens the disclosure hole.

**Tier 1 — rejected in every repo, public or private.** These are live
authentication material: possession is compromise, and a private repo is still
the wrong place for them.

| class | shape | example form |
|---|---|---|
| printer LAN access code | 8 alphanumeric characters, in proximity to `access_code` | `access_code: <8 chars>` |
| AMS / RFID identifiers | long hex `tag_uid`, `tray_uuid`, `chip_id` | 16–32 hex chars |
| generic credential | token, bearer, password, private key | conventional patterns |

**Tier 2 — rejected in the public repo, permitted in `skills-private`.** These
are locators, not credentials. They identify a host that is already behind
Tailscale auth or a LAN boundary; publishing them is the leak, storing them in
a private repo is the payload.

| class | shape | example form |
|---|---|---|
| device serial | vendor serial adjacent to `serial`/`serial_number` | printer and AMS serials |
| network identity | Tailscale hostnames, LAN IPs, HA internal URLs | `*.ts.net`, `192.168.*`, `172.19.*` |

The scanner and its ruleset live in the shared infrastructure so both repos and
both enforcement points use one definition, selecting the tier set from the
repo's declared visibility. Approved fixture syntax for documentation examples
must be defined alongside it, so a public skill can show a payload shape
without tripping the gate.

## Constraint provenance

Every constraint that materially narrowed this design, where it came from, and
what would force revisiting it. Prior configuration is provenance, not proof.

| constraint | provenance | evidence / owner | protects | revisit when |
|---|---|---|---|---|
| Five manifests per repo | platform behavior | each of the three CLIs reads its own; all five verified working in the public repo | discovery on every host | a host changes its discovery mechanism, or a shared manifest spec appears |
| Two allowlists, 24 Claude / 23 Copilot | compatibility | `rubber-duck` ships as a Copilot built-in; verified in both manifests | a repo skill shadowing a host built-in | Copilot drops the built-in, or the counts converge |
| Distribution is a **private git repo** | user outcome | must sync across machines *and* three CLIs; private HTTPS clone + `marketplace add` proven this session | keeping domain skills off a public repo | a host gains native private skill sync |
| Every emission bumps the version | platform behavior | cache is keyed by version; an unbumped version leaves stale code installed while every surface reports success — observed and initially misdiagnosed this session | installs actually taking effect | the host stops keying its cache by version |
| Enforcement is a **pre-commit hook** | platform limitation | github.com has no pre-receive at this tier; custom-pattern push protection needs paid Secret Protection | secrets never reaching git | the repo moves to GHES, or Secret Protection is purchased |
| Secret ruleset is **two-tier** | measured | the trees being migrated carry 14 LAN addresses across 8 distinct hosts; a single always-reject table blocks the migration's own commit | the private repo holding its own payload | a tier-2 class starts appearing in the public repo |
| A skill lives in exactly one repo | policy (owner) | no synchronization authority exists between the two repos | divergent copies with no authority | a generator gains a defensible sync direction |
| **Shared infra is a third repo (`skills-infra`)** | **implementation default — not measured, not platform-forced** | none external; chosen while closing a review finding, between "one shared repo" and "vendor into both" | one place to fix a packaging bug | **already fired — see reframe record** |

**Hard numeric limits.** 24/23 skills and 14 LAN addresses are measured. The
description budget deliberately asserts *no* number: the host does not publish
one, so C8 records a total as a human tripwire rather than inventing a
threshold. That is the rubric's requirement met by refusing the limit, not by
guessing it.

## Reframe gate

Implementation returns here when a revisit condition above fires, a new
component mainly preserves an implementation default, repeated fixes move
failure to the next internal boundary, or a proven predecessor satisfies the
supported caller with less machinery.

### Reframe status: `OPEN`

**Triggering evidence.** The `skills-infra` row is the only constraint in the
table whose provenance is an implementation default with no external evidence.
It was decided while closing round-1 finding B4, which asked whether the
topology was specified at all — the choice was framed as *one shared repo vs.
vendoring into both*, and a third option was never evaluated: the generator,
validator, templates and secret ruleset living in the **public repo**, which
already owns `scripts/validate-plugin-manifests.mjs`, consumed by the private
repo at a pinned version. Three review rounds verified the decision was
internally consistent and never asked whether the component should exist.

1. **What user-visible outcome is blocked?** None directly. The cost is a third
   repository to create, clone, pin, and keep in sync on every machine — carried
   permanently by a single-owner setup, to serve exactly two consumers.
2. **Which constraint creates the blocker, and where did it come from?** "Shared
   infrastructure needs its own repository." It came from framing the question
   as one-repo-vs-vendoring; neither option was "the existing owner already
   lives somewhere".
3. **What concrete invariant fails if the constraint changes?** Examined:
   invariant 6 governs *skills*, and infra is not a skill; the public repo
   already carries the validator, so the reuse contract's "fix once" is
   satisfied by any single home. The secret **ruleset** would become public, but
   it is a set of generic shapes (`access_code` proximity, hex `tag_uid`,
   `*.ts.net`), not secrets — treating pattern definitions as sensitive is
   security through obscurity. **No hard invariant appears to fail.**
4. **What is the simplest design without that constraint?** Two repos. Infra
   lives beside the validator it extends in the public repo; `skills-private`
   consumes it pinned. One fewer repo, clone, and pin relationship, and the
   "fix once" property is unchanged.
5. **Which option has fewer trusted components and maintenance surfaces?** The
   two-repo option, plainly.

**What would keep the third repo:** a concrete incompatibility not yet named —
e.g. the public repo's release cadence making a pinned consumer unworkable, or
a requirement that infra be installable independently of either skill set.
Neither is currently claimed.

This record is `OPEN`, so implementation does not start. Closing it requires a
revised work order and its design review, not an author statement that the
concern is resolved.

## Reuse contract

**Reused as-is.** The public repo's five-manifest layout is proven across all
three CLIs and is not redesigned:

```
.claude-plugin/plugin.json        explicit skill allowlist  (Claude Code)
.claude-plugin/marketplace.json   marketplace registration  (Claude Code)
plugin.json                       explicit skill allowlist  (Copilot CLI)
.codex-plugin/plugin.json         "skills": "./skills/"     (Codex)
.agents/plugins/marketplace.json  marketplace registration  (Copilot CLI)
```

Two allowlists exist rather than one because they legitimately differ: the
public repo lists 24 skills for Claude and 23 for Copilot, excluding
`rubber-duck` from Copilot which ships it as a built-in agent. Any shared
generator must preserve per-host exclusions, not collapse them.

**Reused with modification.** `scripts/validate-plugin-manifests.mjs` already
reads all five manifests and cross-checks name, version, description, source and
policy. It hardcodes the string `dfrysinger-skills`, which is precisely why it
cannot serve a second repo unchanged. Parameterizing that is the whole of the
"fix once" requirement — a rewrite is not justified.

**New, and why.** A generator is required rather than convenient because the
alternative is hand-maintaining five manifests in two repos, where the failure
mode is silent: a version left unbumped does not error, it just stops the
plugin cache refreshing, which this session observed and initially misdiagnosed
as a stale marketplace.

**Topology — under an `OPEN` reframe record; see the reframe gate above.** As
written, the shared infrastructure lives in **one repository,
`dfrysinger/skills-infra`**, consumed by both skill repos at a pinned version.
Vendoring a `scripts/` subtree into each repo is **rejected**: two copies with
no synchronization authority reintroduce exactly the two-place maintenance the
objective exists to remove, and the drift would be silent. The consuming repos
record the infra version they were generated with, so drift is detectable.

## Affected data flow

```
dfrysinger/skills-infra  (templates + generator + validator + secret ruleset)
   |  consumed at a pinned version by
   +--> dfrysinger/skills          (public, general)   --> 3 CLIs
   +--> dfrysinger/skills-private  (private, domain)   --> 3 CLIs
```

Existing connection points touched:

- `~/.claude/settings.json` → `extraKnownMarketplaces`, `enabledPlugins`
- `~/.claude/plugins/marketplaces/<name>/` → the CLI's own clone
- `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` → the installed
  copy, **keyed by version**
- `~/.copilot/installed-plugins/_direct/` → Copilot's install
- `~/.claude/skills/` → source of the skills being moved

## Failure model

How this breaks in production, not in theory.

**Version not bumped, cache never refreshes.** `marketplace update` refreshes
the clone but not the installed copy; the cache is keyed by version, so an
unchanged version leaves the old code installed while every surface reports
success. Observed this session. The generator must bump the version on every
manifest emission.

**Version bumped but the install does not take.** The mirror of the above, and
worse because it looks correct: the generator bumps, the marketplace updates,
and `plugin update` still leaves the old cache directory resolving. Only the
cache path shows it.

**Repo created public.** `gh repo create` defaults vary by flag order and
config. A single wrong invocation publishes the owner's home infrastructure.

**Secret committed.** Skills carry example payloads, access codes, device IDs
and serials. A transcript in this session contained a live access code.

**Gate exists but is never invoked.** A scan script that must be remembered is a
report. This is why enforcement points are named rather than the tool alone.

**Per-host exclusion lost.** A generator that writes one skill list to all
manifests silently re-adds `rubber-duck` to Copilot, shadowing its built-in.

**Skill duplicated rather than moved.** A copy left in the public repo means two
divergent versions and an ambiguous authority, which is the condition this whole
change exists to end.

**Generator drifts from consumers.** Templates change; a repo that has not
regenerated ships manifests the validator rejects — or worse, accepts.

**Auth is per-machine.** Private install works here because `gh` is
authenticated with `repo` scope and a credential helper. A second machine
without that fails at clone with a confusing error rather than a permissions
message.

**Both plugins enabled, description budget exceeded.** Descriptions compete for
one budget; adding a second plugin can silently blank the tail of another's
descriptions, disabling autonomous triggering while leaving skills invocable by
name. The blanked skills are whichever fall at the tail — realistically the
*other* plugin's, not the newly added ones.

## Hard invariants

1. `dfrysinger/skills-private` is private at creation and re-asserted private on
   every manifest emission.
2. No secret of a class listed above, in the tier that applies to that repo's
   declared visibility, is committed. Enforcement on every machine that pushes
   is a commit rejection, not a report; the remote-side scan is a report and
   does not satisfy this invariant on its own.
3. Every manifest emission bumps the plugin version.
4. All five manifests agree on name, version and description within a repo.
5. Per-host skill exclusions survive generation.
6. A skill exists in exactly one repo — never both.
7. The public repo's behaviour is unchanged by adopting the generator: its five
   manifests before and after differ only in version.
8. The installed cache resolves the version the generator last emitted.

## Acceptance criteria

Each is observable.

- **A1** `gh repo view dfrysinger/skills-private --json visibility` returns
  `PRIVATE`, and a generator run against a private-declared repo with a failing
  or absent visibility assertion aborts non-zero.
- **A2** `claude plugin marketplace add dfrysinger/skills-private` succeeds and
  `claude plugin install` reports the plugin installed.
- **A3** After `/reload-plugins`, **every** skill from both enabled plugins has
  a non-empty description. The total description size is recorded in the run
  output as a tripwire; no threshold is asserted, because the host publishes no
  budget value.
- **A4** `~/.claude/skills/bambu-printing` and `~/.claude/skills/bambuddy` no
  longer exist, and the skills still resolve from the plugin.
- **A5** The validator passes in both repos, invoked with the repo's own plugin
  name rather than a hardcoded one.
- **A6** Regenerating the public repo's manifests produces a diff in which every
  added or removed line is a `"version":` line.
- **A7** The Copilot manifest of the public repo still omits `rubber-duck`;
  the Claude manifest still includes it.
- **A8** For **each** secret class in the tier applying to that repo, `git
  commit` of a tree containing a planted token of that class is rejected.
- **A8b** On a fresh clone, the bootstrap step is what makes A8 hold: before it
  runs the planted commit succeeds, after it runs the same commit is rejected.
- **A13** The unmodified `bambu-printing` and `bambuddy` trees commit
  successfully into `skills-private`, and the same trees are rejected when
  scanned under the public repo's tier set.
- **A9** Two successive generator emissions produce different versions.
- **A10** After `marketplace update` + `plugin update`, the installed cache
  contains a directory named for the newly emitted version, and the previously
  installed version is no longer the one resolved.
- **A11** The intersection of the two repos' `skills/` directory names is empty.
- **A12** A generator run against a **public**-declared repo completes without
  requiring a visibility assertion.

## Check contract

| # | Protects | Exercised by | Pass / fail signal | Why the failure proves the contract |
|---|---|---|---|---|
| C1a | A1, invariant 1 | Query visibility at creation, before any content | non-zero unless `PRIVATE` | A public repo is the disclosure failure itself, so the check must precede content |
| C1b | A1, invariant 1 | Run the generator with the visibility assertion stubbed to fail | emission aborts non-zero | Proves the repeated assertion is load-bearing, not decorative; a one-time check cannot support an ongoing property |
| C1c | A12 | Run the generator against the public repo config | completes, no assertion required | Proves the rule does not block the public repo the same tooling serves |
| C2 | A8, invariant 2 | Attempt `git commit` on a tree carrying one planted token of **every** class in the secret table, one class at a time | commit rejected each time, naming file and line | A gate that catches one class while the repo carries five is a report; the planted classes are the artefacts these skills actually contain |
| C2b | A8b bootstrap | On a fresh clone, run the bootstrap step, then attempt to commit a planted tier-1 token | commit rejected after bootstrap; the bootstrap step is what installs the hook | Prevention on a second machine is the bootstrap, not the remote; this proves cloning alone is insufficient and the step closes it |
| C2c | A13 migration | Commit the unmodified `bambu-printing` and `bambuddy` trees into `skills-private`; then run the public repo's tier set over the same trees | private commit succeeds; public ruleset rejects, naming the LAN addresses | Proves the two tiers are actually distinct — a single always-reject table blocks migration step 4, and a single never-reject table publishes the network map |
| C3 | A5, invariant 4 | Run the validator in each repo | non-zero listing the mismatched field | Cross-manifest drift is silent at install time and only surfaces as a host not seeing a skill |
| C4 | A7, invariant 5 | Assert the Copilot list excludes `rubber-duck` and the Claude list includes it | non-zero naming the manifest | A collapsed list shadows a host built-in, which presents as the wrong agent answering |
| C5 | A6, invariant 7 | Regenerate public manifests, then `git diff -U0` over the five manifest paths | fails if any added or removed line is not a `"version":` line | `--stat` carries no line content and cannot evaluate this; a reordered key or dropped description would pass |
| C6 | A9, invariant 3 | Emit twice, compare versions | fails if equal | Generator-side half of the version contract |
| C7 | A10, invariant 8 | Plant a version-distinguishing marker line in a skill body before emission. After `marketplace update` + `plugin update` + `/reload-plugins`, invoke that skill and read the marker back | fails unless the cache holds a directory named for the new version **and** the marker returned is the new one | Directory existence is observable by listing, but resolution is not: a stale and a new cache directory coexist, so an `ls`-only check passes in exactly the failing case. The marker is the only signal that names which copy the host actually loaded |
| C8 | A3 | Enumerate every skill from both plugins after reload; sum description bytes | fails if any description is empty; **records** the total as a tripwire | Sampling two skills cannot see another plugin's blanked tail, which is where the budget failure actually lands. The host does not publish its budget, so the recorded total is a human tripwire and deliberately not a gate — an empty description is the only machine-checkable signal, and it fires only after the overflow. See the follow-up below |
| C9 | A11, invariant 6 | Compare `skills/` directory listings across both repos | fails if the intersection is non-empty | A duplicated skill produces two divergent versions with no authority |
| C10 | A2, A4 | Install, reload, then invoke each moved skill by name | fails if the skill does not load | End-to-end proof the move did not strand the skills |

Preference order applied: C1a–C1c, C2b, C9 are state assertions because the
invariants are about facts. C2, C5–C7 are behavioural checks over the generator
and installer. C8, C10 are the live proof that distribution works.

### Guards required before implementation

**C2, the secret gate, including its ruleset and the secret-class table.** It
must exist, be installed as a commit-rejecting hook, and be proven to reject
every listed class *before* any personal skill content is committed — a secret
in git history is not removed by deleting it.

**C1a.** Visibility must be asserted before the repository receives content.

Every other check is written alongside the work.

## Migration

1. Create `skills-infra`; build the generator, validator and secret ruleset.
   Prove C5 and C6 against the public repo without adopting yet.
2. Create `skills-private` with an explicit private flag; prove C1a.
3. Install the pre-commit hook and the post-push detection workflow; prove C2
   with planted tokens of every tier-1 class, and C2b by running the bootstrap
   on a fresh clone.
4. Move `bambu-printing` and `bambuddy` in, preserving git history if practical.
   Prove C9, and C2c — that these trees commit here and would be rejected under
   the public tier set. If C2c's private half fails, the tier split is wrong;
   fix the ruleset rather than exempting files, since a per-file exemption is
   how the network map reaches the public repo later.
5. Plant C7's version marker in a skill body, then generate manifests; run C3,
   C4, C1b, C1c. The marker must go in before emission, or C7 has nothing to
   read back.
6. Install on this machine; run C7, C8, C10. Take a tarball of the two skill
   directories, then delete `~/.claude/skills/bambu-printing` and
   `~/.claude/skills/bambuddy`.
7. Adopt the generator in the public repo; prove C5 again post-adoption.

Step 6 deletes only after its own checks pass and a tarball exists, so a failed
install leaves recovery independent of the private repo.

## Definition of Done — private-skills-plugin

- The reframe status is `CLEAR`, with the evidence that closed it. It is
  currently `OPEN`, so implementation has not started.
- All **14** acceptance criteria pass: A1–A8, A8b, A9–A13. Enumerated rather
  than given as a range, because a range silently drops any criterion added
  out of sequence — A8b and A13 both were, and A13 is the only criterion
  proving the two-tier secret split is actually two-tiered.
- All **14** checks exist — C1a, C1b, C1c, C2, C2b, C2c, C3–C10 — and have been
  observed failing for the right reason at least
  once, not merely passing.
- The validator and generator take the plugin name and declared visibility as
  input; no repo name is hardcoded in shared code.
- Both repos regenerate their manifests from `skills-infra` at a pinned version,
  and each records the infra version it used.
- `bambu-printing` and `bambuddy` load from the private plugin on this machine,
  their local copies are deleted, and a pre-delete tarball exists.
- The public repo's five manifests differ from their pre-adoption state only in
  version.
- This document is committed alongside the code it governs.

## Open questions for the implementer

- **Second-machine bootstrap.** `gh auth login` with `repo` scope plus hook
  installation is required before a second machine can consume or contribute.
  Whether that is scripted or documented is the implementer's call, but it is
  **load-bearing, not optional**: since github.com cannot reject a push before
  accepting it at this tier, the bootstrap is the only prevention invariant 2
  has on a machine other than this one. A8b/C2b make it checkable. Prefer
  scripting it — a documented step that is skipped leaves no signal until the
  secret is already in remote history.
- **Description budget.** C8 records a total with nothing to compare it
  against, because the host publishes no budget value. If a figure is ever
  established empirically — by adding skills until a tail blanks, then
  bisecting — C8 should gain a headroom threshold and become a real gate.
  Recorded as follow-up, not blocking: the empty-description check catches the
  failure, just later than is comfortable.
