#!/usr/bin/env bash

set -euo pipefail

SKILL="$(cd "$(dirname "$0")/.." && pwd)/SKILL.md"

grep -Fq 'session-inbox extension' "$SKILL"
grep -Fq 'requests native compaction through the session-inbox extension' "$SKILL"
grep -Fq 'queues one local' "$SKILL"
grep -Fq '`/new`, and never retries it' "$SKILL"
grep -Fq '~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-send.sh' \
  "$SKILL"
grep -Fq 'call `self_compact` with that one `brief` argument' "$SKILL"
grep -Fq '~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/rotate-session/scripts/rotate.sh' \
  "$SKILL"
! grep -Eq 'send-keys|paste-buffer|load-buffer|capture-pane|null-steered' "$SKILL"

echo "handoff transport tests: pass"
