#!/usr/bin/env bash
# Wait for the authorizing turn to end, replace the pane, and verify the seed.

set -euo pipefail
umask 077

[ "$#" -eq 13 ] || {
  echo "usage: rotate-after-turn.sh EVENTS OFFSET OLD NEW PANE CWD RECOVERY LAUNCHER LOG TMUX STATE READY INBOX" >&2
  exit 2
}

EVENTS="$1"
OFFSET="$2"
OLD="$3"
NEW="$4"
PANE="$5"
CWD="$6"
RECOVERY="$7"
LAUNCHER="$8"
LOG="$9"
TMUX_BIN="${10}"
STATE="${11}"
READY="${12}"
INBOX="${13}"
BARRIER="$STATE/$OLD/rotation.barrier"

exec >>"$LOG" 2>&1
RESULT_RECORDED=false
INPUT_DISABLED=false
REPLACED=false
record_result() {
  RESULT_RECORDED=true
  echo "RESULT: $*"
}
cleanup() {
  status=$?
  if [ "$INPUT_DISABLED" = true ]; then
    "$TMUX_BIN" select-pane -e -t "$PANE" 2>/dev/null || true
  fi
  if [ "$REPLACED" != true ]; then
    rm -f -- "$BARRIER"
  fi
  if [ "$RESULT_RECORDED" != true ]; then
    echo "RESULT: rotation verifier failed unexpectedly (exit $status); prompt preserved at $RECOVERY"
  fi
  rm -f -- "$READY" "$READY.ack"
}
trap cleanup EXIT
: >"$READY"
acknowledged=false
for _ in $(seq 1 40); do
  if [ -f "$READY.ack" ]; then
    acknowledged=true
    break
  fi
  sleep 0.05
done
[ "$acknowledged" = true ] || {
  record_result "rotation launcher did not acknowledge the verifier; prompt preserved at $RECOVERY"
  exit 1
}

turn_probe() {
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($path, $offset) = @ARGV;
    open my $fh, "<", $path or exit 2;
    binmode $fh;
    seek($fh, $offset, 0) or exit 2;
    my $saw_turn_end = 0;
    while (my $line = <$fh>) {
      next unless substr($line, -1) eq "\n";
      my $event = eval { decode_json($line) };
      exit 3 unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      my $type = $event->{type} // "";
      if ($type eq "user.message") {
        print "cancel\n";
        exit;
      }
      $saw_turn_end = 1 if $type eq "assistant.turn_end";
    }
    print $saw_turn_end ? "ready\n" : "wait\n";
  ' "$EVENTS" "$OFFSET"
}

probe=""
for _ in $(seq 1 720); do
  probe="$(turn_probe)"
  case "$probe" in
    ready) break ;;
    cancel)
      record_result "rotation cancelled because new user activity arrived before replacement; prompt preserved at $RECOVERY"
      exit 1
      ;;
    wait) ;;
    *)
      record_result "rotation authorization probe failed; prompt preserved at $RECOVERY"
      exit 1
      ;;
  esac
  sleep 0.25
done
[ "$probe" = ready ] || {
  record_result "rotation timed out waiting for the authorizing turn to end; prompt preserved at $RECOVERY"
  exit 1
}

: >"$BARRIER"
DELIVERY_LOCK="$STATE/$OLD/delivery.lock"
exec 8>"$DELIVERY_LOCK"
if ! /usr/bin/lockf -t 10 8; then
  record_result "rotation cancelled because session-inbox publication could not be quiesced; prompt preserved at $RECOVERY"
  exit 1
fi
inbox_status="$(/usr/bin/perl -MJSON::PP -e '
  use strict;
  use warnings;
  my ($root, $session_id) = @ARGV;
  for my $phase ("pending", "processing") {
    my $dir = "$root/$phase";
    my $dh;
    if (!opendir($dh, $dir)) {
      next if $!{ENOENT};
      print "error\n";
      exit;
    }
    while (my $name = readdir $dh) {
      next unless $name =~ /\.json\z/;
      open my $fh, "<", "$dir/$name" or next;
      local $/;
      my $request = eval { decode_json(<$fh>) };
      next unless $request && ref($request) eq "HASH";
      my $target = $request->{target};
      if (
        $target && ref($target) eq "HASH" &&
        ($target->{sessionId} // "") eq $session_id
      ) {
        print "busy\n";
        exit;
      }
    }
  }
  print "clear\n";
' "$INBOX" "$OLD")"
exec 8>&-
case "$inbox_status" in
  busy)
    record_result "rotation cancelled because session-inbox work is in flight; prompt preserved at $RECOVERY"
    exit 1
    ;;
  clear) ;;
  *)
    record_result "rotation cancelled because session-inbox quiescence could not be verified; prompt preserved at $RECOVERY"
    exit 1
    ;;
esac

# Require a second clean read at the replacement boundary. There is no shared
# lock between SDK senders and tmux, so the post-replacement check below still
# detects any non-terminal activity that lands during this boundary.
"$TMUX_BIN" select-pane -d -t "$PANE"
INPUT_DISABLED=true
sleep 0.05
probe="$(turn_probe)"
[ "$probe" = ready ] || {
  record_result "rotation cancelled because new user activity arrived at the replacement boundary; prompt preserved at $RECOVERY"
  exit 1
}

if ! "$TMUX_BIN" respawn-pane -k -t "$PANE" -c "$CWD" "$LAUNCHER"; then
  record_result "pane replacement failed or was not confirmed; prompt preserved at $RECOVERY"
  exit 1
fi
REPLACED=true
"$TMUX_BIN" select-pane -e -t "$PANE"
INPUT_DISABLED=false

seed_probe() {
  [ -r "$STATE/$NEW/events.jsonl" ] || {
    echo "wait"
    return
  }
  /usr/bin/perl -MJSON::PP -e '
    use strict;
    use warnings;
    my ($events, $prompt_path) = @ARGV;
    open my $prompt_fh, "<", $prompt_path or exit 2;
    my $expected = do { local $/; <$prompt_fh> };
    open my $events_fh, "<", $events or exit 2;
    my @messages;
    while (my $line = <$events_fh>) {
      next unless substr($line, -1) eq "\n";
      my $event = eval { decode_json($line) };
      exit 3 unless $event && ref($event) eq "HASH";
      next if defined $event->{agentId};
      next unless ($event->{type} // "") eq "user.message";
      my $data = $event->{data};
      push @messages, $data && ref($data) eq "HASH"
        ? ($data->{content} // "")
        : "";
    }
    if (!@messages) {
      print "wait\n";
    } elsif (@messages == 1 && $messages[0] eq $expected) {
      print "ready\n";
    } else {
      print "cancel\n";
    }
  ' "$STATE/$NEW/events.jsonl" "$RECOVERY"
}

seeded=false
for _ in $(seq 1 1200); do
  seed_status="$(seed_probe)"
  case "$seed_status" in
    ready)
      seeded=true
      break
      ;;
    cancel)
      record_result "pane was replaced for $NEW but its seed or boundary activity was not exact; prompt preserved at $RECOVERY"
      exit 1
      ;;
    wait) ;;
    *)
      record_result "replacement session verification failed; prompt preserved at $RECOVERY"
      exit 1
      ;;
  esac
  sleep 0.25
done

[ "$seeded" = true ] || {
  record_result "pane was replaced for $NEW but its exact seed was not observed; prompt preserved at $RECOVERY"
  exit 1
}

probe="$(turn_probe)"
[ "$probe" = ready ] || {
  record_result "rotated from $OLD to $NEW, but new user activity was recorded in the retired session; prompt preserved at $RECOVERY"
  exit 1
}
seed_status="$(seed_probe)"
[ "$seed_status" = ready ] || {
  record_result "rotated from $OLD to $NEW, but boundary activity was recorded in the replacement session; prompt preserved at $RECOVERY"
  exit 1
}

if rm -f -- "$RECOVERY" "$LAUNCHER"; then
  record_result "rotated from $OLD to $NEW, seeded through tmux process replacement"
  exit 0
fi
record_result "rotated from $OLD to $NEW and seeded, but recovery cleanup failed; prompt preserved at $RECOVERY"
exit 1
