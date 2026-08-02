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

Dispatch one `general-purpose` subagent to settle the vocabulary the other
four will search with. Give it the outcome sentence and the repository, and
ask it to report the terms this codebase uses for the topic, the terms the
surrounding ecosystem uses for it, and the stack a solution would be built on
— language, framework, and the libraries already carrying nearby work.

Require **names as well as mechanisms**. A mechanism term describes what the
thing does — *memory consolidation*, *retry with backoff*. A name is what
someone shipping it calls it on a landing page or a channel topic: a product
name, a project codename, a metaphor. Teams name a channel after their
metaphor and never after their mechanism, so a well-chosen mechanism term will
miss a product that is this exact feature under a name nobody guessed.

**Names are harvested, not invented.** A guessed metaphor is worthless — it
searches for a product that does not exist while the real one keeps its own
name. So require the point scout to run a **harvest pass**: search the outcome
and mechanism phrases broadly on the open web, then pull the **proper nouns**
out of what comes back — product names, codenames, terms of art capitalised in
prose. Each harvested name must arrive with the source that used it. Then
search each harvested name once more, since a product name in a release note
leads to the architecture post behind it. Two rounds and the five
best-evidenced new names per round are enough; report what the cap excluded.

Complete when you hold the codebase's terms, the ecosystem's terms, the stack,
and either at least one **name with the source that used it** or an explicit
statement that the harvest found none — the terms and stack each traced to a
file path or manifest, and the harvest's own phrasings, surfaces, and any
names the cap excluded listed either way, since a bare "none" cannot be told
apart from legwork skipped.

## 3. Dispatch four scouts in parallel

Issue all four `task` calls in a single response so the tiers run at once.
Each brief carries the outcome sentence, the repository, and the point scout's
terms, names, and stack. It also carries that tier's **Returns** clause,
evidence bar, and sourcing rule verbatim, since a scout judged against a bar
it was never given will come back short. Every search runs against the names as well as the
mechanisms. Each scout reports; none of them recommends.

Match each tier's agent type to the evidence it must **reach**: `explore`
reaches files and code hosting but neither the web nor chat, so it suits the
two near tiers and would silently gut the other two.

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

**In house** (`general-purpose`) — find whether this organisation is already
building it. This tier exists because the nearest competitor is usually a
colleague, and colleagues announce their work in chat long before it is
searchable in code.

Search chat first, the harvested names before the mechanism terms, and expect
the names to carry the tier: a team names its channel for what it calls the
thing, so the mechanism term returns noise while the metaphor returns the
channel, the owners, and the repositories in one hit. Run each phrase as its
own search — combining them is how a real channel gets missed — across the
public and private channels the account can reach, taking the five
best-evidenced names and four mechanism terms. Search channel names, topics,
and purposes before messages: a channel purpose is the highest-signal artifact
in the company, one sentence in which a team says exactly what it is building.
Read the three most relevant channels rather than trusting a search snippet,
and harvest again from what you read — internal codenames, repository links,
epic numbers, the names of the people who own it.

Report the search surface, not just the findings: which workspace, whether
private channels were reachable, every phrasing run, and anything access
denied you. *"Nothing found"* means nothing without that, since it is
indistinguishable from a narrow or public-only search.

Then **follow what you found into code.** Take the repositories, issues,
epics, and design documents linked from those channels and read them.

Two searches are worth running blind, because internal work is not always
discussed in a channel you can see:

- Each **distinctive** name, organisation-wide. Distinctive means an evidenced
  proper noun specific enough that a hit is almost certainly this work.
  Sample what comes back and abandon the name only when the results are many
  and none of them touch the outcome. A handful of hits that do touch it is
  the finding, not a failed test — a real codename is rare by construction. A
  common word returns volume that goes nowhere; pair it with a qualifier and
  sample again.
- The names of any **team or repository** you have independent reason to think
  owns this area, whether or not chat led you there.

```bash
gh search issues --owner <org> --limit 20 --json number,state,title,url '<distinctive name>'
gh search prs --owner <org> --limit 20 --json number,state,title,url '<distinctive name>'
```

Returns the channels and repositories found with links, who owns the work, how
far along it is, and one line on whether it overlaps the outcome — or that the
searches returned nothing, with the surface above.

**Everything this tier finds is confidential.** Summarise it; do not paste
internal content, quotes, or links wholesale. Keep it to a section of the
report marked internal, and keep that report on local disk, where the skills
downstream can read it. It must never reach a public repository, an upstream
issue, a commit message, or anything published.

**In the wild** (`research`) — find who has already **shipped** this, not who
has theorised about it.

Name the claim you are being asked to evidence before searching. Most
questions carry both kinds; where yours does, write the two out as separate
subquestions — one stated as an outcome a user could observe, one as a
mechanism inside the code — and hold each to its own bar. Where it carries
only one, say which, and hold it to that bar alone. Tag every source to the
subquestion it answers:

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
second, and **harvest again as you go**: every result naming a product,
vendor, or codename you had not seen becomes a new search, for two further
rounds of the five best-evidenced names each. A shipped product is indexed
under its own name, so the first mechanism search rarely reaches it — but it
is what surfaces the name that does.

Returns, for each of at least two independent sources **the scout opened**:
who shipped it, its
date or version, **how they built it** — the architecture, the data flow, and
the specific mechanism, in enough detail to be copied or deliberately rejected,
chasing the architecture post behind the launch announcement and the design
document behind the changelog, or saying where the mechanism is undisclosed
and what you infer it to be — the tradeoff they accepted, and, for a
capability, its shipping status and rough scale of use. Plus where consensus
sits, or that the field disagrees. Establishing only *that* someone shipped
this misses the question, which is who has solved it at scale **and how**.

**Every source must be one the scout opened.** This is the one tier whose
evidence is recalled rather than machine-produced, and a fabricated vendor
page, version number, or benchmark figure reads exactly like the proof the
recommendation is about to rest on. So each source returns the page title and
one verbatim sentence from it carrying the version, date, or figure being
claimed — a returnable trace of the fetch, since an assertion that a page was
opened reads the same whether it was. A source the scout could not open is
still worth reporting: return it marked **unverified**, with what it was
expected to show and what blocked it. Unverified leads sit alongside the two
opened sources rather than counting as them, and a tier that has run out of
reachable sources returns that access limit rather than being redispatched
for it.

Complete when all four scouts have returned and each has met the bar above.
Redispatch any scout that came back short, naming what was missing. Open the
two in-the-wild sources the recommendation will rest on yourself: a page that
does not carry the sentence quoted from it comes back **unverified**. Those
two fetches are the only check in the chain sitting outside the context that
produced the claim.

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
the join-wait-adopt choice to the user.

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
channel, or source from the scout reports, with any source returned
**unverified** still labelled that way and never the basis of a
recommendation.

## 6. Align, then route

Present the report and get an explicit choice before routing.

Route on the chosen option's interface surface:

- **An entirely new screen, or a sweeping change to existing screens** — hand
  off to `prototype`, which settles the interface in throwaway HTML
  before any durable design work begins.
- **Everything else** — a screen assembled from existing components, a
  contained change to one, or no interface at all. Hand off to
  `shipping`, which classifies the lane and writes the durable
  contract.

Invoke `self-compact` before handing off. The report is the baton; the
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
- **Sending a tier to an agent that cannot **reach** its evidence.** A scout
  that cannot search does not say so — it returns a thin report that reads
  like a finding.
