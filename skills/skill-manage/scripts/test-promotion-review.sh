#!/usr/bin/env bash
# Deterministic checks for the promotion public-safety inventory.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/promotion-review-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
passes=0

pass() { echo "PASS  $*"; passes=$((passes + 1)); }
fail() { echo "FAIL  $*" >&2; exit 1; }

make_skill() {
  local root="$1" name="$2"
  mkdir -p "$root/$name/references"
  cat > "$root/$name/SKILL.md" <<EOF
---
name: $name
description: Promotion fixture. Use when testing reviewed inventories.
---

# $name

Safe procedure.
EOF
  echo "Safe reference." > "$root/$name/references/example.md"
  touch "$root/$name/.agent-created"
  echo '{}' > "$root/$name/.agent-created.json"
}

LOCAL="$TMP/local"
PUBLIC="$TMP/public"
mkdir -p "$LOCAL" "$PUBLIC/skills" "$PUBLIC/.claude-plugin"
git -C "$LOCAL" init -q
git -C "$PUBLIC" init -q
for root in "$LOCAL" "$PUBLIC"; do
  git -C "$root" config user.email test@example.com
  git -C "$root" config user.name Test
done
echo '{"skills":[]}' > "$PUBLIC/.claude-plugin/plugin.json"
git -C "$PUBLIC" add .claude-plugin/plugin.json
git -C "$PUBLIC" commit -qm base

make_skill "$LOCAL" private-skill
echo "PRIVATE_SENTINEL" >> "$LOCAL/private-skill/references/example.md"
if "$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/private-skill" \
  --reviewer claude --reviewer gpt >/dev/null 2>&1; then
  fail "private support-file sentinel was approved"
fi
pass "private support-file sentinel blocks approval"

make_skill "$LOCAL" nested-sidecar
echo "PRIVATE_SENTINEL" > "$LOCAL/nested-sidecar/references/.promotion-reviewed.json"
if "$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/nested-sidecar" \
  --reviewer claude --reviewer gpt >/dev/null 2>&1; then
  fail "nested reserved promotion sidecar was approved"
fi
pass "nested reserved sidecars fail closed"

make_skill "$LOCAL" safe-skill
if "$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/safe-skill" \
  --reviewer same --reviewer same >/dev/null 2>&1; then
  fail "single reviewer identity was approved"
fi
"$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/safe-skill" \
  --reviewer claude --reviewer gpt >/dev/null
"$SCRIPT_DIR/promotion-review.py" verify "$LOCAL/safe-skill" >/dev/null
echo "changed after review" >> "$LOCAL/safe-skill/references/example.md"
if "$SCRIPT_DIR/promotion-review.py" verify "$LOCAL/safe-skill" >/dev/null 2>&1; then
  fail "stale inventory passed"
fi
pass "promotion inventory requires two reviewers and exact hashes"

git -C "$LOCAL" add safe-skill
git -C "$LOCAL" commit -qm "add safe skill"
"$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/safe-skill" \
  --reviewer claude --reviewer gpt >/dev/null
git -C "$LOCAL" add safe-skill/.promotion-reviewed.json
git -C "$LOCAL" commit -qm "approve safe skill"
SKILLS_LOCAL_ROOT="$LOCAL" SKILLS_REPO_ROOT="$PUBLIC" SKILLS_STATE_DIR="$TMP/state" \
  SKILLS_COAUTHOR_TRAILER="Reviewed-by: fixture" \
  "$SCRIPT_DIR/promote-skill.sh" safe-skill >/dev/null
[[ -f "$PUBLIC/skills/safe-skill/SKILL.md" ]] || fail "promoted skill missing"
if find "$PUBLIC/skills/safe-skill" -name '.agent-created*' -print -quit | grep -q .; then
  fail "public skill retained agent provenance"
fi
[[ ! -f "$PUBLIC/skills/safe-skill/.promotion-reviewed.json" ]] ||
  fail "public skill retained private review manifest"
pass "promotion strips provenance and the local review manifest"

make_skill "$LOCAL" rollback-skill
git -C "$LOCAL" add rollback-skill
git -C "$LOCAL" commit -qm "add rollback skill"
"$SCRIPT_DIR/promotion-review.py" approve "$LOCAL/rollback-skill" \
  --reviewer claude --reviewer gpt >/dev/null
git -C "$LOCAL" add rollback-skill/.promotion-reviewed.json
git -C "$LOCAL" commit -qm "approve rollback skill"
cat > "$PUBLIC/.git/hooks/pre-commit" <<'SH'
#!/usr/bin/env bash
exit 1
SH
chmod +x "$PUBLIC/.git/hooks/pre-commit"
if SKILLS_LOCAL_ROOT="$LOCAL" SKILLS_REPO_ROOT="$PUBLIC" SKILLS_STATE_DIR="$TMP/state" \
  SKILLS_COAUTHOR_TRAILER="Reviewed-by: fixture" \
  "$SCRIPT_DIR/promote-skill.sh" rollback-skill >/dev/null 2>&1; then
  fail "forced public commit failure returned success"
fi
[[ -f "$LOCAL/rollback-skill/.agent-created" ]] ||
  fail "failed promotion lost authority marker"
[[ -f "$LOCAL/rollback-skill/.agent-created.json" ]] ||
  fail "failed promotion lost evidence envelope"
[[ -f "$LOCAL/rollback-skill/.promotion-reviewed.json" ]] ||
  fail "failed promotion lost review manifest"
[[ ! -e "$PUBLIC/skills/rollback-skill" ]] ||
  fail "failed promotion left the skill in the public tree"
pass "failed promotion restores local provenance"

echo "PASS  $passes deterministic promotion checks"
