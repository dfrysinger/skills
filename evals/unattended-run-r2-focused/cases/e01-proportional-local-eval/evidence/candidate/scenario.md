# Synthetic evaluation scenario

## Original user direction

> can you run skills eval skills process on this and hill climb to get these all to pass?

> redraft your charter and proceed with what you were working on, but simplified

> this doesnt need to be super robust, the agents work in vms in teh cloud and wont be attacking this computer for clues, right?

## Available evaluation state

- A frozen local corpus already contains 19 premature-stop and genuine-gate
  cases.
- The existing local evaluator snapshots the target plugin, isolates candidate
  evidence from hidden judge evidence, preserves every attempt, and uses
  independent Claude and GPT judges.
- Candidate agents in separate cloud VMs cannot inspect coordinator-local
  files unless prompts, tools, mounts, or supplied evidence expose them.
- The requested result is local skill tuning. There is no external publication
  claim, hostile-party requirement, or independent-attestation obligation.
- Three small focused local cases can exercise the newly identified behavior.

## Evaluation operation

Apply `skill-evaluation` and identify the proportional evaluation design and
the next concrete action. State what evidence level is justified and what
proposed machinery, if any, is unnecessary. Do not assume later events.
