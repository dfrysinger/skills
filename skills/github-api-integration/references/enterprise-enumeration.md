# Enterprise enumeration & policy-surface reference

Specialized reference for `github-api-integration`: enumerating enterprise
Copilot seats/licenses/agent activity, and which enterprise/org policy surfaces
have a REST API. Reach for it only when a run actually touches these endpoints.

## Enumerating Copilot seats, licenses & agent activity (enterprise)

GitHub's enterprise Copilot enumeration endpoints have **unstable ordering** and
**no total-consistent pagination** — walking them naively both duplicates and
drops rows. Reconcile to a known total; never trust a single page walk.

- **`/enterprises/{ent}/copilot/billing/seats`** has unstable page-offset
  pagination: naive `page=1..ceil(total/100)` yields duplicates AND misses
  seats. You **must follow `Link rel=next` to exhaustion**; even then expect the
  walk to under-cover — mark the result incomplete honestly. Per-seat fields
  include `organization.login`, `assigning_team` (enterprise team slug `ent:...`),
  `last_activity_at`, `plan_type`, `pending_cancellation_date`. The org-level
  `/orgs/{org}/copilot/billing/seats` **404s** when Copilot billing is
  enterprise-managed.
- **The `all_member_licenses` endpoint has NO sort param** and its seat query is
  an unordered `UNION ALL`, so page order is unstable across refetches — the
  client must **reconcile-to-total**, not page once.
- **Copilot coding-agent Actions runs** are attributed to actor
  `{login:"Copilot", type:"Bot"}` (a distinct numeric bot id) — a **distinct**
  identity from the PR-author `copilot-swe-agent[bot]`, which is *never* the
  Actions-run actor. Don't conflate them when attributing runs.
- **No single API lists all agentic activity enterprise-wide.** Live "running
  now" is only repo/user-scoped (requires fan-out); enterprise breadth is
  **historical only** (audit log `actor:Copilot`, or `copilot/usage-records` over
  a trailing window).
- **`/enterprises/{ent}/copilot/custom-agents`** needs the `copilot` OAuth scope
  **plus** an enterprise role — without them it's a **403, not a 404**. It
  returns only a `{name, file_path, url}` inventory; there's no run/session
  provenance to join onto live activity.
- **Audit-log scope differs by host.** On github.com, `GET /orgs/{org}/audit-log`
  needs `admin:org` **and** org-owner rights (`read:org` gets a 403); on GHES the
  same endpoint accepts `read:org` for org admins — so audit-log breadth works on
  a GHE enterprise but not on a dotcom sub-org you don't own.

## Enterprise & org policy: which surfaces have an API

- **Enterprise Actions policy is fully REST-scriptable** at
  `/enterprises/{ent}/actions/permissions/*` — the allowed-actions allowlist,
  `sha_pinning_required`, fork-PR approval, and the default read-only
  `GITHUB_TOKEN` setting. But the **classic member-privilege enterprise policies**
  (repo creation / visibility / base permissions) are **UI-only — no API.**
- **GitHub's native policy engine is rulesets + custom properties.** Rulesets
  carry a conditions engine (`ref_name` / `repo_name` / repo custom-property, plus
  org targeting at the enterprise level) and an **`evaluate` (dry-run) mode**;
  custom properties act as targeting labels. All of it is GA via REST / Terraform.
