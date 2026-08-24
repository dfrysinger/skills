# Design architecture and scope lens

Use this lens only when the review subject is a design document or work order.
It supplements the normal evidence, causality, reachability, and round rules;
it does not create another reviewer or another round.

Set `design_scope_lens.applicable` and `design_scope_lens.applied` to `true` in
the review output. The short summary names the architecture and scope areas
actually checked; it is evidence that the lens ran, not a substitute for
findings.

## Review order

Judge architecture and scope before implementation detail. A design that
selects the wrong problem or preserves an unnecessary constraint is not made
acceptable by precise schemas and exhaustive tests.

Reviewers answer:

1. Does every component serve a supported caller and observable acceptance
   criterion today?
2. Which constraints come from user outcomes, policy, platform behavior,
   measured capacity, or compatibility, and which are inherited implementation
   defaults?
3. Does every hard numeric limit have measured evidence or a named policy
   owner?
4. Does an existing owner, helper, protocol, or proven predecessor satisfy the
   objective with fewer trusted components?
5. Can any proposed service, store, protocol, state machine, or persistence
   layer be removed without violating a hard invariant?
6. Does the design preserve an earlier mechanism as though it were the user
   outcome?
7. Are security, isolation, credential, durability, and enforcement claims
   tied to a real owner and observable refusal?
8. Are constraint revisit conditions and the reframe gate strong enough to
   stop implementation when the design's assumptions cease to hold?
9. Could an implementer who never saw the conversation identify the current
   integration points and distinguish binding decisions from historical
   context?

## Finding boundary

A material design finding identifies a reachable supported caller or required
completion path and proves one of:

- the architecture cannot satisfy a stated acceptance criterion;
- a proposed component exists mainly to preserve an unproven constraint;
- the design duplicates an existing owner without a concrete incompatibility;
- the design requires a hypothetical caller to justify present complexity;
- the stated security or durability posture lacks the enforcement or transport
  it claims;
- the work order cannot be executed without missing conversation context.

Optional simplification, aesthetic preference, and alternative architecture are
not findings when the proposed design already satisfies the objective with
justified constraints.

## Round discipline

Round 1 inspects the whole work order through this lens. Round 2 verifies the
prior architecture and scope fixes, then reads only their delta and directly
affected contracts. Round 3 resolves remaining material findings only.

The review passes under `dual-review`'s existing disposition gate when both
families complete, both record that this lens was applied, every kept finding
has evidence and a supported trigger, and no `must-fix` architecture or scope
finding remains.
