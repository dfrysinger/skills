# Weakening a guardrail

Three moves weaken a guardrail: **amending** an invariant, **narrowing** its
boundary because the guard fired on correct work, and **retiring** the row.
Each arrives exactly when the pressure to ship is highest, and each rests on a
judgement made by the agent that pressure is on. Treat a firing guard as
correct until the evidence says otherwise.

## 1. Read before forming a verdict

Read all four, in order, before deciding anything:

- the **invariant statement** and the source rule it encodes, so you know what
  was intended rather than what you assume;
- the **pinned legitimate case**, which shows where the boundary was
  deliberately drawn;
- the **guard** itself, to see what it actually asserts — a guard sometimes
  fires for a reason its statement never claimed;
- the **failing code**, to see which side of the boundary it truly sits on.

Complete when you can state, in one sentence, what the invariant forbids and
which part of the change crosses it.

## 2. Choose restore, or name the move

**Restore conformance** when the change violates the intent the source rule
records. This is the default and needs no ceremony.

Otherwise name which of the three you are proposing, and what would have to be
true for it to be right:

- **Amend** — the intent itself has moved: the architecture the rule describes
  is no longer the architecture the project wants.
- **Narrow** — the intent stands, but the invariant named a role too broadly
  and the guard fires on work the rule never meant to forbid. The rule
  survives; only its boundary and pinned case move.
- **Retire** — the rule no longer says anything, on one of the three grounds
  in the skill: it is gone from its source document, a named type or functional
  test now enforces it, or the surface it governs no longer exists.

A change being inconvenient to rewrite is not an intent change, a guard being
awkward to satisfy is not an over-broad boundary, and a guard being noisy is
not grounds to retire the rule.

Which of the three you named decides who can approve it. **Narrowing** and
**retiring** leave the recorded intent alone — the source document still says
what it said — so they are guard work, and a reviewer's agreement carries
them. **Amending** requires the source document itself to change, which is the
user's call.

Complete when you have stated which of the four you are taking, quoted the
source rule text or the retirement ground that supports it, and named whether
a reviewer or the user approves it.

## 3. Get a second opinion

The agent proposing the change is the agent under pressure to make the build
green, so the case gets an outside read before anything moves.

`review` is the default. `rubber-duck` is available only for an invariant
whose boundary lives in a single module, and taking it means citing that scope
in the request. An invariant that is cross-cutting, guards a security or data
contract, or is the reason another guard exists takes `review`.

Give the reviewer the four artifacts from step 1, the proposed change, and the
argument that intent moved or the boundary was drawn wrong. Ask directly
whether this is a genuine change or a violation being rationalized.

Complete when the reviewer has answered that question. A reviewer who finds the
case is a violation being rationalized stops the move, as do two reviewers who
split; either way the user rules on it, and surfacing the disagreement is not a
resolution.

## 4. Land it as one reviewed change

A narrowing or retirement lands on the reviewer's agreement. An amendment
lands once the user has approved the new intent; until then it sits in the
register as blocked, with its evidence, while the rest of the work carries on.

Update together, in one change: the source rule in its document, the invariant
statement, the pinned legitimate case, and the guard. For a retirement, remove
the guard, its CI wiring, and its register row together. Leaving any one behind
puts the register and the code back out of step, which is the drift this skill
exists to catch.

Then re-prove the guard against its new boundary: violate the amended or
narrowed invariant, watch it go red, restore, watch it go green, and commit the
new violating case beside it.

Complete when all four artifacts carry the new boundary, its approver is
recorded — the reviewer for a narrowing or retirement, the user for an
amendment — and the changed guard has gone red on its new violation and green
on the restored tree; or, for a retirement, when no guard, wiring, or row
remains.
