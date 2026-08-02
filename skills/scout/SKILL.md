---
name: scout
description: Scout how to achieve something in a project before any code is written. Use when the user asks how to achieve, add, or support something in a project, asks whether it is possible or how hard it would be, asks what the best or standard approach is, or asks who already ships it and how. Use when another skill needs the problem explored before the change is defined.
---

# scout

Answer "how should we do X here?" with evidence rather than the first plausible
design. You are scouting ahead of the build: go look, report back, let the user
choose. This skill ends at a report and a handoff; the skill downstream writes
the code.

A **point scout** rides out first to settle the terms, then four ride at once
— **in flight**, **in tree**, **in house**, and **in the wild**. The near tiers
can end the mission: work already underway makes the question moot.

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

Dispatch one `explore` subagent to settle the vocabulary the other four will
search with. Give it the outcome sentence and the repository, and ask it to
report the terms this codebase uses for the topic, the terms the surrounding
ecosystem uses for it, and the stack a solution would be built on — language,
framework, and the libraries already carrying nearby work.

Require **names as well as mechanisms**. A mechanism term describes what the
thing does — *memory consolidation*, *retry with backoff*. A name is what
someone shipping it calls it on a landing page or a channel topic: a product
name, a project codename, a metaphor. Teams name a channel after their
metaphor and never after their mechanism, so a well-chosen mechanism term will
miss a product that is this exact feature under a name nobody guessed.

**Names are harvested, not invented.** A guessed metaphor is worthless — it
searches for a product that does not exist while the real one keeps its own
name. So require the point scout to run a **harvest pass**: search the outcome
and mechanism phrases broadly on the open web and across the organisation's
own issues, then pull the **proper nouns** out of what comes back — product
names, codenames, channel names, repository names, terms of art capitalised in
prose. Each harvested name must arrive with the source that used it. Then
search each harvested name once more, since a product name in a release note
leads to the architecture post behind it.

The names are the harvest's output, and there may be none. Reporting *"no
distinct name found; here are the terms searched"* is a valid, useful result.
Inventing one to satisfy this step is the failure it exists to prevent.

Complete when you hold the codebase's terms, the ecosystem's terms, the stack,
and either at least one **name with the source that used it** or an explicit
statement that the harvest found none — the terms and stack each traced to a
file path or manifest.

## 3. Dispatch the four tiers at once

In a single response, issue the `task` calls for **in flight**, **in tree**,
and **in the wild**, and run your own chat searches for **in house** alongside
them. Then dispatch the in-house follow-up scout with the names that search
harvested. Each brief carries the outcome sentence, the repository, and the
point scout's terms, names, and stack. Every search runs against the names as
well as the mechanisms. Each scout reports; none of them recommends.

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
returned nothing. When `gh` reports an invalid token inside the agent shell,
the login keychain is not visible to this process: restart the tmux server
from a GUI Terminal session so it inherits one.

**In tree** (`explore`) — read what the codebase already does toward this
outcome, searching on the point scout's terms, and the orienting docs
(`README`, `AGENTS.md`, design docs, ADRs) for rules that constrain the
answer. Returns, with file paths, the entry points, state owners, and
extension points a solution would sit on, plus every existing helper or
pattern that could carry part of the outcome; and which orienting docs it read
and which rules in them bind — or that there is none of the above. Collect
what exists; designing belongs in the report.

**In house** — find whether this organisation is already building it. This
tier exists because the nearest competitor is usually a colleague, and
colleagues announce their work in chat long before it is searchable in code.

**Split this tier across yourself and a subagent.** A subagent does not
inherit your MCP tools, so an `explore` scout dispatched to search Slack finds
no Slack tools and returns nothing — the tier's highest-signal step, silently
skipped. So run the chat search **yourself**, in your own context. It is the
one exception to keeping legwork out of your context, and it is affordable
because a handful of channel searches is small next to what it catches. Then
dispatch an `explore` scout with the names you harvested to do the reading and
the code-following, which is the bulk of the work.

Search chat first. Run **each** harvested name and **each** mechanism term as
its own search — combining them into one query is how a real channel gets
missed — across both public and private channels the account can reach. Search
channel names, topics, and purposes before messages: a channel purpose is the
highest-signal artifact in the company, one sentence in which a team says
exactly what it is building. Read the most relevant channel rather than
trusting a search snippet, and harvest again from what you read — internal
codenames, repository links, epic numbers, the names of the people who own it.

Expect the names to carry this tier and the mechanism terms to return noise: a
team's channel is named for what they call the thing, so a search for
*skills forge* finds nothing while the project's metaphor finds the channel,
the owners, and the repositories in one hit.

Report the search surface, not just the findings: which workspace, whether
private channels were reachable, every phrasing run, and anything access
denied you. *"Nothing found"* means nothing without that, since it is
indistinguishable from a narrow or public-only search.

Then **follow what you found into code.** Take the repositories, issues,
epics, and design documents linked from those channels and read them. Do not
sweep the organisation's repositories on mechanism terms — generic terms
return hundreds of unrelated hits and bury the finding.

Two searches are worth running blind, because internal work is not always
discussed in a channel you can see:

- Each **distinctive** name, organisation-wide. Distinctive means an evidenced
  proper noun or codename specific enough that a hit is almost certainly this
  work — test it by sampling the first few results and abandoning the search
  if they are unrelated. A common word, even a vivid one, is not distinctive
  on its own; pair it with a qualifier.
- The names of any **team or repository** you have independent reason to think
  owns this area, whether or not Slack led you there.

```bash
gh search issues --owner <org> --limit 20 --json number,state,title,url '<distinctive name>'
gh search prs --owner <org> --limit 20 --json number,state,title,url '<distinctive name>'
```

Returns the channels and repositories found with links, who owns the work, how
far along it is, and one line on whether it overlaps the outcome — or that the
searches returned nothing, with the surface above.

**Everything this tier finds is confidential.** Summarise it; do not paste
internal content, quotes, or links wholesale. Keep it to a section of the
report marked internal, and keep that report on local disk. It must never
reach a public repository, an upstream issue, a commit message, a published
document, or an external service — including any agent or tool that transmits
its input off this machine.

**In the wild** (`research`) — find who has already **shipped** this, not who
has theorised about it.

Decide first which kind of claim you are being asked to evidence, and say
which you chose. A question is often **both** — *how should we cache this?*
has a user-visible half and an implementation half — so where it is both,
split it and apply each bar to its own half rather than forcing one label:

- **A capability** — a feature a user would notice. Require **shipped products
  at scale**: generally available or in public preview, from an organisation
  large enough that the design survived real users. Evidence is vendor
  documentation carrying a version or date, changelogs and release notes,
  pricing or availability pages, conference talks, and postmortems. A blog
  post proposing an approach, an unmerged prototype, a preprint, and a
  weekend project are **not** evidence a design works; cite them only when
  labelled as unproven, and never as the basis of a recommendation.
- **A programming pattern** — a technique inside the code with no user-visible
  surface. Here consensus *is* the evidence: framework documentation, RFCs,
  standard-library precedent, and engineering write-ups from teams running it.

Search the point scout's harvested **names** first and its mechanism terms
second, and **harvest again as you go**: every result that names a product,
vendor, or codename you had not seen becomes a new search. A shipped product
is indexed under its own name, so the first mechanism search rarely reaches
it — but it is what surfaces the name that does. Stop when a round of searches
turns up no new names.

Returns, for each of at least two independent sources: who shipped it, its
date or version, **how they built it** — the architecture, the data flow, and
the specific mechanism, in enough detail to be copied or deliberately rejected
— the tradeoff they accepted, and, for a capability, its shipping status and
rough scale of use. Plus where consensus sits, or that the field disagrees.

A source that establishes only *that* someone shipped this has not met the bar.
The question is who has solved it at scale **and how**, so keep digging until
the mechanism is legible: chase the architecture post behind the launch
announcement, the design document behind the changelog, the source behind the
product page. Where the how is genuinely undisclosed, say so plainly and say
what you inferred it to be.

Complete when all four scouts have returned and each has met the bar above.
Redispatch any scout that came back short, naming what was missing.

## 4. Triage what came back

**Stop when the work is joinable.** If a team upstream or in house owns this
and the user could plausibly join it, wait for it, or adopt what it produces,
stop here: report who and where, and put that choice to them. The other
reports are already in hand, so offer them.

A vendor who merely ships something similar is **not** a reason to stop. It
cannot be joined, it may cover only part of the outcome, and its architecture
is exactly the evidence the report needs. Carry it into *Who is already
building it* and finish the report.

Complete when you have either stated that no joinable effort overlaps, or put
the join-wait-build choice to the user.

## 5. Write the scout report

Cover five things, in this order:

- **What is possible** — the genuine options, including doing nothing.
- **What is easy** — what the tree already supports today, from the in-tree
  scout.
- **Who is already building it** — the in-flight and in-house findings, and
  any shipped product that covers this outcome: for each, who owns it, how
  much of the outcome it covers, and **how it works**, since a design that
  survived scale elsewhere is the cheapest evidence available to us.
- **What is best practice** — what the in-the-wild scout found, and where it
  conflicts with this codebase's existing patterns.
- **What you recommend** — one option, the tradeoff it accepts, and the ladder
  rung it lands on: reuse, extend, or create. Recommending *create* requires
  saying which reuse and extend candidates you rejected and why — including
  any shipped or in-house product that already covers the outcome.

Follow `explain` for the register.

Complete when all five sections are present, the recommendation names its
tradeoff and says why the balance sits there rather than one rung cheaper or
one rung better, and every claim traces to a specific pull request, file path,
channel, or source from the scout reports.

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

- **Dispatching the scouts in separate responses.** That runs them in series
  and costs four times the wall clock.
- **Scouting the tiers yourself.** The legwork belongs in subagent context so
  yours stays clear for the report.
- **Searching the mechanism and never the name.** A team ships this capability
  under a product name or a metaphor, and a search for what it *does* returns
  nothing. Harvest names from what the first searches return, then search
  those — and never invent a name to search for.
- **Skipping the in-house tier because the work feels novel.** The competitor
  most likely to already be building this is a colleague, and the only place
  that is visible early is chat.
- **Accepting a proposal as proof.** A conference talk about a running system
  outranks a blog post proposing one, however well argued. For a capability,
  shipped beats clever.
