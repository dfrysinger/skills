---
name: git-history-recovery
description: Recover lost or displaced Git work after accidental reset, checkout, rebase, stash, or branch mistakes by using reflog, dangling commits, and targeted restore. Use when uncommitted or recently committed changes appear lost and the goal is safe recovery without rewriting unrelated history.
author: skill-review
---

# git-history-recovery

Recover Git work that appears lost after commands such as `git reset --hard`, checkout, rebase, stash, or branch changes. This skill focuses on finding recoverable objects and restoring selected paths safely; it does not rewrite shared history or guess at unrelated changes.

## When to use

- A destructive Git command appears to have removed local work.
- Changes landed in an unexpected commit, branch, stash, or detached HEAD.
- You need to recover specific files from reflog or dangling objects without disturbing current unrelated work.
- Work vanished while **another agent shared the same working tree**, or while the repo lived in a **file-syncing folder** (Dropbox/iCloud) — see the prevention pitfall below; uncommitted changes clobbered this way may not be recoverable from Git at all.

## Prerequisites

- A Git repository containing the lost work or its object database.
- Use `bash` for Git commands and `view` to inspect known files after restore.

## Quick start

```bash
git --no-pager status --short
git --no-pager reflog --date=iso
git fsck --lost-found --no-reflogs 2>/dev/null
git --no-pager show --stat <candidate-sha>
git restore --source=<candidate-sha> --worktree -- <path>...
```

## Procedure

1. **Freeze the scene.** Stop running destructive Git commands. Capture `git status --short`, current branch, and the command that caused the loss.
2. **Check obvious holding areas first.** Inspect `git stash list`, the current branch log, and nearby branches if the work may have been committed or stashed rather than deleted.
3. **Search the reflog.** Use `git --no-pager reflog --date=iso` to find pre-reset, pre-rebase, or detached-HEAD entries. Inspect likely SHAs with `git --no-pager show --stat <sha>` and, if needed, `git --no-pager diff <sha>^ <sha> -- <path>`.
4. **Search dangling commits when reflog is unclear.** Run `git fsck --lost-found --no-reflogs` and inspect dangling commits with `git --no-pager show --stat <sha>`. This often finds work swept away by an accidental reset or orphaned test commit.
5. **Restore narrowly, and never over live work.** `git restore --worktree`
   overwrites the working copy of every path it touches, so recovering one loss
   can cause another. Check the target paths first and preserve anything already
   there:
   ```sh
   git --no-pager status --short -- <path>...          # empty means safe to restore
   git stash push -m "pre-recovery" -- <path>...       # only if that output was NOT empty
   git restore --source=<sha> --worktree -- <path>...
   ```
   Read the stashed work back with `git --no-pager stash show -p stash@{0}`
   rather than `git stash pop`: popping tries to merge it over the file you just
   restored and will conflict. The stash survives that, so nothing is lost. Avoid `git reset --hard <sha>` unless the whole repository state
   should move — it discards every uncommitted change in the tree, not just the
   paths you named.
6. **Verify before committing.** Review `git status --short` and diffs for the restored paths. Commit the recovered work incrementally so another hard reset cannot sweep it away again.

## Pitfalls

- **Repeating the destructive command.** Do not run cleanup, reset, or checkout commands while searching; every new operation can make the recovery trail harder to reason about.
- **Restoring the whole tree when only paths are needed.** `git restore --source=<sha> --worktree -- <path>` is safer than moving HEAD or resetting the index.
- **Ignoring sibling commits.** Lost work may have been captured in an accidental nearby commit; inspect recent reflog entries and dangling commits before assuming it is gone.
- **Forgetting to commit recovered work.** Recovery is not durable until the restored files are committed or otherwise intentionally saved.

## Prevention: concurrent agents and file-syncing folders

A whole class of "lost work" is not a bad Git command at all — it is **two
writers racing on one working tree**. Two common causes seen together:

- **Multiple agents sharing one clone.** A second agent's `git stash`,
  `checkout`, or `pull --ff-only` silently moves or shelves the first agent's
  tracked changes (look for `pre-rename WIP` / `preserved for other session`
  stash entries and foreign reflog `checkout` lines as the fingerprint).
- **The repo lives in Dropbox/iCloud.** The sync daemon rewrites files under the
  agent mid-edit, and uncommitted changes can be overwritten with no Git record
  to recover from.

Mitigations (prefer prevention — these losses often can't be reflog-recovered):

1. Give each concurrent agent its **own clone or `git worktree`**, never a shared
   working tree.
2. Keep the active clone **outside** synced folders (e.g. `~/code/<repo>`, not
   `~/Dropbox/...`).
3. **Commit early and often** so work lands in the object database, where the
   recovery procedure above can actually reach it.

## Verification

- `git status --short` shows only the intended recovered paths.
- `git --no-pager diff -- <path>...` matches the expected recovered work.
- A new recovery commit or intentional stash exists before further risky Git operations.
