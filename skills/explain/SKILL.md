---
name: explain
description: Explain work to someone who steers it but never reads the code. Use proactively before summarizing what you built, finished, or found; before presenting options or a recommendation; when handing off or catching someone up on a project; whenever the user asks you to explain, teach, or walk through something; and when asking the user a clarifying question.
author: skill-review
---

# explain

The reader steers this work but never reads the code. They run several projects
at once through parallel agents and see all of it second hand. They are the
architect and the product owner, so they need an accurate picture of the whole
system in their head — accurate enough to notice when one agent rebuilds what
another already shipped, or invents a solution that should have been built on
work that exists.

They read to stay current on how the system works and to **catch** what is
going wrong before anything is built on it: a solution fitted too tightly to
today's problem, a quick fix standing in for the right one, a design that will
strain at ten times the size. This explanation is their review surface, so a
bad pattern has to be as obvious here as it would be in the diff, and a
weakness goes in as soon as it is known and stays in every retelling.
Explaining this way is the default, not a mode the reader requests.

**Simple words, full detail.** These pull in the same direction, not opposite
ones. The detail belongs in what you describe — the pieces, the order, the
choice you made — not in the vocabulary you describe it with. Write so that
someone with no involvement in the project could follow the whole thing.

Assume no memory of the code, the design, or the decisions — including their
own.

## The shape

**Open with the result or the "so what" in a sentence or two, then the shape
below it.** Inside each section, framing comes before the point.

**Scale it to the work.** A one-line fix, a version bump, or a contained
change earns a few sentences covering whichever points apply. Spend the full
shape on work that introduces a component, settles a decision, or sets a
pattern others will build on.

1. **Where we are** — the project, what it is for, and what this work was meant
   to achieve. Include it in your first report on this project in the current
   conversation, when a task finishes, or when the reader's own message does
   not establish which project they mean; skip it when the turns just before
   this one were already about this work.
2. **What changed** — what now exists or behaves differently that did not
   before.
3. **How it is built** — the architecture in detail: the pieces, what each one
   owns, how they connect, what happens in what order, and which existing parts
   of the system it builds on. This is where the detail budget goes.
4. **Where it is weak** — say each of these plainly and unprompted, since the
   reader has no other way to find them:
   - **Whether it duplicates something.** For anything introducing a component
     or a pattern, look for existing work that could have carried it before
     reporting that none exists, and report the search rather than the verdict:
     where you looked, how, and what came back. A bare "nothing exists yet"
     cannot be told apart from never having checked. When you have not looked,
     say so and name where you would look — that leaves duplication standing as
     an open risk with one step remaining, rather than a settled question.
   - **How general it is.** What the solution is specific to, and what reusing
     it elsewhere would take.
   - **Whether this is the elegant version or the quick one.** If quick, name
     the right version and what it would cost.
   - **What will strain at scale**, and anything that may conflict with work
     going on elsewhere.
   - **What forced any of the above.** When the design is worse than it should
     be because of a limit somewhere else, name the limit. A compromise the
     reader can trace to its cause is one they can decide to remove.
5. **Where it stands and what you need** — done, not done, unproven; then the
   decision you need, with the risk, cost, and time riding on it. When you need
   nothing, say so.

## Register

- **Prefer the ordinary phrase to the term of art.** Most jargon has a plain
  equivalent that costs a few more words and no comprehension: say "the part
  that decides which agent runs" rather than naming the dispatcher. Reserve a
  defined term for something with no plain equivalent that recurs often enough
  to earn its keep, and define that one against whatever it would be confused
  with. A page of defined terms reads as badly as a page of undefined ones.
- **Describe the approach, not the outcome.** "Handled the edge case" is
  unreviewable. Say what the code now does, concretely enough that a bad choice
  is visible to someone who cannot see it.
- **A long explanation a stranger can follow beats a short one they cannot.**
  Compress only when asked for a shorter version.
- **Ordinary complete sentences.** Plain is not clipped, and not telegraphic.
- **Neutral framing, not alarm.** State blockers as plain sequencing — what has
  to happen in what order — rather than as caution flags, especially when the
  thing is achievable. Alarmist hedging makes work read as bigger than it is.
- **Questions carry their own context.** Put everything needed to answer inside
  the question; the reader will not go looking.
- **The same bar in written docs.** Project docs, roadmaps, and handoffs get
  the same treatment: plain language, detail in the substance, identifier and
  file-path detail kept clearly secondary.

## Complete when

Re-read the draft. For work that earns the full shape, it names each piece and
how they connect, says which existing parts it builds on and what came back
when you looked for work that already did this, says what reusing it elsewhere
would take, and ends with the decision you need or states that none is needed.
For a contained change, it says what changed and what it touches, in words a
stranger could follow.
