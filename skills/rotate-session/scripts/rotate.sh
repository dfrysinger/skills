#!/usr/bin/env bash
# Replace the current tmux pane's Copilot session with one fresh seeded session.
#
#   rotate.sh <old-session-id> <prompt-file> [--consume-prompt]

set -uo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/rotate-after-turn.sh"
USAGE="usage: rotate.sh <old-session-id> <prompt-file> [--consume-prompt]"
OLD="${1:?$USAGE}"
PROMPT_FILE="${2:?$USAGE}"
CONSUME_PROMPT="${3:-}"
STATE="${ROTATE_STATE_ROOT:-$HOME/.copilot/session-state}"
LOG="${ROTATE_LOG:-/tmp/rotate-session-$OLD.log}"
TMP_ROOT="${TMPDIR:-/tmp}"
TMUX_BIN="${ROTATE_TMUX_BIN:-$(command -v tmux 2>/dev/null || true)}"

case "$CONSUME_PROMPT" in
  ""|--consume-prompt) ;;
  *) echo "rotate.sh: $USAGE" >&2; exit 1 ;;
esac

[ -n "${TMUX_PANE:-}" ] && [ -x "$TMUX_BIN" ] || {
  echo "rotate.sh: automated rotation requires the current Copilot session to run in tmux" >&2
  exit 1
}
[ -x "$HELPER" ] || {
  echo "rotate.sh: detached rotation helper is unavailable" >&2
  exit 1
}
[ -s "$PROMPT_FILE" ] || {
  echo "rotate.sh: prompt file is empty" >&2
  exit 1
}
[ -d "$STATE/$OLD" ] && [ -r "$STATE/$OLD/events.jsonl" ] || {
  echo "rotate.sh: no readable session $OLD" >&2
  exit 1
}

PROMPT="$(cat -- "$PROMPT_FILE")" || {
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

HOST_PID=""
ancestor="$PPID"
while [ "$ancestor" -gt 1 ]; do
  if [ -e "$STATE/$OLD/inuse.$ancestor.lock" ]; then
    HOST_PID="$ancestor"
    break
  fi
  ancestor="$(ps -o ppid= -p "$ancestor" 2>/dev/null | tr -d '[:space:]')"
  [ -n "$ancestor" ] || break
done
[ -n "$HOST_PID" ] || {
  echo "rotate.sh: current process does not belong to session $OLD" >&2
  exit 1
}

EVENT_OFFSET="$(
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path) = @ARGV;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    my $offset;
    while (my $line = <$fh>) {
      next unless substr($line, -1) eq "\n";
      my $event = eval { decode_json($line) };
      exit 3 unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      $offset = tell($fh) if ($event->{type} // "") eq "assistant.turn_start";
    }
    exit 4 unless defined $offset;
    print $offset;
  ' "$STATE/$OLD/events.jsonl"
)" || {
  echo "rotate.sh: could not find the current assistant turn boundary" >&2
  exit 1
}

PANE_NAME="$("$TMUX_BIN" display-message -p -t "$TMUX_PANE" '#{session_name}')"
PANE_CWD="$("$TMUX_BIN" display-message -p -t "$TMUX_PANE" '#{pane_current_path}')"
[ -n "$PANE_NAME" ] && [ -d "$PANE_CWD" ] || {
  echo "rotate.sh: could not resolve the current tmux pane" >&2
  exit 1
}

COPILOT_BIN="$(command -v copilot 2>/dev/null || true)"
[ -x "$COPILOT_BIN" ] || {
  echo "rotate.sh: copilot executable is unavailable" >&2
  exit 1
}

HOST_COMMAND="$(ps -ww -o command= -p "$HOST_PID" 2>/dev/null || true)"
HOST_OPTIONS="${HOST_COMMAND%% --interactive *}"
HOST_OPTIONS="${HOST_OPTIONS%% -i *}"
REMOTE_FLAG=""
PERMISSION_FLAG=""
set -f
set -- $HOST_OPTIONS
[ "$#" -gt 0 ] && shift
while [ "$#" -gt 0 ]; do
  case "$1" in
    --remote)
      REMOTE_FLAG="--remote"
      shift
      ;;
    --no-remote)
      REMOTE_FLAG="--no-remote"
      shift
      ;;
    --allow-all|--yolo)
      PERMISSION_FLAG="--allow-all"
      shift
      ;;
    --session-id|--name|-C)
      [ "$#" -ge 2 ] || {
        echo "rotate.sh: current Copilot launch has an incomplete $1 option" >&2
        exit 1
      }
      shift 2
      ;;
    --session-id=*|--name=*)
      shift
      ;;
    *)
      echo "rotate.sh: current Copilot launch option cannot be preserved safely: $1" >&2
      exit 1
      ;;
  esac
done
set +f

NEW="$(uuidgen 2>/dev/null | tr '[:upper:]' '[:lower:]')" || {
  echo "rotate.sh: could not allocate a replacement session ID" >&2
  exit 1
}
case "$NEW" in
  ????????-????-????-????-????????????) ;;
  *)
    echo "rotate.sh: generated replacement session ID is invalid" >&2
    exit 1
    ;;
esac

TMP_ROOT="${TMP_ROOT%/}"
[ -n "$TMP_ROOT" ] || TMP_ROOT=/
RECOVERY_FILE="$(mktemp "$TMP_ROOT/copilot-rotate-recovery-$OLD.XXXXXX")" || {
  echo "rotate.sh: could not create private prompt snapshot" >&2
  exit 1
}
if ! printf '%s' "$PROMPT" >"$RECOVERY_FILE"; then
  rm -f -- "$RECOVERY_FILE"
  echo "rotate.sh: could not write private prompt snapshot" >&2
  exit 1
fi

if ! exec 3>>"$LOG"; then
  rm -f -- "$RECOVERY_FILE"
  echo "rotate.sh: could not open rotation log; original prompt retained at $PROMPT_FILE" >&2
  exit 1
fi
printf '%s\n' \
  "=== rotate $OLD at $(date -Iseconds) ===" \
  "recovery snapshot: $RECOVERY_FILE (removed after replacement session and seed verification)" \
  "transport: tmux process replacement from pane $TMUX_PANE" \
  "replacement session: $NEW" >&3 || {
  exec 3>&-
  rm -f -- "$RECOVERY_FILE"
  echo "rotate.sh: could not write rotation log; original prompt retained at $PROMPT_FILE" >&2
  exit 1
}

LAUNCHER="$RECOVERY_FILE.launch.sh"
{
  printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail'
  printf 'prompt=$(cat -- %q)\n' "$RECOVERY_FILE"
  printf 'exec %q --session-id=%q --name=%q' "$COPILOT_BIN" "$NEW" "$PANE_NAME"
  [ -z "$REMOTE_FLAG" ] || printf ' %q' "$REMOTE_FLAG"
  [ -z "$PERMISSION_FLAG" ] || printf ' %q' "$PERMISSION_FLAG"
  printf ' -C %q --interactive "$prompt"\n' "$PANE_CWD"
} >"$LAUNCHER" || {
  exec 3>&-
  rm -f -- "$RECOVERY_FILE" "$LAUNCHER"
  echo "rotate.sh: could not write replacement launcher; original prompt retained at $PROMPT_FILE" >&2
  exit 1
}
chmod 700 "$LAUNCHER"

HELPER_SESSION="rotate-$(printf '%s' "$NEW" | cut -c1-8)"
LOCK_FILE="$STATE/$OLD/rotation.lock"
LOCK_READY="$RECOVERY_FILE.helper-ready"
INBOX_ROOT="${COPILOT_SESSION_INBOX_DIR:-$HOME/.copilot/session-inbox}"
printf -v HELPER_COMMAND '%q ' \
  /usr/bin/lockf -k -t 0 "$LOCK_FILE" \
  "$HELPER" "$STATE/$OLD/events.jsonl" "$EVENT_OFFSET" "$OLD" "$NEW" \
  "$TMUX_PANE" "$PANE_CWD" "$RECOVERY_FILE" "$LAUNCHER" "$LOG" \
  "$TMUX_BIN" "$STATE" "$LOCK_READY" "$INBOX_ROOT"

if ! "$TMUX_BIN" new-session -d -s "$HELPER_SESSION" "$HELPER_COMMAND"; then
  exec 3>&-
  rm -f -- "$LAUNCHER"
  echo "rotate.sh: could not start detached verifier; recovery copy preserved at $RECOVERY_FILE" >&2
  exit 1
fi

helper_ready=false
for _ in $(seq 1 40); do
  if [ -f "$LOCK_READY" ]; then
    helper_ready=true
    break
  fi
  sleep 0.05
done
[ "$helper_ready" = true ] || {
  "$TMUX_BIN" kill-session -t "$HELPER_SESSION" 2>/dev/null || true
  exec 3>&-
  rm -f -- "$LAUNCHER"
  echo "rotate.sh: another rotation is pending or the detached verifier could not acquire its lock; recovery copy preserved at $RECOVERY_FILE" >&2
  exit 1
}
: >"$LOCK_READY.ack" || {
  "$TMUX_BIN" kill-session -t "$HELPER_SESSION" 2>/dev/null || true
  exec 3>&-
  rm -f -- "$LAUNCHER"
  echo "rotate.sh: could not acknowledge the detached verifier; recovery copy preserved at $RECOVERY_FILE" >&2
  exit 1
}

if [ "$CONSUME_PROMPT" = "--consume-prompt" ] && ! rm -f -- "$PROMPT_FILE"; then
  "$TMUX_BIN" kill-session -t "$HELPER_SESSION" 2>/dev/null || true
  echo "RESULT: prompt consumption failed; recovery copy preserved at $RECOVERY_FILE" >&3
  exec 3>&-
  rm -f -- "$LAUNCHER"
  echo "rotate.sh: could not remove consumed prompt; recovery copy preserved at $RECOVERY_FILE" >&2
  exit 1
fi

printf 'detached verifier: %s\n' "$HELPER_SESSION" >&3
exec 3>&-
echo "rotation requested; result will be written to $LOG"
