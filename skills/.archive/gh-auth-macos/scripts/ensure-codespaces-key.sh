#!/usr/bin/env bash
# ensure-codespaces-key.sh — Guarantee ~/.ssh/codespaces.auto exists before
# the first `gh codespace ssh` / `gh codespace cp` invocation.
#
# Background: gh expects a dedicated managed ed25519 key at
# ~/.ssh/codespaces.auto (referenced as IdentityFile in `gh codespace ssh
# --config` output). In an interactive Terminal gh auto-creates it on first
# use, but in a non-interactive agent shell it does NOT, so ssh offers no
# key and the Codespace bounces the connection with "Permission denied
# (publickey)". This script generates the key once, idempotently.
#
# Usage:
#   ./ensure-codespaces-key.sh          # silent if key exists
#   ./ensure-codespaces-key.sh --print  # print path on success

set -euo pipefail

KEY="$HOME/.ssh/codespaces.auto"
PRINT=0
[[ "${1:-}" == "--print" ]] && PRINT=1

# Fast path requires a private key that is non-empty AND actually parses.
# Testing only for existence accepts a zero-byte or truncated key left by an
# interrupted run, which then fails at connect time as "Permission denied
# (publickey)" — the very error this script exists to prevent. Redirect stdin
# so a passphrase-protected key fails instead of hanging on the prompt.
if [[ -s "$KEY" && -s "$KEY.pub" ]] && ssh-keygen -y -f "$KEY" >/dev/null 2>&1 </dev/null; then
  [[ "$PRINT" == "1" ]] && echo "$KEY"
  exit 0
fi

# An unusable private key can't be repaired, and ssh-keygen would prompt to
# overwrite it. Move it aside so the generate path below has a clean slate.
if [[ -f "$KEY" ]] && ! ssh-keygen -y -f "$KEY" >/dev/null 2>&1 </dev/null; then
  BAD="$KEY.unusable-$(date +%Y%m%dT%H%M%S)"
  echo "ensure-codespaces-key: $KEY does not parse; moving to $BAD" >&2
  mv "$KEY" "$BAD"
  rm -f "$KEY.pub"
fi

# Partial-state recovery: handle each half-missing-or-empty case explicitly.
# Without this, ssh-keygen would prompt "Overwrite (y/n)?" against the
# existing private key, read EOF from non-interactive stdin, and exit 1
# under `set -e` — breaking the SKILL's idempotency promise. The fast path
# above uses `-s` (non-empty) on the public key so that a zero-byte .pub
# left behind by an interrupted earlier run is treated as "missing" and
# recovered here, not silently accepted.
if [[ -f "$KEY" && ( ! -f "$KEY.pub" || ! -s "$KEY.pub" ) ]]; then
  echo "ensure-codespaces-key: regenerating missing $KEY.pub from existing private key" >&2
  # Write to a temp file first so a failed `ssh-keygen -y` (e.g. corrupt or
  # password-protected private key) doesn't leave an empty $KEY.pub behind
  # that would make the next invocation's all-present fast path lie.
  tmp_pub=$(mktemp "${KEY}.pub.XXXXXX")
  if ssh-keygen -y -f "$KEY" > "$tmp_pub" && [[ -s "$tmp_pub" ]]; then
    chmod 644 "$tmp_pub"
    mv "$tmp_pub" "$KEY.pub"
  else
    rm -f "$tmp_pub"
    echo "ensure-codespaces-key: failed to derive public key from $KEY" >&2
    echo "  The private key may be passphrase-protected or corrupt." >&2
    exit 1
  fi
  [[ "$PRINT" == "1" ]] && echo "$KEY"
  exit 0
fi

if [[ ! -f "$KEY" && -f "$KEY.pub" ]]; then
  # Public-only state is unsafe to silently overwrite (the user may have
  # placed it deliberately, e.g. mid-migration). Bail with guidance.
  echo "ensure-codespaces-key: $KEY.pub exists but $KEY is missing" >&2
  echo "  Refusing to silently regenerate. Remove $KEY.pub first, then re-run." >&2
  exit 1
fi

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

# Generate without prompting. -N "" = empty passphrase (gh manages this key
# and must load it non-interactively; matches gh's own behavior when it
# auto-creates this key in an interactive Terminal).
ssh-keygen -t ed25519 -f "$KEY" -N "" -C "codespaces-auto" -q

chmod 600 "$KEY"
chmod 644 "$KEY.pub"

echo "ensure-codespaces-key: generated $KEY" >&2
[[ "$PRINT" == "1" ]] && echo "$KEY"
