#!/usr/bin/env bash
# validate-skill.sh — HARDLINE skill-authoring rule validator.
#
# Lifted from Hermes Agent's tools/skill_manager_tool.py validation paths
# (_validate_name, _validate_frontmatter, _validate_content_size, ALLOWED_SUBDIRS,
# VALID_NAME_RE, MAX_*). Run after every skill-create or skill-manage edit.
#
# Usage:  validate-skill.sh /path/to/SKILL.md
# Exit:   0 = pass, 1 = validation failed (errors printed to stderr).

set -u

ERR_COUNT=0

err() { printf 'ERROR: %s\n' "$1" >&2; ERR_COUNT=$((ERR_COUNT + 1)); }

if [[ $# -ne 1 ]]; then
  echo "usage: $(basename "$0") /path/to/SKILL.md" >&2
  exit 2
fi

SKILL_MD="$1"

if [[ ! -f "$SKILL_MD" ]]; then
  err "SKILL.md not found at $SKILL_MD"
  exit 1
fi

# Skill name = parent directory name.
SKILL_DIR="$(dirname "$SKILL_MD")"
SKILL_NAME="$(basename "$SKILL_DIR")"

# Rule 7: name regex + length.
if ! [[ "$SKILL_NAME" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  err "name '$SKILL_NAME' violates regex ^[a-z0-9][a-z0-9._-]*$ (lowercase, starts with alnum, only - . _)"
fi
if [[ ${#SKILL_NAME} -gt 64 ]]; then
  err "name '$SKILL_NAME' exceeds 64 chars (got ${#SKILL_NAME})"
fi

# Rule 6: frontmatter — must start with --- and have closing ---.
FIRST_LINE="$(head -1 "$SKILL_MD")"
if [[ "$FIRST_LINE" != "---" ]]; then
  err "frontmatter missing — first line must be '---' (got '$FIRST_LINE')"
fi

# Find closing ---.
CLOSE_LINE=$(awk 'NR>1 && /^---[[:space:]]*$/{print NR; exit}' "$SKILL_MD")
if [[ -z "$CLOSE_LINE" ]]; then
  err "frontmatter not closed — need a second '---' line after the YAML block"
else
  FM="$(sed -n "2,$((CLOSE_LINE - 1))p" "$SKILL_MD")"

  # Required: name, description.
  NAME_FM=$(printf '%s\n' "$FM" | awk -F': *' '/^name:/{print $2; exit}' | tr -d '"'"'")
  DESC_FM=$(printf '%s\n' "$FM" | awk -F': *' '/^description:/{ $1=""; sub(/^ */,""); print; exit}' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

  if [[ -z "$NAME_FM" ]]; then
    err "frontmatter missing required field: name"
  elif [[ "$NAME_FM" != "$SKILL_NAME" ]]; then
    err "frontmatter name '$NAME_FM' does not match directory name '$SKILL_NAME'"
  fi

  if [[ -z "$DESC_FM" ]]; then
    err "frontmatter missing required field: description"
  else
    # Rule 1: description ≤ 1024 chars (per agentskills.io spec) and should include
    # "Use when…" or similar trigger phrasing. Trigger check is soft (warn-only).
    if [[ ${#DESC_FM} -gt 1024 ]]; then
      err "description is ${#DESC_FM} chars, exceeds 1024 (cap from Hermes MAX_DESCRIPTION_LENGTH)"
    fi
    if [[ ${#DESC_FM} -lt 30 ]]; then
      err "description is only ${#DESC_FM} chars — too vague for the agent to pick it (state capability + 'Use when…')"
    fi
    # Only a model-invoked skill needs triggers. A user-invoked skill
    # (disable-model-invocation: true) is reached by name alone, and its
    # description is human-facing — trigger phrasing there is dead weight.
    if grep -qE '^disable-model-invocation:[[:space:]]*true[[:space:]]*$' "$SKILL_MD"; then
      if [[ ${#DESC_FM} -gt 200 ]]; then
        printf 'WARN:  user-invoked skill has a %s-char description; only you read it, so one line is enough.\n' "${#DESC_FM}" >&2
      fi
    elif ! grep -qiE 'use when|when.*(user|you)|invoke when' <<<"$DESC_FM"; then
      printf 'WARN:  description has no "Use when…" trigger phrasing; agent may not pick this skill reliably.\n' >&2
    fi
  fi

  # Body must exist after frontmatter.
  BODY="$(sed -n "$((CLOSE_LINE + 1)),\$p" "$SKILL_MD" | sed '/^[[:space:]]*$/d')"
  if [[ -z "$BODY" ]]; then
    err "SKILL.md has frontmatter but empty body — needs instructions after the closing '---'"
  fi
fi

# Rule 8: size cap on SKILL.md.
SIZE=$(wc -c < "$SKILL_MD" | tr -d ' ')
if [[ "$SIZE" -gt 100000 ]]; then
  err "SKILL.md is $SIZE bytes, exceeds 100000-char cap (split into references/)"
fi

# Rule 5/8: supporting files must be under allowed subdirs, none > 1 MiB.
ALLOWED='references templates scripts assets'
if [[ -d "$SKILL_DIR" ]]; then
  while IFS= read -r -d '' f; do
    REL="${f#$SKILL_DIR/}"
    TOP="${REL%%/*}"
    case " $ALLOWED " in
      *" $TOP "*) ;;
      *)
        # Allow SKILL.md and root metadata sidecars used by skill tooling.
        if [[ "$REL" != "SKILL.md" && "$REL" != ".pinned" && "$REL" != ".agent-created" && "$REL" != ".agent-created.json" && "$REL" != ".promotion-reviewed.json" && "$REL" != ".skill-evaluation-cases.json" ]]; then
          err "stray file '$REL' — supporting files must be under one of: $ALLOWED"
        fi
        ;;
    esac
    FSIZE=$(wc -c < "$f" | tr -d ' ')
    if [[ "$FSIZE" -gt 1048576 ]]; then
      err "$REL is $FSIZE bytes, exceeds 1 MiB cap"
    fi
  done < <(find "$SKILL_DIR" -type f -print0)
fi

# Path traversal in script paths inside SKILL.md prose.
if grep -nE '\.\./\.\./|\.\.\\\.\.\\' "$SKILL_MD" >/dev/null; then
  err "SKILL.md contains '..' path traversal — disallowed by skill_manager_tool.py"
fi

if [[ "$ERR_COUNT" -gt 0 ]]; then
  printf '\n%d validation error(s) in %s\n' "$ERR_COUNT" "$SKILL_MD" >&2
  exit 1
fi

DESC_LEN="${#DESC_FM}"
printf 'OK: %s (name=%s, description=%d chars, body=%d bytes)\n' \
  "$SKILL_MD" "$SKILL_NAME" "$DESC_LEN" "$SIZE"
