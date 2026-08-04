# Self-Compact v0.100 Live Proof

## Receipt status

**PASS.** The final one-row command candidate completed the marked compact,
continuation, draft restoration, and watcher teardown lifecycle.

## Candidate

- Worktree: `/Users/dfrysinger/code/skills-worktrees/self-compact-ambiguous-input-recovery`
- Branch: `dfrysinger/self-compact-ambiguous-input-recovery`
- Version: `0.100.0`
- Sierra pane: `%62`
- Sierra session state:
  `/Users/dfrysinger/.copilot/session-state/d9ed581f-96c6-54a2-b59d-fa33dfab4f2d`

## Final passing lifecycle

Run marker:
`SCM:6a71d3cc-03dca`

The final worktree candidate submitted this one-row command while
`SIERRA_V100B_DRAFT` was visible:

```text
/compact Keep: proof; Drop: output. Keep SCM:6a71d3cc-03dca
```

The detached watcher recorded:

```text
marked compact advanced summary_count to 9
submitted post-compact continuation after event line 699
```

Checkpoint `009-proving-v0-100c-compaction.md` contains the exact marker. One
`proceed` user event was recorded after compaction, the continuation turn ended,
and `SIERRA_V100B_DRAFT` returned unchanged in the editor without being
submitted. The run's `.ready`, `.armed`, and `.cancelled` files were removed.

## Prior passing lifecycle (discovery only)

Historical run marker:
`SELF_COMPACT_RUN_ID:20260804T105808Z-3615`

The worktree candidate submitted the marked compact with
`SIERRA_V100B_DRAFT` visible in the editor. The detached watcher recorded:

```text
marked compact advanced summary_count to 8
submitted post-compact continuation after event line 657
```

The marked checkpoint exists, one `proceed` user event was recorded, the
continuation turn ended, and `SIERRA_V100B_DRAFT` returned unchanged in the
editor without being submitted. The run's `.ready`, `.armed`, and `.cancelled`
files were removed after the watcher exited.

## Input-state checks

- A visible draft transitioned to empty with the `stashed` footer before
  compaction.
- A pre-stashed `SIERRA_V100B_DRAFT` was restored, re-stashed by the shared
  helper, and restored unchanged afterward.
- A single-line draft was cleared by Ctrl-U.
- In Copilot's multiline editor, Ctrl-U cleared only the current logical line.
  The candidate treats any remaining rows as nonempty and does not press Enter
  unless the helper command alone is reconstructed exactly.
- A long single-line command rendered over multiple visual rows. The
  reconstruction experiment made that run possible, but it is not accepted as
  safe final behavior because tmux cannot distinguish those rows from logical
  newlines.
- A locale-scrubbed watcher environment selected `C.UTF-8` and captured visible
  `proceed` as `70726f63656564`. The final probe additionally requires
  `locale charmap` to report UTF-8 and uses a multi-glyph divider.

## Redraw and geometry

With `SIERRA_V100B_DRAFT` visible, the one-column resize pulse preserved:

```text
geometry: 68x34 -> 68x34
window-size: manual/manual -> manual/manual
input: SIERRA_V100B_DRAFT -> SIERRA_V100B_DRAFT
```

The pane remained outside tmux modes and autopilot remained selected.

## Escape behavior

Sierra's existing bounded escape check ran `sleep 20`, received one Esc while
the tool was active, completed the shell command, and recorded the requested
`ESC_TEST_DONE` response. Autopilot remained selected.

## Discoveries from live proof

The live work exposed three failures and informed the final design:

1. Visual and logical row boundaries are indistinguishable. The final supported
   path uses concise `SCM:<epoch-hex>-<pid-hex>` syntax, printable-ASCII
   pane-width preflight, and exactly one captured prompt row at every
   ownership/Enter/cleanup gate. The prior reconstruction is discovery only.
2. Detached tmux shells may omit a UTF-8 locale, so helper initialization
   verifies an active UTF-8 charmap plus a realistic awk prompt/full-divider
   parse, exports it, or fails closed.
3. Renderer updates may lag key delivery, so verification polls stable captures
   for a bounded interval without sending another editor key.

The deterministic round-1 suite also proves C, POSIX, and bogus locales are
rejected with fallback advancement; transcript menu prose does not send Esc;
concrete nearby menu chrome controls the bounded first/second Esc behavior; and
a 68-column pane accepts exactly 31 steer columns while longer input fails
before watcher launch or editor mutation.
