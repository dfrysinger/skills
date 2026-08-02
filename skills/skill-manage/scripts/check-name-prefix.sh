#!/usr/bin/env bash
# Report the shortest typeable prefix that reaches a candidate skill name and
# nothing else, across every skill installed on this machine.
#
#   check-name-prefix.sh <candidate-name> [more-candidates...]
#
# Exit 0 when every candidate has a unique 3- or 4-character prefix; exit 1 when
# one does not, printing what it collides with.
set -uo pipefail

roots=(
  "$HOME/.copilot/skills"
  "$HOME/.copilot/installed-plugins"
  "$HOME/code/skills/skills"
)

installed=$(
  for r in "${roots[@]}"; do
    [ -d "$r" ] || continue
    find "$r" -name SKILL.md -maxdepth 5 2>/dev/null |
      grep -v '/\.archive/' |
      sed 's|/SKILL.md$||; s|.*/||'
  done | sort -u
)

status=0
for cand in "$@"; do
  # A candidate already on disk is its own match, not a collision.
  others=$(printf '%s\n' "$installed" | grep -vx "$cand")
  best=""
  for n in 3 4; do
    for word in ${cand//-/ }; do
      [ "${#word}" -ge "$n" ] || continue
      p="${word:0:$n}"
      # Substring match anywhere, matching how the CLI completes a name.
      if ! printf '%s\n' "$others" | grep -q -- "$p"; then
        best="$p"
        break 2
      fi
    done
  done

  if [ -n "$best" ]; then
    lead="${cand%%-*}"
    if [ "$best" = "${lead:0:${#best}}" ]; then
      echo "ok   $cand -> /$best (leading word)"
    else
      echo "ok   $cand -> /$best (later word; leading word '$lead' is taken)"
    fi
  else
    echo "FAIL $cand — no unique 3- or 4-character prefix. Collisions:"
    for word in ${cand//-/ }; do
      [ "${#word}" -ge 3 ] || continue
      p="${word:0:3}"
      hits=$(printf '%s\n' "$others" | grep -- "$p" | paste -sd' ' -)
      [ -n "$hits" ] && echo "       /$p -> $hits"
    done
    status=1
  fi
done
exit $status
