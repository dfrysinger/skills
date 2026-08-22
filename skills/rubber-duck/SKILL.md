---
name: rubber-duck
description: Rubber-duck a plan, trace, or implementation past a model from a different family and get a second opinion back. Use when a bounded solution is ambiguous, a failure will not surface, the first instance of a new idiom needs confirming, repeated variations keep failing, or a reversible decision would otherwise go to the user. Reach for it whenever another skill calls for a rubber-duck pass; on Copilot CLI it defers to the built-in agent.
---

# rubber-duck

Explaining a problem aloud finds the flaw. Explaining it to **a different model
family** finds the flaw your own family is biased to miss — that is the whole
delta over talking to yourself, and the reason the listener must not be the
model already driving the session.

One pass, advisory only. The duck reads and reasons; it never edits, builds,
tests, or lands. You decide what to do with what comes back.

## Host

Copilot CLI ships this as a built-in agent, so use that and stop here. The rows
below exist because other hosts have no built-in, and the skills in this
library call for a rubber-duck pass regardless of where they run.

| Host | Reach a different family by |
|---|---|
| Copilot CLI | the built-in rubber duck agent |
| Claude Code | `codex exec -m <gpt-model> --sandbox read-only --skip-git-repo-check` |
| Codex CLI | `claude -p --model <opus-model>` |

Model identifiers move between generations. Resolve the current full,
non-mini, non-codex model at session start rather than trusting an example.
`dual-review` carries the same transport table; when both run in one session,
resolve the models once.

Read-only is not a formality here. The duck's value is an outside view of work
it did not write, and a listener that starts editing the tree stops being a
listener. Where the transport offers a read-only sandbox, use it, so the
boundary holds mechanically rather than by instruction.

## What to send

Send the smallest packet that lets an outsider judge the thing:

- the decision, plan, trace, or diff in question;
- what you are trying to achieve, and what is explicitly out of scope;
- what you already tried and what it did;
- the specific question you want answered.

A duck given the whole repository returns generalities. A duck given one
ambiguous decision and its constraints returns an opinion you can act on.

Ask for blind spots, design flaws, and substantive issues. Ask it to say
plainly when it would choose differently and why — a duck that only validates
is a duck you did not need.

## What comes back

Feedback is evidence, not instruction. Take the parts that survive your own
check of the code, and say so when you set a point aside; an unexamined "the
duck said so" is how a second opinion becomes an unreviewed edit.

One pass is the norm. Reaching for a second round on the same question usually
means the packet was unclear rather than the answer, so sharpen the question
before spending another pass.

## Boundary with dual-review

Reach for the duck to **make a decision**; reach for `dual-review` to **land a
change**.

The duck is one advisory pass on a question still open. `dual-review` is two
reviewers, adjudication, and a bounded round budget over a change that already
works, and it owns the landing gate. A duck pass never satisfies that gate, and
a change that only needs a second opinion never needs the full protocol.

Skills that offer both name their own threshold — `guardrails` sets one for
amending an invariant. Follow the calling skill's rule rather than a copy of it
kept here.
