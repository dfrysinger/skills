---
name: prototype
description: Prototype what a screen should look like in throwaway HTML before it is built. Use when work introduces an entirely new screen or sweepingly changes existing ones, and when `scout` routes a chosen option here. Send contained or component-level UI changes to `feature-development-loop` instead.
---

# prototype

Prototype the interface in a throwaway file, where a change costs seconds,
rather than in a real implementation, where it costs days. This skill ends when
the user approves the sketch, and hands that file to `feature-development-loop`
as the picture its durable record is written against.

Two fidelities, in order. A **wireframe** shows structure only — navigation,
page chrome, where things sit. A **mockup** shows the thing actually being
decided, dressed enough to judge. Wireframe first to establish the canvas, then
mockup the part in question.

Every sketch is one self-contained `.html` file: inline styles, hard-coded
data, opened straight from disk. Anything that needs installing is out of
scope.

Put every version in front of the user's eyes and name the file path
alongside it. `visual-proof` owns that ladder.

## 1. Name the decision

State in one sentence what the user will decide by looking at the sketch —
which screens are in play, and what question the picture has to answer.
Fidelity follows from that sentence: dress only what the decision depends on.

Complete when the decision sentence and the list of screens are both stated.

## 2. Survey what already exists

Dispatch an `explore` subagent to inventory anything worth starting from, so
the search stays out of your context: existing sketches or prototypes, design
documents and screenshots, component libraries, style tokens, and the live
screens nearest to the ones in play.

Ask it to return file paths, the fonts, colors, spacing, and components the
product already uses, and one line on whether each find is usable as a
starting point.

Complete when you have either named a specific artifact to start from, or
established that nothing usable exists after searching design assets, existing
markup, and the component library.

## 3. Lay the canvas

When step 2 found a usable sketch, start from it and skip to step 4.

Otherwise, wireframe the interface as it stands today: navigation, page
structure, the chrome that surrounds the area in question, and the nearest
existing screens. Structure only — boxes labelled with real product nouns.
Nothing here is being proposed yet; this is the blank canvas the proposal will
sit on.

Complete when the user confirms the wireframe reads as their product, before
any new interface is drawn on it.

## 4. Iterate in rounds

Each round settles one named decision. Say which decision you are taking and
what you propose, change that and only what depends on it, then show the
result with a short **changed / unchanged / open** list and one question whose
answer opens the next round. Areas the user has already settled stay put until
they reopen them.

When feedback spans navigation, layout, and content at once, offer those as
separate rounds unless the user asks for a combined pass.

Show alternatives side by side when a choice is genuinely open — two variants
in one file beats two rounds of guessing.

Overwrite whole sections freely; this is a sketch, and the only thing it owes
the future is the decision it settles.

Keep a `<!-- decisions -->` comment at the top of the file listing the settled
decisions, the open one, and the round number. That comment is what survives a
compacted session; the conversation is not.

Complete when the user explicitly approves the sketch as final. Appreciation is
not approval: when the feedback is warm but settles nothing, ask whether to
treat the sketch as final and hand it to development.

## 5. Hand it to the build

Commit the file at a path that will still make sense in a year, named for the
screen rather than the round.

Hand off to `feature-development-loop` with the sketch linked at the top of the
durable record its lane produces — the design document for systemic or
critical work, the change note for bounded work. Every interface claim in that
record should be checkable against the file.

Invoke `context-hygiene` before handing off. The committed file and its
`<!-- decisions -->` comment carry everything the build needs; the rounds that
produced them do not.

Complete when the file is committed, the handoff names both its path and the
record it was linked into, and the compact is submitted.

## Pitfalls

- **Sketching the happy path only.** Empty, loading, error, and overflow states
  are where a new screen is really decided, and they are the states an
  implementation discovers too late.
- **Implementing instead of sketching.** Wiring real data or making it work is
  the build's job. The sketch only has to show.
