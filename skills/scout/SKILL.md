---
name: scout
description: Scout how to achieve something in a project before any code is written. Use when the user asks how to achieve, add, or support something in a project, asks whether it is possible or how hard it would be, or asks what the best or standard approach is. Use when another skill needs the problem explored before the change is defined.
---

# scout

Answer "how should we do X here?" with evidence rather than the first plausible
design. You are scouting ahead of the build: go look, report back, let the user
choose. This skill ends at a report and a handoff; the skill downstream writes
the code.

A **point scout** rides out first to settle the terms, then three ride at once
— **in flight**, **in tree**, and **in the wild**. The nearest can end the
mission: work already underway makes the question moot.

Every scout is a subagent. Their digging stays in their context; only their
reports enter yours.

Every recommendation obeys one ladder: **reuse before extend, extend before
create.**

## 1. Frame the question

Restate the goal as one sentence naming the outcome the user wants to observe,
not the mechanism they guessed at. Identify the target repository; when the user
names no project, use the repository containing the current working directory
and say which one you picked.

Complete when the outcome sentence and the chosen repository are both stated in
your reply.

## 2. Send the point scout

Dispatch one `explore` subagent to settle the vocabulary the other three will
search with. Give it the outcome sentence and the repository, and ask it to
report the terms this codebase uses for the topic, the terms the surrounding
ecosystem uses for it, and the stack a solution would be built on — language,
framework, and the libraries already carrying nearby work.

Complete when you hold the codebase's terms, the ecosystem's terms, and the
stack, each traced to a file path or manifest.

## 3. Dispatch three scouts in parallel

Issue all three `task` calls in a single response so the tiers run at once.
Each brief carries the outcome sentence, the repository, and the point scout's
terms and stack. Each scout reports; none of them recommends.

**In flight** (`explore`) — search pull requests and issues before anyone reads
code. Someone may already own this.

```bash
gh repo view --json nameWithOwner
gh search prs --repo <owner/repo> --state open --limit 30 --json number,state,title,url '<terms>'
gh search prs --repo <owner/repo> --state closed --limit 30 --json number,state,title,url '<terms>'
gh search issues --repo <owner/repo> --limit 30 --json number,state,title,url '<terms>'
```

Require a search for each of the point scout's terms, the codebase's and the
ecosystem's alike. Closed-unmerged pull requests matter most: a rejected
attempt at this feature is the highest-value thing this tier can find. When
the remote is not GitHub, use that host's equivalent searches and name which
ran. Returns every phrasing searched, and each candidate with its number,
state, url, and one line on whether it overlaps — or that the searches
returned nothing. If `gh` reports an invalid token inside the agent shell,
see `gh-auth-macos`.

**In tree** (`explore`) — read what the codebase already does toward this
outcome, searching on the point scout's terms, and the orienting docs
(`README`, `AGENTS.md`, design docs, ADRs) for rules that constrain the
answer. Returns, with file paths, the entry points, state owners, and
extension points a solution would sit on, plus every existing helper or
pattern that could carry part of the outcome; and which orienting docs it read
and which rules in them bind — or that there is none of the above. Collect
what exists; designing belongs in the report.

**In the wild** (`research`) — find how others solved this on the point scout's
stack in production, preferring engineering write-ups, framework documentation,
RFCs, and the source of comparable systems. Returns at least two independent
sources describing real production use, each with its date or version and the
tradeoff it accepted, plus where consensus sits or that the field disagrees.

Complete when all three scouts have returned and each has met the bar above.
Redispatch any scout that came back short, naming what was missing.

## 4. Triage what came back

**When someone is already building it, stop here.** Report who and where, and
ask the user whether to join that effort, wait for it, or research on anyway.
The other two reports are already in hand, so offer them.

Complete when you have either stated that no in-flight work overlaps, or put the
join-wait-continue choice to the user.

## 5. Write the scout report

Cover four things, in this order:

- **What is possible** — the genuine options, including doing nothing.
- **What is easy** — what the tree already supports today, from the in-tree
  scout.
- **What is best practice** — what the in-the-wild scout found, and where it
  conflicts with this codebase's existing patterns.
- **What you recommend** — one option, the tradeoff it accepts, and the ladder
  rung it lands on: reuse, extend, or create. Recommending *create* requires
  saying which reuse and extend candidates you rejected and why.

Follow `explain` for the register.

Complete when all four sections are present, the recommendation names its
tradeoff and says why the balance sits there rather than one rung cheaper or
one rung better, and every claim traces to a specific pull request, file path,
or source from the three scout reports.

## 6. Align, then route

Present the report and get an explicit choice before routing.

Route on the chosen option's interface surface:

- **An entirely new screen, or a sweeping change to existing screens** — hand
  off to `interface-mockup`, which settles the interface in throwaway HTML
  before any durable design work begins.
- **Everything else** — a screen assembled from existing components, a
  contained change to one, or no interface at all. Hand off to
  `feature-development-loop`, which classifies the lane and writes the durable
  contract.

Invoke `context-hygiene` before handing off. The report is the baton; the
scouting that produced it is not.

Complete when the user has chosen an option, you have named the route taken,
and the compact is submitted.

## Pitfalls

- **Dispatching the three in separate responses.** That runs them in series and
  costs three times the wall clock.
- **Scouting the tiers yourself.** The legwork belongs in subagent context so
  yours stays clear for the report.
