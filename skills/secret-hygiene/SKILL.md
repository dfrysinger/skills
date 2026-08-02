---
name: secret-hygiene
description: Keep secrets (tokens, API keys, PATs, passwords, private keys, session cookies) out of the chat transcript and out of git. Use when reading a token, configuring auth, writing a script that authenticates, asking a user to authenticate, or committing code that touches credentials.
author: dfrysinger
---

# secret-hygiene

Secrets must never reach two durable, third-party-visible places: the chat
transcript (every turn goes to a cloud model and is persisted) and git history
(forever, scraped within seconds on public repos). Once a value is seen outside
your trust boundary, rotation is the only fix — deletion never un-leaks it.

## Rule 0: chat is not private

Every user message, every assistant message, every tool output you display
back is sent to the cloud model provider and persisted in session-store
history. Treat the chat transcript as a **public, durable log**. If a value
shouldn't be on a billboard, it shouldn't be in chat.

This includes:

- A `cat ~/.env` or `env` dump that includes credential-shaped values
- A `gh auth token` or `aws configure get` output rendered in your reply
- A debug log line or captured request that prints an `Authorization` header
- A screenshot the user attaches that shows the secret on screen
- A stack trace that includes a connection string with embedded password
- A test fixture you read that turns out to contain a real key

If any of these appear, the secret is **already leaked**. Apologize, tell the
user to **rotate immediately**, and continue the work without that value in
the transcript.

## Rule 1: never ask the user to paste a secret into chat

Always prefer an indirection:

- "Put your token in `~/.config/<app>/token` (mode 600) and I'll pass it
  straight to the command that needs it, without reading it into the
  transcript."
- "Set `export GITHUB_TOKEN=...` in your shell and I'll consume it via env
  without printing it."
- "Run `op item get <name> --fields password | pbcopy` (1Password CLI) and
  paste it directly into the target tool — not into this chat."
- For macOS specifically: store in login keychain
  (`security add-generic-password -s <svc> -a <user> -w`) and read with `-w`
  inside a single-shot script that pipes straight to the consumer. **Never
  use `-g`** — it prints the password in human-readable form to the terminal,
  which means into your chat transcript.
- **Apply the same indirection to every credential, whatever its privilege.** A
  read-only token still enumerates your repos, collaborators, and CI variable
  names — reconnaissance an attacker uses to escalate. The bar is identical.

If the user *does* paste a secret despite this rule, stop and have them
rotate. A leaked credential cannot be un-leaked by being careful with it
afterward.

## Rule 2: never print, log, or echo a secret

When you must handle a credential value in a script you write or run:

- **Pipe, don't print.** Compose the value into the consumer inside a single
  bash tool call (each call is a fresh process, so vars don't persist anyway),
  and keep it off argv — a command-line argument is visible to `ps` for every
  user on the machine. Read it into a variable without echoing, then hand it to
  the consumer over stdin. `curl` takes a header from stdin with `--config -`,
  so only a status code reaches the transcript:

  ```bash
  TOK=$(security find-generic-password -s SERVICE -a "$USER" -w)
  printf 'header = "%s: Bearer %s"\n' 'Authorization' "$TOK" \
    | curl --config - -sS -o /dev/null -w '%{http_code}\n' https://api.example.com/
  ```
- **Redact in any displayed output**, but know that redaction protects only the
  display: every value in a tool output is sent to the model, so keep the raw
  value out of the output rather than masked in it. When you must show a header
  or env var for debugging, print only length and prefix — `len=40 starts=gho_`
  is enough to diagnose "wrong token type" without disclosing the value.
- **No `set -x` / `bash -x` while a secret is in scope.** Trace mode echoes
  every expanded command including the substituted credential.
- **Suppress error output that includes the value.** Many CLIs print the auth
  header on failure. Pipe stderr to `/dev/null` and rely on exit code + status
  code instead.
- **Summarize tool outputs that contain secrets.** "Got 200, token validates,
  scopes are X/Y/Z" — not the raw `gh auth status` block that includes the
  token.

## Rule 3: never commit a secret to git

Treat every repo as if it may become public (visibility flip, fork, archive
export); a private repo today can be public tomorrow. Layered defenses, each
assuming the previous one fails:

### Layer 1 — gitignore from day one

Before any code: `.env`, `.env.local`, `.env.*.local`, `*.pem`, `*.key`,
`*.p12`, `*.keystore`, `*credentials*`, `*secret*`, `id_rsa*`, `id_ed25519*`,
`*.kdbx`, `config/secrets.yml`, `.npmrc` (if it contains an auth token),
`.netrc`. Add framework-specific entries (Rails `master.key`, Next `.env*`).

### Layer 2 — committed `.env.example`, never the real one

Track an `.env.example` with **shape only** — placeholder values, not real
ones (`DATABASE_URL=driver://USER:PASS@HOST:PORT/DB`, `GITHUB_TOKEN=changeme`).
This documents the contract without leaking values.

### Layer 3 — pre-commit secret scanner that you prove fires

Install `gitleaks` (`brew install gitleaks` on macOS) and wire it as a
pre-commit hook. Pin a real release tag — resolve the current one with
`gitleaks version` or from github.com/gitleaks/gitleaks/releases (v8.30.1 at
time of writing) rather than guessing:

```bash
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
```

Or as a raw git hook in `.git/hooks/pre-commit`:

```bash
#!/usr/bin/env bash
gitleaks protect --staged --redact --no-banner || {
  echo "gitleaks found a secret in staged changes. NOT committing." >&2
  exit 1
}
```

`--staged` scans only what's about to be committed (fast); `--redact` keeps the
diagnostic itself from re-leaking the value.

**Prove the hook fires before you trust it** — installing a hook you never
triggered is not protection. Stage a synthetic fixture holding a fake
credential of a shape the scanner detects, and confirm the commit is REJECTED:

```bash
printf 'aws_secret_access_key = AKIA%s\n' '3H8Q2ZK9WL4M7XP0' > .leak-probe
git add .leak-probe
git commit -m 'probe (must be rejected)'   # non-zero exit = hook works
git restore --staged .leak-probe && rm -f .leak-probe
```

If that commit succeeds, the hook is not wired — fix it before relying on it.
Alternatives: `trufflehog`, `detect-secrets`. Pick one, configure once, leave
it on.

### Layer 4 — server-side push protection (verify it is actually on)

On GitHub, enable **Secret scanning** and **Push protection** (repo Settings →
Code security). Push protection rejects pushes containing known credential
patterns before the commit reaches the remote — the layer that saves you on a
fresh clone that never installed Layer 3.

Org policy can disable this, so confirm it rather than assume it:

```bash
gh api repos/{owner}/{repo} \
  --jq '.security_and_analysis.secret_scanning_push_protection.status'
```

If it reports `disabled`, or you lack permission to read or enable it, tell the
user this layer is unavailable and that Layers 1–3 are the only active
defenses. Do not claim a protection the repo does not have.

### Layer 5 — repo visibility matches intent before the first push

Before `git push` on a new repo, compare its actual visibility against the
visibility you intend for it:

```bash
gh repo view --json visibility -q .visibility
```

If the reported value differs from your intent — most often `PUBLIC` when you
meant private, the default `gh repo create` accepts silently — stop and fix the
visibility before pushing the first commit, not after.

## Rule 4: if a secret leaks, rotate

A leaked secret is leaked the moment it leaves your trust boundary —
posted to chat, pushed to GitHub, pasted in a Slack DM, screen-shared in a
Zoom call, written to a log shipped to a SaaS, included in a stack-trace
emailed to an error tracker. None of those are reversible by deletion.

The only effective response is **rotation**:

1. Generate a new credential at the source (GitHub PAT page, AWS console,
   `op item edit`, etc.).
2. Replace it everywhere it's consumed (env vars, keychain entries, CI
   secrets, deploy targets).
3. Revoke the old one immediately — leaving it "for now in case something
   breaks" is how leaks become incidents weeks later.
4. **Then** clean up the visible artifact (delete the chat message, force-push
   the history-rewritten branch, etc.). Treat that as cosmetic: the value was
   already seen, so rewriting history removes the artifact, not the exposure.
   The security-relevant action was step 3.

On a **public** repo: skip directly to rotation. GitHub's secret-scanning
partner program notifies issuers (AWS, GitHub itself, etc.) within seconds of a
leaked credential appearing in a public commit. Assume the value is compromised
the moment the push completes.

## Rule 5: store secrets at rest encrypted

Every credential written to disk is encrypted at rest — the OS keychain or a
properly encrypted store, never a plaintext column in a SQLite/Postgres table
or a plaintext config file. A plaintext credential on disk is a defect
regardless of the build's intended lifetime; a "temporary" plaintext store
reliably outlives its purpose and becomes the leak. If code-signing friction
(which unlocks the OS keychain) is the reason for reaching for plaintext, fix
the signing instead.

## Mode-specific traps

### macOS keychain

- Read with `-w` (writes only the password to stdout — pipe it straight to the
  consumer or into an unexported variable used in the same command), never `-g`
  (which prints "password: <value>" to the terminal in a parseable format).
- **The interactive `-w` prompt truncates input at 128 chars** (the
  `readpassphrase` cap). Storing a longer secret (JWTs, GitHub/HA long-lived
  tokens ~183 chars) via the prompt silently saves a truncated, useless value.
  For anything possibly over 128 chars pass the value non-interactively:
  `security add-generic-password -s <svc> -a <user> -w "$(pbpaste)"` or read it
  from a file — never the prompt.

### GitHub Codespaces / Actions

- Never `echo $SECRET` in an Actions step. Use `::add-mask::` if you must
  pass it to a downstream step and need it visible in logs (it gets
  redacted from the displayed log but is still in the workflow's memory).
- Codespaces expose the secrets configured for Codespaces, which are set
  separately from Actions secrets. To check which are present, list names
  only — `env` prints values, and a `grep` over it does not redact them:
  `env | sed 's/=.*$/=[set]/' | grep -iE 'token|secret|key'`.

### LLM tool calls (Copilot CLI, Claude Code, etc.)

- A `cat ~/.env` that contains real values is a leak even if you "only meant to
  look" — tool outputs go to the model on the next turn. To verify a credential
  file's shape, redact at the source:
  `awk -F= '{print $1"=...(redacted)..."}' ~/.env`
- Be wary of debug commands that dump request/response: `curl -v` prints
  the Authorization header. Use `-sS` plus `-w '%{http_code}\n'` instead.

### Test fixtures

- Test files that look like fixtures (`tests/fixtures/auth.json`,
  `__fixtures__/cookies.txt`) are still real secrets if they contain real
  values. The "it's just a test" reasoning has caused production leaks more
  than once.
- Use generated values (`uuidgen`, deterministic hashes) for fixtures.
  Real-shape, fake-value.

## Post-incident order

If you or the user just leaked something and need to clean up, the order is
fixed: **rotate first, audit second, clean third.** Don't spend time on history
rewrites or chat deletions until the credential is rotated (Rule 4).
