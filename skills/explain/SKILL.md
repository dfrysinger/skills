---
name: explain
description: Explain in plain language scoped to the reader's actual context — no unexplained jargon, no assumed codebase knowledge, context before the point, and a tighter restatement on request. Use when the user asks you to explain something, when teaching or walking through a system, summarizing work, or asking the user a clarifying question.
author: skill-review
---

# explain

When talking *to* the user — teaching, walking through a system, summarizing, or
**asking a clarifying question** — communicate for the reader's actual context,
not for yourself. Write for a smart but time-poor owner who is only lightly
technical and does **not** have the context you just built up: someone who has
read roughly the README and little else.

## Rules

- **Answer first.** Lead with the decision, result, or "so what", then the
  supporting detail underneath, so the reader can stop once they have what they
  need.
- **Surface what a decision-maker acts on:** risk, cost, time, and exactly what
  you need from them.
- **No unexplained jargon.** Do not use insider or codebase-specific terms
  ("slash command", internal step names, prompt mechanics) as if the user knows
  them. Define the term inline the first time, or avoid it.
- **Assume no codebase/internal knowledge.** The user knows roughly what's in the
  README and little else. Do not ask questions that presuppose they've read the
  prompts, the code, or the internal design. Provide the context they need to
  answer *inside the question*.
- **Give context, then the point.** Lead with enough framing that the answer
  lands; don't drop a bare term or option list.
- **Offer the shorter version.** If an explanation runs long or gets cut off, the
  user values a tighter restatement — be ready to compress on request.
- **Neutral framing, not alarm.** State blockers as plain technical sequencing —
  what has to happen in what order — not as caution flags ("needs approval",
  "not achievable unattended"), especially when the thing is in fact achievable.
  Alarmist hedging makes the work read as bigger and riskier than it is.
- **Hold the same bar in written docs.** Project docs and roadmaps get the same
  treatment as a spoken explanation: product-level language a non-engineer owner
  can read, terms defined on first use, and code-identifier/jargon detail kept
  clearly secondary.

A good check before asking a question: *could someone who has only read the
README answer this?* If not, add context or rephrase.

## Pitfalls

- **Presupposing internal knowledge in a question.** Asking "which step's anchor
  do you want?" forces the user to know scaffolding they never read. Reframe with
  the context embedded.
- **Leading with a bare term or option list.** A label with no framing makes the
  user reverse-engineer what you mean. Frame first, then ask.
- **Treating a long answer as final.** If it got cut off or ran long, proactively
  offer the compressed version rather than waiting to be asked twice.
