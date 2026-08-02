#!/usr/bin/env bash
# pw-session.sh - wrapper that ensures Playwright + Chromium are installed in a
# user-scoped cache directory, then runs pw-session.mjs.
#
# Cache layout (override with COPILOT_AUTH_BROWSE_DIR):
#   ~/.cache/copilot-skills/authenticated-browse/
#     package.json
#     node_modules/playwright/...
#     pw-session.mjs                # copied from skill source so 'playwright' bare import resolves
#     profiles/<name>/              # persistent browser profile per site

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_DIR="${COPILOT_AUTH_BROWSE_DIR:-${HOME}/.cache/copilot-skills/authenticated-browse}"

if ! command -v node >/dev/null 2>&1; then
  echo "[authenticated-browse] node is required but not on PATH. Install Node.js 18+ and retry." >&2
  exit 127
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "[authenticated-browse] npm is required but not on PATH. Install Node.js (which ships with npm) and retry." >&2
  exit 127
fi

mkdir -p "$CACHE_DIR"

if [ ! -d "$CACHE_DIR/node_modules/playwright" ]; then
  echo "[authenticated-browse] First run: installing Playwright + Chromium under $CACHE_DIR (one-time, ~150-300MB)..." >&2
  (
    cd "$CACHE_DIR"
    [ -f package.json ] || npm init -y >/dev/null
    npm install --silent --no-audit --no-fund playwright >&2
    npx --yes playwright install chromium >&2
  )
fi

# Keep the runtime script colocated with node_modules so the bare 'playwright'
# import in pw-session.mjs resolves to the cached install. Atomic copy via mv
# so concurrent invocations don't read a half-written file.
TMP_MJS="$CACHE_DIR/.pw-session.mjs.$$.tmp"
cp -f "$SRC_DIR/pw-session.mjs" "$TMP_MJS"
mv -f "$TMP_MJS" "$CACHE_DIR/pw-session.mjs"

exec node "$CACHE_DIR/pw-session.mjs" "$@"
