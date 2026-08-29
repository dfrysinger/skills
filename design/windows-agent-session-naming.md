# Windows Copilot Agent Session Naming

## Objective

Give each Windows agent name such as `hotel` one stable Copilot session ID so
the agent can be created, resumed, displayed, and mailbox-routed by name without
tmux or ambiguous historical-name lookup.

## Non-goals

- Do not add a Windows terminal multiplexer, ConPTY host, detached daemon,
  named-pipe protocol, session registry file, or replacement session store.
- Do not change Copilot's workspace metadata, session-inbox heartbeat schema,
  mailbox address format, or request ownership model.
- Do not call the experimental `session.rpc.name.set()` API.
- Do not infer `COPILOT_AGENT_MACHINE` from the Windows hostname.
- Do not synchronize local Copilot session state through OneDrive.
- Do not support the deprecated `--config-dir`; callers configure the session
  store through `COPILOT_HOME`.
- Do not create a Windows Agent Stack UI, pane manager, or agent process
  supervisor.
- Do not repair or rename historical sessions that were created outside this
  launcher.

## Lane

**Systemic.** The launcher defines a stable mapping from a public human agent
name and machine label to Copilot's durable session ID. That mapping becomes a
versioned identity contract used across process restarts and therefore requires
design review, deterministic tests, migration behavior, and rollback.

## Observed failure and reframe history

The installed Copilot CLI already exposes:

```text
--name <name>       Set a name for a new session
--resume <value>    Resume by ID, ID prefix, task ID, or exact name
--session-id <id>   Resume an existing session or assign the UUID for a new one
```

A physical Windows probe created `hotel` successfully, persisted
`workspace.yaml` with `name: hotel`, and published a session-inbox heartbeat
with `sessionName: hotel`. A subsequent `--resume hotel` failed because many
historical sessions already had that name. Copilot listed every match and
required an exact session ID.

The first design proposed an extension bootstrap through
`session.rpc.name.set()`. Native `--name` made that unnecessary. The second
design proposed direct name-based resume. The ambiguity probe proved that a
human-readable name alone is not a durable ownership key.

## Constraint provenance

| Constraint | Provenance | Protects | Revisit condition |
| --- | --- | --- | --- |
| Copilot's session ID remains the durable ownership key. | Native CLI behavior and existing session-inbox request ownership. | Exact resume and delivery without historical-name ambiguity. | Revisit only if Copilot provides a supported unique alias namespace. |
| Copilot's native `--name` remains the displayed and mailbox-routed label. | Native CLI contract plus existing `workspace.name` readers. | One readable name across CLI UI, heartbeat, and mailbox. | Revisit if Copilot replaces workspace names with another supported label. |
| One `(machine, agent-name)` pair maps deterministically to one UUID. | User outcome: repeatedly launch `hotel@surface-pro` as the same Windows agent. | Stable resume without a separate mapping file. | Revisit if the mapping needs explicit rotation or multiple parallel instances of one agent name become supported. |
| `COPILOT_AGENT_MACHINE` is explicit and required. | Existing cross-computer mailbox contract; no hostname fallback. | Prevents the same agent name on two computers from sharing a session ID accidentally. | Revisit if a repository-independent machine identity authority is added. |
| Agent names are canonical lowercase mailbox-safe names of 1-100 characters. | Existing mailbox validation, exact-case session-inbox routing, and Copilot's native 100-character session-name limit. | Prevents launcher/mailbox case disagreement and rejects values Copilot would reject only after child launch. | Revisit only with both a mailbox routing and native Copilot name-limit change. |
| Machine labels are canonical lowercase mailbox-safe names of 1-128 characters. | Existing mailbox validation and exact transport route names. | Keeps the deterministic session ID aligned with the configured qualified mailbox route. | Revisit only with a mailbox address grammar change. |
| The deterministic mapping algorithm and namespace are versioned constants. | Persistence compatibility requirement. | Prevents a refactor from silently creating a different session. | Revisit only through an explicit migration design. |
| Existing local-first mailbox roots remain binding. | `design/windows-cross-computer-mailbox-addressing.md`. | Keeps mutable state off OneDrive. | Revisit only through that design's reframe gate. |

No configurable numeric limit is introduced. UUID construction uses the first
128 bits of SHA-256 after setting RFC 4122 version and variant bits; collision
risk is bounded by the UUID space rather than a product limit.

## Reframe gate

Implementation returns here before adding another component if:

- Copilot does not resume reliably by the deterministic `--session-id`;
- `--session-id` plus `--name` cannot create a new named session;
- detecting whether the deterministic ID already exists would require a
  network service, shared lock, or second registry;
- machine labels cannot be guaranteed stable; or
- Copilot adds a supported unique startup alias that removes the mapping.

**Status: CLEAR.** A live Windows probe proved `--session-id=<new UUID>` plus
`--name=<name>` creates the requested native session. Repeating both flags
against the existing ID fails explicitly because `--name` is new-session-only,
which defines the required local existence branch. The existing local session
directory provides that branch without creating another state owner.

## Reuse contract

- Copilot CLI remains the only session creator, metadata writer, session store,
  and resume implementation.
- `<copilot-home>/session-state/<session-id>/workspace.yaml` is used only as
  the local existence signal already owned by Copilot. `copilot-home` is the
  non-empty `COPILOT_HOME` value when set and the current user's
  `~/.copilot` directory otherwise. The launcher never edits it.
- `extensions/session-inbox/session-identity.mjs` continues to read the native
  name from `workspace.name`.
- `extensions/session-inbox/request.mjs` continues to resolve one fresh name to
  an exact session ID and generation; duplicate live names still fail closed.
- `extensions/mailbox-watcher/extension.mjs` continues to watch the mailbox
  matching the native name.
- `COPILOT_AGENT_MACHINE` continues to qualify remote mailbox addresses.

The only new executable is a PowerShell launcher. It has no writable state.

## Stable session ID contract

The launcher:

1. validates mode (`new` or `resume`);
2. requires the agent name to match
   `^[a-z0-9][a-z0-9._-]{0,99}$`;
3. requires the explicit machine label to match
   `^[a-z0-9][a-z0-9._-]{0,127}$`;
4. rejects extra arguments that could replace the wrapper-owned identity or
   session store:
   - any token matching
     `^--(?:name|resume|session-id|config-dir)(?:=|$)`;
   - any short token beginning with `-n` or `-r`, including attached values
     such as `-nHOTEL`;
5. resolves Copilot home from non-empty `COPILOT_HOME`, otherwise
   `~/.copilot`;
6. hashes this UTF-8 payload with SHA-256:

   ```text
   dfrysinger-skills/windows-agent-session/v1\0<machine>\0<agent-name>
   ```

7. takes the first sixteen hash bytes;
8. sets UUID version bits to `5` and RFC 4122 variant bits to `10`;
9. formats the bytes as a canonical UUID string.

The validated lowercase values are already canonical, so neither the launcher
nor downstream routing performs a hidden case conversion. The version nibble
describes a deterministic name-derived UUID contract. SHA-256 is used rather
than SHA-1, but the UUID-shaped result remains accepted by Copilot's
`--session-id` validation. The namespace string is immutable for v1.

## Launch behavior

```powershell
copilot-agent.ps1 new hotel
copilot-agent.ps1 resume hotel
```

### New

- Refuse when
  `<copilot-home>/session-state/<derived-id>/workspace.yaml` already
  exists.
- Invoke with the validated canonical name:

  ```text
  copilot --session-id=<derived-id> --name=<canonical-name> <extra args>
  ```

### Resume

- Refuse when the deterministic local workspace under `copilot-home` does not
  exist. This prevents Copilot from treating an unknown `--session-id` as a new
  unnamed session.
- Invoke:

  ```text
  copilot --session-id=<derived-id> <extra args>
  ```

The wrapper passes an argument array directly and never constructs or evaluates
a command string.

## Failure model

- Missing, mixed-case, over-length, or otherwise invalid machine/name fails
  before Copilot starts.
- Empty `COPILOT_HOME` is treated as unset. Relative or invalid
  `COPILOT_HOME` values fail before Copilot starts rather than probing a
  different store from the child.
- Wrapper-owned identity flags and deprecated `--config-dir` fail before
  Copilot starts.
- `new` against an existing deterministic ID fails and directs the caller to
  `resume`.
- `resume` without local workspace state fails rather than creating an unnamed
  session.
- If local state was deleted while a synchronized remote session still exists,
  the launcher stays fail closed; recovering remote-only sessions is outside
  this change.
- A failed first Copilot launch may leave a partial native session directory.
  The next `new` refuses it; the user may inspect or remove that failed native
  session before retrying.
- Two simultaneously launched `new` processes may race before Copilot creates
  the directory. Copilot's exact session-ID ownership is the final arbiter; at
  most one valid session may own that UUID, and either process failure is
  surfaced.
- Two live processes resuming the same exact session ID are governed by
  Copilot's native session ownership behavior. The launcher does not add a
  competing lock.
- Duplicate historical display names do not affect resume because the launcher
  never resolves by name.

## Hard invariants

1. One canonical `(machine, name, mapping-version)` tuple always yields one
   UUID.
2. Mixed-case inputs are rejected rather than creating a second external
   identity that exact-case mailbox routing cannot reach.
3. Changing machine or name changes the UUID.
4. The launcher never writes Copilot workspace metadata or a mapping registry.
5. `new` always supplies both exact session ID and native name.
6. `resume` always supplies the exact session ID and never relies on name
   lookup.
7. An unknown resume target cannot create an unnamed session.
8. The existence probe and child always use the same Copilot home.
9. Extra arguments cannot replace wrapper-owned session identity or storage
   location.
10. Session ID plus extension generation remains mailbox request ownership.
11. Duplicate live display names continue to fail closed in session-inbox.
12. Naming reads and writes no OneDrive path.

## Acceptance criteria

1. Deterministic test vectors produce stable UUIDs across PowerShell processes.
2. Mixed-case input is rejected before child launch; another canonical machine
   or name derives a different UUID.
3. `new hotel` creates a native workspace whose ID is the derived UUID and
   whose name is `hotel`.
4. `resume hotel` loads the same session ID despite other historical sessions
   named `hotel`.
5. The live session-inbox heartbeat reports `sessionName=hotel`, the derived
   session ID, and one exact generation.
6. A mailbox/session-inbox request targeting live `hotel` reaches that exact
   session once.
7. Invalid input, duplicate `new`, and missing-state `resume` fail before
   launching a child.
8. Non-reserved extra arguments including spaces pass through without command
   evaluation; reserved identity and config-store flags are rejected.
9. Existing duplicate-live-name refusal remains unchanged.
10. Local-first mailbox validation proves local unqualified delivery, one
    qualified import, byte-identical remote acknowledgement plus receipt, and
    offline outbox retry on Windows.
11. Default and explicit `COPILOT_HOME` each select the same workspace path for
    the existence probe and the Copilot child.

## Migration and rollback

Existing sessions are not migrated automatically. For each long-lived Windows
agent, create the deterministic session once with `new`. Historical sessions
with the same display name remain accessible by their old IDs but do not affect
the launcher.

Rollback removes the wrapper and documentation. Native sessions remain valid
and can be resumed directly by the derived ID. The deterministic namespace and
algorithm must not be reused for a different mapping.

## Check contract

| Check | Protects | Setup and transition | Pass signal | Failure meaning |
| --- | --- | --- | --- | --- |
| PowerShell deterministic vectors | Stable identity contract. | Derive multiple canonical names and machines in fresh processes. | Exact frozen UUID vectors and required not-equal relations. | A refactor would strand existing named sessions. |
| Wrapper fake-child tests | Validation, mode mapping, storage alignment, and quoting. | Put a capture executable named `copilot` first on PATH and isolate both the default home and an explicit `COPILOT_HOME`. | Exact argv and workspace probes; 100-character agent names succeed; mixed-case, 101-character agent names, long reserved forms, `--flag=value`, `-nHOTEL`, and other invalid inputs make no child call. | Wrapper can create wrong, unroutable, unnamed, or unresumable sessions. |
| Native `new` proof | CLI creation contract. | Launch a unique agent through the wrapper. | Workspace ID equals derived ID and native name equals the canonical input. | CLI behavior does not support the mapping. |
| Native `resume` proof | Ambiguity-free persistence. | Add or retain unrelated historical sessions with the same display name, then resume through wrapper. | Same derived ID loads successfully. | Wrapper still depends on ambiguous name lookup. |
| Heartbeat and mailbox proof | End-to-end coordination identity. | Keep the resumed agent live and send one local envelope. | One heartbeat and one native turn identify the derived session. | Native naming did not reach routing. |
| Existing focused suite | No session-inbox/mailbox regression. | Run repository Node and shell tests on Windows. | Current expected pass/skip baseline remains. | Packaging or docs movement broke existing behavior. |
| Local-first physical proof | Windows 0.108.17+ ownership contract. | Exercise local, qualified import/ack receipt, and offline outbox flows. | Mutable state stays local and remote transport bytes remain unchanged. | Windows remains on obsolete shared mutable roots. |

## Definition of Done: Windows deterministic agent naming

- The reviewed deterministic mapping, PowerShell wrapper, documentation, and
  tests are committed.
- A real Windows `hotel` session is created and resumed by the derived exact
  session ID despite historical name duplicates.
- Its heartbeat and one mailbox delivery use `hotel` and that exact ID.
- Existing mailbox/session-inbox tests pass on Windows.
- The installed plugin and user environment use mailbox 0.108.18 local-first
  configuration with no OneDrive-backed local or state path.
- Local unqualified delivery, qualified import exactly once, immutable remote
  acknowledgement plus receipt, and offline outbox retry pass on Windows.
- Dual implementation review has no material finding.
- The change is merged through the normal pull-request flow.
- `whisky@macbook-pro` receives the exact commit/version, configuration,
  deterministic and live results, and PR URL.
- Both pending `hotel@surface-pro` handoffs are acknowledged after completion.
