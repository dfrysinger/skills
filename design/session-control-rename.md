# Session-Control Rename

## Objective

Rename the shared SDK request extension from `session-inbox` to
`session-control` without loading duplicate extensions, splitting live state,
or orphaning existing local requests and receipts.

## User decision

The exact decision is recorded in
`design/self-compact-session-control-decisions.json`:

> im confused when you say session inbox, is that the extension name? its
> awfully specific to one feature and confusing

The user subsequently approved the `session-control` name.

## Lane

**Systemic.**

This changes a shared extension name, script paths, diagnostics, environment
names, default storage authority, and documentation used by mailbox,
unattended-run, handoff, rotation, reload, and self-compact callers. It does not
change their operation authority or delivery semantics.

## Non-goals

- Do not change send, autopilot, compact, reload, mailbox, or rotation
  behavior.
- Do not change immediate-delivery policy or add enqueue delivery.
- Do not rewrite historical receipts or logs.
- Do not load an old-name compatibility extension beside the renamed one.
- Do not make this rename a prerequisite or rollback dependency of
  self-compact interruption reliability.

## Constraint provenance

| Constraint | Provenance | Protects | Revisit condition |
|---|---|---|---|
| Product surfaces use `session-control` | Direct user product decision | Understandable shared-component naming | Revisit only on a later explicit naming decision |
| Existing local state remains usable | Current compatibility promise to installed mailbox, handoff, rotation, unattended-run, and self-compact callers | No lost pending work or receipts during upgrade | Revisit after the legacy root has had a separately approved retirement window |
| Only one extension instance loads | Existing generation and dedupe model | No duplicate claims or SDK sends | Revisit only if extension loading gains native aliases |
| Historical evidence is immutable | Existing receipt/proof discipline | Auditability and diagnosis | Never rewrite; retirement can only stop new writes |

## Reframe gate

**Status: CLEAR.**

The rename uses the existing extension and storage model. Return to design
before introducing a proxy extension, dual-running roots, receipt copier,
background migrator, or second request protocol.

## Reuse contract

Rename the current extension directory and update existing callers. Add one
shared storage-root resolver used by the extension and request-side tools:

1. `COPILOT_SESSION_CONTROL_DIR`, when explicitly set before an operation;
2. deprecated `COPILOT_SESSION_INBOX_DIR`, when explicitly set before an
   operation;
3. existing `~/.copilot/session-inbox`;
4. `~/.copilot/session-control`.

This is selection, not copying. A legacy default root wins until an explicit,
drained migration removes or renames it. One process uses one root.

## Affected consumers

- `extensions/session-inbox` extension, request CLI, reload helper,
  diagnostics, and tests;
- `extensions/mailbox-watcher`;
- `skills/mailbox`;
- `skills/unattended-run`;
- `skills/handoff`;
- `skills/rotate-session`;
- `skills/self-compact`;
- plugin manifest and marketplace packaging through extension-directory
  discovery;
- README, architecture invariants, and current design documents.

Historical design records retain old names when describing old versions. They
are not current product instructions and are excluded from the naming check.

## Invariants

1. Exactly one shared request extension loads under `session-control`.
2. Every process participating in one request selects the same root.
3. An explicit new environment variable wins over the deprecated alias.
4. An existing legacy default root remains authoritative even when a new
   default root also exists.
5. No automatic copy or merge combines two roots.
6. Current errors, diagnostics, usage text, and docs say `session-control`.
7. Compatibility references to `session-inbox` are labeled deprecated or
   historical.
8. Request fingerprints, dedupe keys, receipts, and target-generation
   semantics do not change.

## Acceptance criteria

1. A new installation creates and uses `~/.copilot/session-control`.
2. An installation with only `~/.copilot/session-inbox` continues using that
   root after upgrade and emits a deprecation diagnostic.
3. Explicit `COPILOT_SESSION_CONTROL_DIR` overrides every other root.
4. Explicit `COPILOT_SESSION_INBOX_DIR` still works and is labeled deprecated.
5. If both default roots exist with no explicit setting, the legacy root wins
   and no state is copied or merged.
6. Extension reload reports one healthy `session-control` and no
   `session-inbox`.
7. Mailbox, handoff, rotation, unattended-run, reload, and self-compact
   targeted tests pass with updated paths.
8. A repository check finds no current product use of `session-inbox` outside
   compatibility and historical allowlists.

## Check contract

| Check | Setup | Passing signal | Failure proves |
|---|---|---|---|
| Root-selection table test | Exercise five precedence cases | Exactly one expected root selected | Upgrade can split shared state |
| Extension discovery test | Reload installed candidate | One healthy `session-control`, no old extension | Rename loads duplicates or disappears |
| Consumer path tests | Run targeted suites for all named consumers | Existing behavior passes unchanged | A caller still points at the old path |
| Naming check | Scan current product surfaces with explicit historical/compatibility exclusions | No unapproved old-name match | Users still encounter misleading naming |
| Live compatibility probe | Use an isolated legacy-only root, send one request, inspect receipt | Renamed extension claims and completes it | Upgrade orphans legacy state |
| Live-root transition test | Start with a legacy root containing a pending request and a live self-compact lock, then make the new root available and start another participant during the operation | Every participant, including the late participant, selects the legacy root; no state is orphaned or copied | Upgrade can split one operation across roots |

## Migration and rollback

Migration is path and root selection only; no data is moved.

The rename installation has a drain precondition:

- no pending or processing shared request;
- no live self-compact verifier;
- no self-compact lock in `publishing` or any later state.

If a legacy default root exists, every process selects it regardless of whether
the new default root also exists. The resolver never creates, copies, merges,
or switches to the new root while the legacy root exists. After the drain
precondition passes, an operator may explicitly remove or rename the legacy
root; only then does the new default root become authoritative. An explicit
environment setting may select another root only before an operation starts;
it cannot move an operation already bound to a generation and root.

Rollback restores the old extension directory and caller paths. A machine that
has started using only the new default root must set
`COPILOT_SESSION_INBOX_DIR=~/.copilot/session-control` while running the old
version, or move that state in an explicit operator action. The rename commit
must document this rollback command.

## Definition of Done: Session-Control Rename

- The extension, callers, diagnostics, and current documentation use
  `session-control`.
- Root selection preserves legacy-only installations without dual-running or
  copying state.
- All named consumers pass targeted validation.
- One installed extension and one live root are verified.
- The rename is committed separately from reliability behavior and is not
  pushed unless the user requests publication.
