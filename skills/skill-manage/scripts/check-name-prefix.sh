#!/usr/bin/env bash
# Report the shortest typeable prefix that reaches a candidate skill name and
# nothing else, across every skill installed on this machine.
#
#   check-name-prefix.sh [--agent-only] <candidate-name> [more-candidates...]
#
# The prefix only has to be short for a skill a human types. A skill reached
# solely by an agent, a script, or a scheduled job spends no keystrokes, so it
# is exempt: pass --agent-only for a name not yet on disk, or set
# `hand-invoked: false` in its frontmatter once it exists.
#
# Exit 0 when every candidate that needs a prefix has one; exit 1 when one does
# not, printing what it collides with. An exempt candidate never fails.
set -uo pipefail

agent_only=0
[ "${1:-}" = "--agent-only" ] && { agent_only=1; shift; }

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
  # A skill nobody types spends no keystrokes, so it needs no short prefix.
  exempt=$agent_only
  if [ "$exempt" -eq 0 ]; then
    for r in "${roots[@]}"; do
      while IFS= read -r f; do
        [ -n "$f" ] || continue
        if sed -n '1,/^---$/p' "$f" | grep -qi '^hand-invoked: *false'; then
          exempt=1
        fi
      done < <(find "$r" -maxdepth 5 -path "*/$cand/SKILL.md" 2>/dev/null |
                 grep -v '/\.archive/')
    done
  fi
  if [ "$exempt" -eq 1 ]; then
    echo "n/a  $cand — hand-invoked: false, so no prefix needed"
    continue
  fi

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
