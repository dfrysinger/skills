#!/usr/bin/env bash
# Rename a skill and every reference to it, across both skill roots.
#
#   rename-skill.sh <old-name> <new-name> [--no-commit]
#
# Moves the directory, updates the frontmatter name and the H1, rewrites
# references in both roots (backticked mentions, skills/<name>/ paths,
# /dfrysinger-skills:<name> invocations, and [<name>](...) links), re-registers
# the skill in the PUBLIC plugin manifest, validates, and commits each repo it
# touched. The installed plugin cache is not edited — it is rebuilt by sync.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLIC="${SKILLS_REPO_ROOT:-$HOME/code/skills}"
LOCAL="${SKILLS_LOCAL_ROOT:-$HOME/.copilot/skills}"

die() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 2 ] || die "usage: $(basename "$0") <old-name> <new-name> [--no-commit]"
OLD="$1"; NEW="$2"; shift 2
COMMIT=1
[ "${1:-}" = "--no-commit" ] && COMMIT=0

[ "$OLD" = "$NEW" ] && die "old and new names are identical"
[[ "$NEW" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || die "'$NEW' violates ^[a-z0-9][a-z0-9._-]*$"
[ "${#NEW}" -le 64 ] || die "'$NEW' exceeds 64 characters"

# Locate the skill and the root that owns it.
if   [ -f "$PUBLIC/skills/$OLD/SKILL.md" ]; then ROOT="$PUBLIC"; DIR="$PUBLIC/skills/$OLD"
elif [ -f "$LOCAL/$OLD/SKILL.md" ];        then ROOT="$LOCAL";  DIR="$LOCAL/$OLD"
else die "no live skill named '$OLD' in $PUBLIC/skills or $LOCAL"
fi
NEWDIR="$(dirname "$DIR")/$NEW"
[ -e "$NEWDIR" ] && die "'$NEW' already exists at $NEWDIR"
for c in "$PUBLIC/skills/$NEW/SKILL.md" "$LOCAL/$NEW/SKILL.md"; do
  [ -f "$c" ] && die "'$NEW' is already taken by $c"
done

git -C "$ROOT" mv "$DIR" "$NEWDIR"
sed -i '' "1,20s/^name: $OLD\$/name: $NEW/" "$NEWDIR/SKILL.md"
sed -i '' "s/^# $OLD\$/# $NEW/" "$NEWDIR/SKILL.md"

# Rewrite references in both roots. Only forms that name a skill are touched;
# prose that happens to contain the words is left alone.
touched=()
for R in "$PUBLIC" "$LOCAL"; do
  [ -d "$R" ] || continue
  changed=0
  while IFS= read -r f; do
    before=$(shasum "$f" | cut -d' ' -f1)
    sed -i '' \
      -e "s/\`$OLD\`/\`$NEW\`/g" \
      -e "s|skills/$OLD/|skills/$NEW/|g" \
      -e "s|/dfrysinger-skills:$OLD|/dfrysinger-skills:$NEW|g" \
      -e "s|\[$OLD\](|[$NEW](|g" \
      "$f"
    [ "$(shasum "$f" | cut -d' ' -f1)" = "$before" ] || changed=1
  done < <(grep -rl -- "$OLD" "$R" --include='*.md' --include='*.txt' 2>/dev/null |
             grep -v '/\.git/\|/\.archive/' || true)
  [ "$changed" -eq 1 ] && touched+=("$R")
done

# The PUBLIC manifest lists every skill by path.
MANIFEST="$PUBLIC/.claude-plugin/plugin.json"
if [ "$ROOT" = "$PUBLIC" ] && [ -f "$MANIFEST" ]; then
  sed -i '' "s|\"./skills/$OLD\"|\"./skills/$NEW\"|" "$MANIFEST"
  touched+=("$PUBLIC")
  if [ -x "$PUBLIC/scripts/validate-plugin-manifests.mjs" ] || [ -f "$PUBLIC/scripts/validate-plugin-manifests.mjs" ]; then
    node "$PUBLIC/scripts/validate-plugin-manifests.mjs" || die "plugin manifests inconsistent after rename"
  fi
fi

"$HERE/validate-skill.sh" "$NEWDIR/SKILL.md" || die "validation failed after rename"

stale=$(grep -rn -- "\`$OLD\`\|skills/$OLD/\|dfrysinger-skills:$OLD" "$PUBLIC" "$LOCAL" \
          --include='*.md' --include='*.txt' --include='*.json' 2>/dev/null |
        grep -v '/\.git/\|/\.archive/' || true)
[ -n "$stale" ] && { echo "$stale"; die "stale references to '$OLD' remain"; }

if [ "$COMMIT" -eq 1 ]; then
  for R in $(printf '%s\n' "${touched[@]}" "$ROOT" | sort -u); do
    git -C "$R" add -A
    git -C "$R" diff --cached --quiet || \
      git -C "$R" commit -q -m "skills: rename $OLD -> $NEW"
  done
fi

echo "renamed $OLD -> $NEW in $ROOT"
echo "next: bump the PUBLIC version, push, and rsync the plugin cache"
