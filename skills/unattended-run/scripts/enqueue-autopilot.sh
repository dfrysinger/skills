#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUEST_CLI="${SESSION_INBOX_REQUEST_CLI:-$SCRIPT_DIR/../../../extensions/session-inbox/request.mjs}"
USAGE="usage: enqueue-autopilot.sh (--target-session ID | --target-tmux NAME) <objective-file>"
TARGET_FLAG="${1:-}"
TARGET="${2:-}"
OBJECTIVE_FILE="${3:-}"
TIMEOUT_SECONDS="${AUTOPILOT_HANDOFF_TIMEOUT_SECONDS:-360}"
OBJECTIVE=""
OBJECTIVE_DIGEST=""
REQUEST_OUTPUT=""
OBJECTIVE_PAYLOAD=""

case "$TARGET_FLAG" in
  --target-session|--target-tmux) ;;
  *) echo "enqueue-autopilot.sh: $USAGE" >&2; exit 64 ;;
esac

[[ -n "$TARGET" && -r "$OBJECTIVE_FILE" ]] || {
  echo "enqueue-autopilot.sh: $USAGE" >&2
  exit 64
}
[[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] &&
  ((TIMEOUT_SECONDS >= 1 && TIMEOUT_SECONDS <= 360)) || {
  echo "enqueue-autopilot.sh: timeout must be between 1 and 360 seconds" >&2
  exit 64
}
[[ -r "$REQUEST_CLI" ]] || {
  echo "enqueue-autopilot.sh: session-inbox request helper is unavailable" >&2
  exit 2
}

if ! OBJECTIVE="$(cat -- "$OBJECTIVE_FILE")" ||
  ! grep -q '[^[:space:]]' <<<"$OBJECTIVE"; then
  echo "enqueue-autopilot.sh: objective file must contain a non-empty objective" >&2
  exit 64
fi
if grep -Fq '<SLOT>' <<<"$OBJECTIVE"; then
  echo "enqueue-autopilot.sh: objective still contains an unresolved <SLOT>" >&2
  exit 64
fi
FIRST_INSTRUCTION="$(awk 'NF { sub(/^[[:space:]]+/, ""); print; exit }' <<<"$OBJECTIVE")"
case "$FIRST_INSTRUCTION" in
  /autopilot*|/goal*)
    echo "enqueue-autopilot.sh: objective file must contain only the objective body" >&2
    exit 64
    ;;
  /allow-all*)
    echo "enqueue-autopilot.sh: permission changes remain user-controlled" >&2
    exit 64
    ;;
esac
if grep -Eq '^[[:space:]]*/allow-all([[:space:]]|$)' <<<"$OBJECTIVE"; then
  echo "enqueue-autopilot.sh: permission changes remain user-controlled" >&2
  exit 64
fi
OBJECTIVE_DIGEST="$(
  printf '%s' "$OBJECTIVE" |
    cksum |
    awk '{print $1 "-" $2}'
)"
[[ "$OBJECTIVE_DIGEST" =~ ^[0-9]+-[0-9]+$ ]] || {
  echo "enqueue-autopilot.sh: could not fingerprint the validated objective" >&2
  exit 2
}

umask 077
RECEIPT_DIR="${HOME}/.copilot/autopilot-enqueue"
mkdir -p "$RECEIPT_DIR"
RECEIPT="${RECEIPT_DIR}/$(date -u +%Y%m%dT%H%M%SZ)-$$.txt"
REQUEST_OUTPUT="$(mktemp "${TMPDIR:-/tmp}/copilot-autopilot-request.XXXXXX")"
OBJECTIVE_PAYLOAD="$(mktemp "${TMPDIR:-/tmp}/copilot-autopilot-objective.XXXXXX")"
printf '%s' "$OBJECTIVE" >"$OBJECTIVE_PAYLOAD"
chmod 600 "$OBJECTIVE_PAYLOAD"

cleanup() {
  rm -f -- "$REQUEST_OUTPUT" "$OBJECTIVE_PAYLOAD"
}
trap cleanup EXIT

finish() {
  local status="$1"
  local detail="$2"
  {
    printf 'status=%s\ntime=%s\ntarget_type=%s\ntarget=%s\ndetail=%s\nobjective_begin\n' \
      "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${TARGET_FLAG#--target-}" "$TARGET" "$detail"
    printf '%s\nobjective_end\nrequest_output_begin\n' "$OBJECTIVE"
    cat -- "$REQUEST_OUTPUT"
    printf 'request_output_end\n'
  } >"$RECEIPT"
  if [[ "$status" != "confirmed" ]] && command -v osascript >/dev/null 2>&1; then
    osascript -e 'display notification "Autopilot handoff failed. The latest receipt in ~/.copilot/autopilot-enqueue contains the objective and SDK result." with title "Copilot unattended run"' >/dev/null 2>&1 || true
  fi
}

if node "$REQUEST_CLI" send \
  "$TARGET_FLAG" "$TARGET" \
  --prompt-file "$OBJECTIVE_PAYLOAD" \
  --agent-mode autopilot \
  --mode immediate \
  --dedupe-key "autopilot:${TARGET_FLAG#--target-}:$TARGET:$OBJECTIVE_DIGEST" \
  --timeout "$TIMEOUT_SECONDS" >"$REQUEST_OUTPUT" 2>&1; then
  if grep -Fq '"delivery":"idle"' "$REQUEST_OUTPUT"; then
    finish "confirmed" "SDK session.send delivered the objective at an idle boundary"
    echo "autopilot handoff confirmed; receipt: $RECEIPT"
    exit 0
  fi
  finish "unconfirmed" "SDK receipt did not prove idle delivery"
  echo "enqueue-autopilot.sh: SDK receipt did not prove idle delivery; receipt: $RECEIPT" >&2
  exit 1
else
  status=$?
fi

finish "failed" "session-inbox request failed with exit status $status"
echo "enqueue-autopilot.sh: SDK handoff failed; receipt: $RECEIPT" >&2
exit "$status"
