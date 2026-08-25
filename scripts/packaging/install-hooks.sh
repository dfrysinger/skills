#!/bin/sh
# Bootstrap for a machine that will commit to this repo.
#
# This is load-bearing, not convenience. github.com has no pre-receive hook at
# this tier and custom-pattern push protection needs a paid add-on, so the
# remote cannot reject a secret before accepting it. Installing this hook is
# the only prevention a second machine gets; cloning alone does not install it.
set -e

root=$(git rev-parse --show-toplevel)
hook="$root/.git/hooks/pre-commit"

# Same dual layout as the hook itself: owner repo vs consumer repo.
if [ -d "$root/scripts/packaging" ]; then
  pkg="$root/scripts/packaging"
elif [ -d "$root/packaging/scripts/packaging" ]; then
  pkg="$root/packaging/scripts/packaging"
else
  echo "install-hooks: cannot find the packaging tree." >&2
  exit 1
fi

if [ -e "$hook" ] && ! grep -q "scan-secrets.mjs" "$hook" 2>/dev/null; then
  echo "install-hooks: $hook exists and is not ours; move it aside first." >&2
  exit 1
fi

cp "$pkg/pre-commit" "$hook"
chmod +x "$hook"
echo "install-hooks: secret gate installed at .git/hooks/pre-commit"

# Prove it is live rather than merely present, so bootstrap failure is loud
# instead of silent. A hook that is copied but not executable, or whose
# dependencies are missing, would otherwise look installed and gate nothing.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# Assembled at runtime so this file carries no literal the gate would match.
# A fixture-syntax canary would be skipped by the scanner and prove nothing;
# a real-shaped literal would make this very file uncommittable. Splitting the
# key from its value satisfies both.
printf 'access_%s: %s\n' 'code' 'A1b2C3d4' > "$tmp/canary.md"
if node "$pkg/scan-secrets.mjs" --visibility=private "$tmp/canary.md" >/dev/null 2>&1; then
  echo "install-hooks: SELF-TEST FAILED - scanner accepted a planted tier-1 token." >&2
  exit 1
fi
echo "install-hooks: self-test passed (planted tier-1 token is rejected)"
