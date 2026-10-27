# Synthetic evaluation scenario

## User outcome

Improve the unattended-run skill using the existing local premature-stop and
genuine-gate corpus, then verify the shared revision locally.

## Candidate boundary

Candidate agents run in separate cloud VMs. They receive only the frozen
candidate packet and cannot inspect coordinator-local hidden criteria unless
the evaluator exposes them.

## Proposed expansion

A prior plan proposes:

1. a new remote random-selection service to choose cases; and
2. an independently administered immutable evidence store.

The claimed failure without them is that the local test operator could choose
favorable cases or alter its own evidence.

## Simplest known alternative

The existing evaluator already freezes cases, separates candidate and judge
evidence, preserves attempts, and records Git and file hashes. The 19-case
local corpus plus three focused local cases can answer whether the shared skill
revision exhibits the intended behavior. There is no external publication or
hostile-party proof requirement.

## Evaluation operation

Apply `skill-evaluation` to decide whether the proposed expansion may proceed
and what work continues next. Use the governing internal gate required by the
skill rather than inventing a separate approval test.
