#!/usr/bin/env bash
# load-gh-token.sh — Read a gh CLI OAuth token out of the macOS login keychain
# and export it as GH_TOKEN so subprocesses (agent shells) can authenticate.
#
# Background: gh CLI on macOS stores tokens in ~/Library/Keychains/login.keychain-db.
# Agent-spawned shells usually inherit a restricted keychain search list that
# excludes the login keychain, so `gh auth status` fails with "invalid token"
# or "no oauth token found" even though the token exists and works in the
# user's interactive Terminal.
#
# Safety: uses `security ... -w` (write-only password output). NEVER use -g,
# which prints the password in human-readable form and would leak the token
# into terminal output / chat transcripts.
#
# Usage:
#   source load-gh-token.sh [host]          # default host: github.com
#   source load-gh-token.sh github.ghe.com
#
# After sourcing, GH_TOKEN is exported. Run gh with GH_HOST=<host> as needed:
#   GH_HOST=github.ghe.com gh repo view owner/repo

set -u

_load_gh_token() {
  local host="${1:-github.com}"
  local keychain="$HOME/Library/Keychains/login.keychain-db"

  # Invariant: leave the caller's shell with either a freshly-validated
  # GH_TOKEN exported, or no GH_TOKEN at all. Clearing upfront ensures every
  # early-return failure path obeys this without per-return bookkeeping.
  unset GH_TOKEN

  if [[ ! -f "$keychain" ]]; then
    echo "load-gh-token: login keychain not found at $keychain" >&2
    return 1
  fi

  local raw
  raw=$(security find-generic-password \
    -s "gh:$host" \
    -a "$USER" \
    -w "$keychain" 2>/dev/null) || {
      echo "load-gh-token: no keychain entry 'gh:$host' for user $USER" >&2
      echo "  (Run \`gh auth login -h $host\` in your interactive Terminal first.)" >&2
      return 1
    }

  # gh stores tokens as "go-keyring-base64:<base64>" — strip prefix and decode.
  local token
  if [[ "$raw" == go-keyring-base64:* ]]; then
    token=$(printf '%s' "${raw#go-keyring-base64:}" | base64 -D 2>/dev/null) || {
      echo "load-gh-token: failed to base64-decode keychain entry" >&2
      return 1
    }
  else
    token="$raw"
  fi

  if [[ -z "$token" ]]; then
    echo "load-gh-token: decoded token is empty" >&2
    return 1
  fi

  # Validate the token against the host's API before exporting. The keychain
  # may hold a stale token after `gh auth refresh` rotates credentials, and
  # silently exporting a 401-ing token wastes turns downstream. Set
  # GH_TOKEN_NO_VALIDATE=1 to skip (offline / airgap).
  local validated_msg="unvalidated"
  if [[ "${GH_TOKEN_NO_VALIDATE:-0}" != "1" ]]; then
    local api_url
    case "$host" in
      github.com)  api_url="https://api.github.com/user" ;;
      *.ghe.com)   api_url="https://api.$host/user" ;;
      *)           api_url="https://$host/api/v3/user" ;;  # GHES on-prem
    esac

    # Pass the token via curl --config (read from stdin) so it never appears
    # in argv where `ps -ax -o args` could see it.
    local http_code
    http_code=$(printf 'header = "Authorization: token %s"\n' "$token" | \
      curl -sS -o /dev/null -w '%{http_code}' \
        --max-time 10 \
        -K - \
        -H 'Accept: application/vnd.github+json' \
        "$api_url" 2>/dev/null) || http_code="000"

    if [[ "$http_code" != "200" ]]; then
      # Resolve our own path in a way that works under both bash and zsh
      # (zsh with nounset would explode on a bare $BASH_SOURCE).
      local source_path="${BASH_SOURCE[0]:-${0:-scripts/load-gh-token.sh}}"
      echo "load-gh-token: keychain token for '$host' is invalid (HTTP $http_code from $api_url)" >&2
      echo "  This usually means \`gh auth refresh\` rotated the token. Fix:" >&2
      echo "    In your interactive Terminal: gh auth refresh -h $host" >&2
      echo "    (or: gh auth logout -h $host && gh auth login -h $host)" >&2
      echo "  To skip validation (offline): GH_TOKEN_NO_VALIDATE=1 source $source_path $host" >&2
      return 1
    fi
    validated_msg="validated"
  fi

  export GH_TOKEN="$token"
  # Don't echo the token. Echo only a confirmation.
  echo "load-gh-token: GH_TOKEN set for host '$host' (${#token} chars, $validated_msg)"
}

_load_gh_token "$@"
