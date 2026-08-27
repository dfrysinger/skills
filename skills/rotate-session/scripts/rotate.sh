#!/usr/bin/env bash
# Rotate the current Copilot CLI session into a fresh one seeded with a prompt.
#
#   rotate.sh <old-session-id> <prompt-file> [--consume-prompt]
#
# The seed is snapshotted and logged synchronously. A detached request then asks
# the session-inbox extension to create one new seeded session only after the
# old session reaches idle.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUEST_CLI="${SESSION_INBOX_REQUEST_CLI:-$SCRIPT_DIR/../../../extensions/session-inbox/request.mjs}"
USAGE="usage: rotate.sh <old-session-id> <prompt-file> [--consume-prompt]"
OLD="${1:?$USAGE}"
PROMPT_FILE="${2:?$USAGE}"
CONSUME_PROMPT="${3:-}"
STATE="$HOME/.copilot/session-state"
INSTANCES="$HOME/.copilot/session-inbox/instances"
LOG="${ROTATE_LOG:-/tmp/rotate-session-$OLD.log}"
TMP_ROOT="${TMPDIR:-/tmp}"
TMP_ROOT="${TMP_ROOT%/}"
TIMEOUT_SECONDS="${ROTATE_SESSION_TIMEOUT_SECONDS:-360}"
[ -n "$TMP_ROOT" ] || TMP_ROOT=/

case "$CONSUME_PROMPT" in
  ""|--consume-prompt) ;;
  *) echo "rotate.sh: $USAGE" >&2; exit 1 ;;
esac

[[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] &&
  ((TIMEOUT_SECONDS >= 1 && TIMEOUT_SECONDS <= 360)) || {
  echo "rotate.sh: timeout must be between 1 and 360 seconds" >&2
  exit 1
}
[ -r "$REQUEST_CLI" ] || {
  echo "rotate.sh: session-inbox request helper is unavailable" >&2
  exit 1
}
[ -s "$PROMPT_FILE" ] || { echo "rotate.sh: prompt file is empty" >&2; exit 1; }
[ -d "$STATE/$OLD" ] || { echo "rotate.sh: no such session $OLD" >&2; exit 1; }

PROMPT=$(cat -- "$PROMPT_FILE") || {
  echo "rotate.sh: could not read prompt file $PROMPT_FILE" >&2
  exit 1
}
case "$PROMPT" in
  *"$OLD"*) ;;
  *)
    echo "rotate.sh: prompt does not name expected session $OLD" >&2
    exit 1
    ;;
esac

umask 077
RECOVERY_FILE=$(mktemp "$TMP_ROOT/copilot-rotate-recovery-$OLD.XXXXXX") || {
  echo "rotate.sh: could not create private prompt snapshot" >&2
  exit 1
}
if ! printf '%s' "$PROMPT" >"$RECOVERY_FILE"; then
  if rm -f -- "$RECOVERY_FILE"; then
    echo "rotate.sh: could not write private prompt snapshot" >&2
  else
    echo "rotate.sh: could not write private prompt snapshot; incomplete copy may remain at $RECOVERY_FILE" >&2
  fi
  exit 1
fi

if ! exec 3>>"$LOG"; then
  if rm -f -- "$RECOVERY_FILE"; then
    echo "rotate.sh: could not open rotation log; original prompt retained at $PROMPT_FILE" >&2
  else
    echo "rotate.sh: could not open rotation log; original prompt retained at $PROMPT_FILE; recovery copy also remains at $RECOVERY_FILE" >&2
  fi
  exit 1
fi
if ! printf '%s\n' \
  "=== rotate $OLD at $(date -Iseconds) ===" \
  "recovery snapshot: $RECOVERY_FILE (removed after replacement session and seed verification)" >&3; then
  exec 3>&-
  if rm -f -- "$RECOVERY_FILE"; then
    echo "rotate.sh: could not write rotation log; original prompt retained at $PROMPT_FILE" >&2
  else
    echo "rotate.sh: could not write rotation log; original prompt retained at $PROMPT_FILE; recovery copy also remains at $RECOVERY_FILE" >&2
  fi
  exit 1
fi

if [ "$CONSUME_PROMPT" = "--consume-prompt" ] && ! rm -f -- "$PROMPT_FILE"; then
  echo "RESULT: prompt consumption failed; recovery copy preserved at $RECOVERY_FILE" >&3
  exec 3>&-
  echo "rotate.sh: could not remove consumed prompt; recovery copy preserved at $RECOVERY_FILE" >&2
  exit 1
fi

(
  exec 1>&3 2>&1
  exec 3>&-

  REQUEST_OUTPUT="$RECOVERY_FILE.request-output"
  request_status=0
  node "$REQUEST_CLI" new-session \
    --target-session "$OLD" \
    --prompt-file "$RECOVERY_FILE" \
    --timeout "$TIMEOUT_SECONDS" >"$REQUEST_OUTPUT" 2>&1 ||
    request_status=$?
  cat "$REQUEST_OUTPUT"

  read -r HOST_PID REQUEST_BOUNDARY < <(
    OLD="$OLD" /usr/bin/perl -MJSON::PP -ne '
      my $value = eval { decode_json($_) };
      next unless $value && ref($value) eq "HASH";
      if (($value->{status} // "") eq "completed" &&
          ($value->{sessionId} // "") eq $ENV{OLD} &&
          ($value->{result}{commandQueued} // 0)) {
        print(($value->{hostPid} // ""), "\t", ($value->{completedAt} // ""), "\n");
      }
    ' <"$REQUEST_OUTPUT"
  )
  if ! [[ "$HOST_PID" =~ ^[0-9]+$ ]] || [ -z "$REQUEST_BOUNDARY" ]; then
    REQUEST_ID="$(
      sed -n 's#^request: .*/\([^/]*\)\.json$#\1#p' "$REQUEST_OUTPUT" |
        tail -1
    )"
    MARKER="$HOME/.copilot/session-inbox/commands/$REQUEST_ID.json"
    read -r HOST_PID REQUEST_BOUNDARY < <(
      OLD="$OLD" /usr/bin/perl -MJSON::PP -0777 -e '
        my $value = eval { decode_json(<STDIN>) };
        if ($value && ref($value) eq "HASH" &&
            ($value->{sessionId} // "") eq $ENV{OLD}) {
          print(($value->{hostPid} // ""), "\t", ($value->{startedAt} // ""), "\n");
        }
      ' <"$MARKER" 2>/dev/null
    )
  fi
  [[ "$HOST_PID" =~ ^[0-9]+$ ]] && [ -n "$REQUEST_BOUNDARY" ] || {
    failure_status="$request_status"
    [ "$failure_status" -ne 0 ] || failure_status=1
    echo "RESULT: rotation request failed with exit status $request_status and no accepted local command lineage; prompt preserved at $RECOVERY_FILE; request output preserved at $REQUEST_OUTPUT"
    exit "$failure_status"
  }

  NEW=""
  for _ in $(seq 1 120); do
    NEW="$(
      /usr/bin/perl -MJSON::PP -e '
        use strict;
        use warnings;
        my ($old, $host_pid, $boundary, @paths) = @ARGV;
        my @matches;
        for my $path (@paths) {
          next unless -r $path;
          next unless (stat($path))[9] >= time - 15;
          open my $fh, "<", $path or next;
          my $value = eval { decode_json(do { local $/; <$fh> }) };
          next unless $value && ref($value) eq "HASH";
          next unless ($value->{hostPid} // "") eq $host_pid;
          next unless ($value->{updatedAt} // "") ge $boundary;
          next if ($value->{sessionId} // "") eq $old;
          push @matches, $value->{sessionId}
            if ($value->{sessionId} // "") ne "";
        }
        print $matches[0] if @matches == 1;
      ' "$OLD" "$HOST_PID" "$REQUEST_BOUNDARY" "$INSTANCES"/*.json 2>/dev/null
    )"
    [ -n "$NEW" ] && break
    sleep 0.5
  done
  [ -n "$NEW" ] || {
    echo "RESULT: /new was accepted but no unique replacement session appeared in the same local CLI process; prompt preserved at $RECOVERY_FILE; request output preserved at $REQUEST_OUTPUT"
    exit 1
  }

  SEEDED=false
  for _ in $(seq 1 120); do
    if [ -r "$STATE/$NEW/events.jsonl" ] &&
      PROMPT="$PROMPT" /usr/bin/perl -MJSON::PP -ne '
        our $matched;
        my $event = eval { decode_json($_) };
        next unless $event && ref($event) eq "HASH";
        my $data = $event->{data};
        if (($event->{type} // "") eq "user.message" &&
            $data && ref($data) eq "HASH" &&
            ($data->{content} // "") eq $ENV{PROMPT}) {
          $matched = 1;
          last;
        }
        END { exit($matched ? 0 : 1) }
      ' "$STATE/$NEW/events.jsonl"; then
      SEEDED=true
      break
    fi
    sleep 0.5
  done
  [ "$SEEDED" = true ] || {
    echo "RESULT: rotated to $NEW but its seed was not observed; prompt preserved at $RECOVERY_FILE; request output preserved at $REQUEST_OUTPUT"
    exit 1
  }

  if rm -f -- "$RECOVERY_FILE" "$REQUEST_OUTPUT"; then
    echo "RESULT: rotated to $NEW, seeded"
    exit 0
  fi
  echo "RESULT: rotated to $NEW and seeded, but recovery cleanup failed; prompt preserved at $RECOVERY_FILE"
  exit 1
) &

disown 2>/dev/null
exec 3>&-
echo "rotation requested; result will be written to $LOG"
