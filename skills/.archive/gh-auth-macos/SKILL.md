---
name: gh-auth-macos
description: Fallback for restoring gh CLI authentication inside an agent shell on macOS, and for generating the ~/.ssh/codespaces.auto key gh expects. Use when `gh auth status` reports invalid token, the login keychain isn't visible to the agent process, gh returns a stale token after `gh auth refresh`, or `gh codespace ssh` fails with "Permission denied (publickey)". The preferred fix for the keychain visibility problem is restarting the tmux server under a GUI Terminal session (see remote-agent-stack's tmux-keychain-bootstrap LaunchAgent) — use this skill only when that isn't an option.
---

# gh-auth-macos

## Read this first — preferred fix isn't this skill

The root cause of gh-broken-in-agent-shells on macOS is **not** specific to
`gh` and **not** something this skill ideally solves. It's that the tmux
server inherits the keychain context of whatever shell originally started
it. When that shell is a Tailscale-SSH login (which is what happens the
first time you run `ca <name>` after a Mac reboot), macOS gives it a
restricted keychain search list — System keychain only, no login keychain.
Every shell the tmux server spawns from then on inherits the restriction,
even after you "re-attach" the session from somewhere else. `gh`, the
`osxkeychain` git credential helper, and anything else that goes through
the OS keychain API silently fail.

**The right fix is structural:** restart the tmux server under your GUI
(Aqua) login session, and from then on every session inside it has full
login-keychain access. Done. This skill becomes unnecessary.

The cleanest way to make that automatic across reboots is the
`tmux-keychain-bootstrap` LaunchAgent that `remote-agent-stack`'s
installer offers to install. It runs at every GUI login, starts a hidden
anchor session called `_keychain-anchor` so the tmux server survives,
and that's it. After it's installed, `ca <name>` calls attach to a
correctly-contextualized server and `gh` just works with no env-var
gymnastics.

To install it: re-run `~/code/remote-agent-stack/install.sh` (or the
equivalent path for your clone) and answer Y at the
"tmux keychain bootstrap" prompt.

## When to use this skill anyway

This skill is the **fallback for the cases where you can't restart the
tmux server**, including:

- You're on someone else's Mac and can't install a LaunchAgent.
- Your tmux server is in the wrong context right now and you have an
  in-flight agent task you don't want to interrupt to run
  `tmux kill-server`.
- You're debugging *why* the tmux server is in the wrong context and want
  to verify the keychain entry itself is valid. Set
  `GH_TOKEN_NO_VALIDATE=1` when the network round-trip is what's failing.
- You hit the `gh codespace ssh: Permission denied (publickey)` error —
  the codespaces-key bootstrap in this skill is **independent** of the
  tmux-server issue and is still the right fix for that. See below.

## What this skill does

Two independent things:

1. **`scripts/load-gh-token.sh`** — reads gh's OAuth token directly from
   `~/Library/Keychains/login.keychain-db` using the `security` CLI with
   an explicit keychain-file path (which bypasses the search-list
   restriction), validates the token against the host's API, and exports
   it as `GH_TOKEN`. The agent shell's `gh` then uses `GH_TOKEN` and
   never tries to read the keychain. Per-shell, not permanent.
2. **`scripts/ensure-codespaces-key.sh`** — generates `~/.ssh/codespaces.auto`
   if missing, the ed25519 key that `gh codespace ssh/cp` expects but
   doesn't auto-create in non-interactive shells. Independent of the
   keychain story; still needed even after the LaunchAgent fix.

## Quick start — token fallback

```bash
# Default host github.com:
source scripts/load-gh-token.sh

# Or a specific host (e.g. GHE.com):
source scripts/load-gh-token.sh github.ghe.com

# Then use gh normally:
GH_HOST=github.ghe.com gh repo view owner/repo
```

The script validates the token against the host's API before exporting
it. If the keychain holds a stale token (common after `gh auth refresh`
rotates credentials mid-session), it fails loudly with the exact
`gh auth refresh -h <host>` command to run in your Terminal, instead of
handing back a token that will 401 on every downstream call.

The script also `unset GH_TOKEN` at function entry so all failure paths
leave the shell in a clean "no token" state — never stuck on a stale
value from an earlier successful load.

## Quick start — codespaces ssh key bootstrap

```bash
scripts/ensure-codespaces-key.sh
```

Idempotent, generates `~/.ssh/codespaces.auto` only if missing-or-empty,
and self-heals partial state from interrupted earlier runs. Required
once before `gh codespace ssh` / `gh codespace cp` will work from an
agent shell, since gh's interactive auto-create doesn't run there.

When `gh` can't read its token from the keyring for `gh codespace ssh`/`cp`,
export it with the loader in the same call — the same no-persist path the rest of
this skill uses, so the token never touches disk:
`source scripts/load-gh-token.sh <host> && gh codespace ssh ...`.

## Offline / airgap escape hatch

Token validation requires a round-trip to the host's API. To skip it
(temporarily offline but token is known good):

```bash
GH_TOKEN_NO_VALIDATE=1 source scripts/load-gh-token.sh github.com
```

The confirmation line will say `unvalidated` so the bypass is visible.

## Critical safety rule

Never run `security find-generic-password ... -g` to inspect the token
— `-g` prints the password in human-readable form and leaks it into
terminal output / chat transcripts. The script uses `-w` (write-only
password output) which prints only the password to stdout and pipes
straight into a variable with nothing logged, and passes the token to
curl via `--config -` (stdin) so it never appears in argv where
`ps -ax -o args` could see it.

The script never echoes the token itself, only a confirmation line
with the host, token length, and validation status.

### Caller-side leak hazards (agents read this)

The script is leak-safe, but the **caller** can still spill `GH_TOKEN`
into tool output (and therefore into the agent's context window /
transcript). After sourcing, in the same bash call, do NOT:

- `echo "$GH_TOKEN"`, `env`, or `printenv` (any of these will print it)
- Run `gh` with `--debug` or git with `GIT_CURL_VERBOSE=1` /
  `GIT_TRACE_CURL=1` — these log Authorization headers verbatim
- `set -x` / `bash -x` while `gh` runs
- Pipe `$GH_TOKEN` into a file or curl URL that ends up in the next
  read

Safe pattern is a single chained call:

```bash
source scripts/load-gh-token.sh github.ghe.com && \
  GH_HOST=github.ghe.com gh repo view owner/repo
```

Copilot CLI's bash tool spawns a fresh process per call, so an
`export GH_TOKEN` from one call does NOT persist to the next — the
blast radius is naturally bounded to one call. Don't try to "save"
the token across calls; just re-source the script.

## Manual fallback (one-liner)

If sourcing the script isn't possible:

```bash
RAW=$(security find-generic-password \
  -s "gh:github.ghe.com" -a "$USER" -w \
  ~/Library/Keychains/login.keychain-db 2>/dev/null)
export GH_TOKEN=$(echo "${RAW#go-keyring-base64:}" | base64 -D)
# Then validate manually — pass the token via --config (stdin) so it never
# appears in `ps -ax -o args` output:
printf 'header = "Authorization: token %s"\n' "$GH_TOKEN" | \
  curl -sS -o /dev/null -w '%{http_code}\n' -K - https://api.github.com/user  # expect 200
```

Replace `github.ghe.com` with `github.com` for dotcom. The keychain
service name is always `gh:<host>`.

## Prerequisites

The user must have already run `gh auth login -h <host>` in their
interactive Terminal at some point — this skill recovers an existing
token, it does not create one. If the keychain entry doesn't exist, the
script prints a clear error pointing to `gh auth login`.

## Pitfall — verify the parent process chain BEFORE invoking the SSH/tmux hypothesis

The tmux-server-in-wrong-context story above is real and load-bearing
for this skill, but it is **also a tempting pattern-match for any
macOS broker-auth failure** — including ones that have nothing to do
with tmux or SSH. Agents (and humans) reach for it whenever they see
"works in interactive Terminal, fails in agent shell," and that is
wrong often enough to embarrass you.

**Before invoking the SSH/tmux/Mach-bootstrap-namespace hypothesis for
any macOS auth failure (gh, MSAL/WAM brokers, keychain-backed
credentials, etc.), walk the actual parent process chain and confirm
the shell is in fact descended from an SSH login and/or a tmux server
started under one.** Two cheap probes:

```bash
# Walk parents up to PID 1, print PID/PPID/command:
pid=$$; while [ "$pid" != 1 ] && [ -n "$pid" ]; do
  ps -p "$pid" -o pid=,ppid=,command= 2>/dev/null
  pid=$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d ' ')
done

# Quick "am I in tmux at all" check:
[ -n "$TMUX" ] && echo "in tmux: $TMUX" || echo "not in tmux"
```

If the chain shows e.g. `Termius.app → Termius Helper → login -pf … →
zsh → copilot`, you are in a normal GUI-login Mach bootstrap namespace
and broker auth should work. The failure is somewhere else — a real
bug in the credential client, a swallowed exception in an MCP server,
a stale on-disk token cache, a missing fallback browser cookie — not
your tmux context. Ruling out the SSH/tmux story early prevents an
hour of red-herring debugging and prevents you from confidently
prescribing `tmux kill-server` to a user who isn't even running tmux.

The skill's "Read this first" section still applies whenever the
parent-chain walk *does* confirm an SSH-launched tmux server; this
pitfall just demands you confirm before prescribing.

## GHE.com specifics (github.ghe.com)

Repos on a **github.ghe.com** tenant
are a different host from github.com. `gh`/`git`'s default host is github.com,
so an un-hosted `gh issue create` / `gh api` / clone against a GHE repo fails
with **"Could not resolve to a Repository."** Always set `GH_HOST=github.ghe.com`
(or `-h github.ghe.com`). The keychain service name follows: `gh:github.ghe.com`.

The **Copilot CLI** itself also supports `ghe.com` data-residency tenants, but
only if you point it at the tenant host: set `COPILOT_GH_HOST` (Copilot-only) or
`GH_HOST` to the tenant host, or run `copilot login --host <tenant>`. Without it
the CLI defaults to github.com and 401s a tenant PAT.

### Pushing over HTTPS from an agent shell

When the login keychain isn't visible to the agent shell and you need to
`git push` over HTTPS, **extract the gh OAuth token and run the push in ONE bash
tool call** (Copilot CLI spawns a fresh process per call, so an exported token
does not survive to a second call). A **401 on
`/info/refs?service=git-upload-pack`** proves the credential was *rejected*, not
*absent* — i.e. the token is present but wrong (often a github.com token sent to
a GHE remote, or vice versa); it is not a "no credentials" problem.

One method works in this keychain-not-visible shell; a second works only once the
keychain is reachable (the `AUTHORIZATION: bearer` `http.extraheader` trick is
**rejected** by GHE as invalid credentials — don't use it):

- Feed the token to git through a credential helper, in one call. This is the
  method that survives the keychain-not-visible shell, since the loader reaches
  the token by explicit keychain path rather than the OS search list. The
  helper reads the exported variable at run time, so the token never appears in
  the command line, where `ps` would expose it to every user on the machine and
  git would echo it back in a failed-push error:
  ```bash
  source scripts/load-gh-token.sh <host> && \
    git -c credential.helper='!f() { echo username=x-access-token; echo password=$GH_TOKEN; }; f' \
      push https://<host>/ORG/REPO.git <branch>
  ```
- Only if the login keychain *is* reachable (e.g. you took the preferred
  tmux-restart fix and no longer need this skill), a one-time
  `gh auth setup-git --hostname <host>` lets a plain `git push` work through
  gh's own credential helper. That path depends on the very keychain visibility
  this section assumes you lack, so don't reach for it in a broken shell.

### Minting fine-grained PATs on GHE

When a token can't be recovered from keychain (or you need a scoped
non-interactive credential for `actions/checkout` of a private org repo):

- **Mint fine-grained PATs at the GHE domain itself** (github.ghe.com settings),
  **not** github.com — a github.com PAT is invalid against the GHE API.
- Some orgs **require admin approval** of new fine-grained PATs, and an
  org owner **cannot self-approve**. Workaround: in org settings temporarily
  toggle **"Do not require approval"** for fine-grained PATs, mint the token,
  then restore the setting (restoring does **not** revoke already-issued tokens).
- Scope for `actions/checkout` of one private org repo: resource owner = the
  **org**, "only select repositories" = that one repo, permission
  **Contents: Read** (Metadata is auto-added). No workflow scope, no Copilot.
- **Deploy keys may be org-disabled** (`POST .../keys` → 422 "Deploy
  keys are disabled") — use a fine-grained PAT or GitHub App token for checkout,
  never a deploy key.

## Scope

- macOS only. Linux / Windows use different credential stores and are
  out of scope.
- Read-only with respect to the keychain. Does not modify, delete, or
  rewrite gh's keychain entry.
- Sets `GH_TOKEN` for the current shell only; does not persist it to
  disk.
- Does NOT fix the underlying tmux-server-launched-from-wrong-context
  problem — for that, use the `tmux-keychain-bootstrap` LaunchAgent
  from `remote-agent-stack`.
- The codespaces key bootstrap writes `~/.ssh/codespaces.auto` once
  and is idempotent thereafter.
