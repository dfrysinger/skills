---
name: autonomous-github-actions
description: Guardrails for agent-initiated, externally-visible GitHub writes — filing issues, opening pull requests, posting comments, and pushing to repos the user does not own. Use when about to create or mutate anything visible to other people on GitHub (especially upstream/third-party repos), or when an offered menu option bundles such an action.
author: skill-review
---

# autonomous-github-actions

Externally-visible GitHub writes are **not free background actions**. Filing an
issue, opening a PR, posting a comment, or pushing to a repo the user does not
own is visible to other people and is often hard to cleanly undo. Treat every
such action as requiring **explicit, specific user approval** — not implied
consent from a broad "go ahead."

## The rule

- **Do not file issues or open PRs against upstream / third-party repos without
  explicit permission.** "Fix this" or "work on the project" is NOT permission
  to contact an external project. Ask first, naming the exact repo and the exact
  text you would post.
- **Read menu/option boundaries carefully.** A common failure: the user picks
  option 1, but the externally-visible filing was bundled into option 3. Picking
  a different option is a decline of everything in the options you didn't pick.
  Never treat a side-effect in an unchosen option as authorized.
- **Distinguish the user's own repos from upstream.** Creating a tracking issue
  in the user's own repo to back an approved goal is usually in-scope; filing the
  same thing on `upstream/project` is a separate action that needs its own yes.
- **Clean up invalid artifacts you created.** If you filed an issue/PR that turns
  out to be wrong or unneeded, proactively offer to close it — don't leave noise
  in someone else's tracker.
- **Search for an existing report before filing.** A duplicate is noise you can't
  fully undo. Search broadly: PRs as well as issues, and beyond the one obvious
  public repo — projects often split frontend/backend, mirror trackers, or land
  the actual fix in a separate (sometimes private) implementation repo. Prefer an
  org-wide search where access permits (e.g. `gh search prs --owner <org> ...`,
  not just `gh search issues --repo <one-repo>`).

## When to use

- Before any `gh issue create`, `gh pr create`, `gh ... comment`, or push to a
  remote you don't own.
- When an offered action menu bundles an external filing into one of the options.
- Any time work "for a project" might spill into contacting that project's
  maintainers or repo.

## Checklist before an external GitHub write

1. Whose repo is this? (user-owned → usually fine; upstream/third-party → needs
   explicit yes.)
2. Is this a duplicate? Search PRs and issues, org-wide and across split/private
   implementation repos — not just the one obvious public repo.
3. Did the user approve *this specific* action, naming this repo? (A general
   "go" on the task is not enough for an external filing.)
4. Am I acting on a menu option the user actually selected — not a side effect
   bundled into one they declined?
5. Is it reversible, and do I have a cleanup plan if it turns out wrong?

If any answer is unclear, stop and ask, quoting the exact text you would post and
the exact target repo.

## Pitfalls

- **Treating an upstream filing as a background side effect.** It is a primary,
  visible action — surface it and get a yes.
- **Over-reading consent.** Approval to add a goal/feature is not approval to
  announce it to an external project.
- **Leaving invalid issues open.** If you filed something that was wrong, close
  the loop instead of moving on.
- **Filing a duplicate because you searched too narrowly.** The fix may already
  exist as a PR, or live in a different/private repo than where users file bugs.
  Search PRs (not only issues) and widen beyond the obvious public repo before
  filing.
- **Pushing a "harmless" follow-up untested.** Run the full test suite after
  every commit on the branch — including edits that look trivial, like a comment
  clarification — before pushing. "It looks harmless" is exactly how a green
  branch goes red on the remote.
