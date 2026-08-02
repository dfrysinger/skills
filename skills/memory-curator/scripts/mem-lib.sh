#!/usr/bin/env bash
# mem-lib.sh — shared helpers for the memory-curator scripts.
#
# Locates the authenticated-browse Playwright helper, defines the memory-page
# URL + selectors, and provides a login-check that lets callers no-op cleanly
# when the shared browse session has expired (rather than crashing a headless
# weekly run).
#
# Source this; do not execute.

set -u

MEM_URL="https://github.com/settings/copilot/memory"
MEM_PROFILE="${MEM_PROFILE:-default}"
MEM_STATE_DIR="$HOME/.copilot/skill-state/memory-curator"
MEM_LEDGER="$MEM_STATE_DIR/ledger.jsonl"
# Row selector + the per-row delete affordance (both verified against the live SPA).
MEM_LI_SEL='li[class*=ListItem-module__listItem]'
MEM_DEL_SEL='button[aria-label="Delete memory"]'

mem_locate_pw() {
  # Prints the path to authenticated-browse's pw-session.sh, or empty.
  find "$HOME/.copilot/installed-plugins" -maxdepth 7 -type f \
    -name pw-session.sh -path '*authenticated-browse*' 2>/dev/null | head -1
}

# mem_browse_eval <js-expression> — run one JS expr in page context against the
# memory page, retrying on the profile lock (another browse command may hold it)
# and on empty output. Prints the RAW helper stdout (last {...}/[...] line).
mem_browse_eval() {
  local js="$1" pw out a
  pw="$(mem_locate_pw)"
  [ -x "$pw" ] || { echo "MEM_ERR: authenticated-browse helper not found" >&2; return 3; }
  for a in $(seq 1 8); do
    out="$(bash "$pw" eval "$MEM_PROFILE" "$MEM_URL" "$js" 2>/dev/null | tail -3 | grep -oE '(\{.*\}|\[.*\])' | tail -1)"
    if [ -z "$out" ]; then sleep 12; continue; fi
    printf '%s' "$out"; return 0
  done
  echo "MEM_ERR: browse eval kept failing (locked/empty)" >&2
  return 4
}

# mem_unwrap <raw> — the helper double-JSON-encodes eval output. Emit the inner value.
mem_unwrap() {
  /usr/bin/python3 -c '
import sys,json
raw=sys.stdin.read().strip()
if not raw:
    sys.exit(1)
try:
    d=json.loads(raw)
    if isinstance(d,str): d=json.loads(d)
except Exception:
    try:
        d=json.loads(raw.encode().decode("unicode_escape"))
    except Exception:
        sys.exit(1)
def repair(x):
    if isinstance(x,str):
        try:
            fixed=x.encode("latin-1").decode("utf-8")
            if fixed.count("\ufffd")<=x.count("\ufffd"):
                return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        return x
    if isinstance(x,list): return [repair(i) for i in x]
    if isinstance(x,dict): return {k:repair(v) for k,v in x.items()}
    return x
print(json.dumps(repair(d)))
'
}

# mem_logged_in — returns 0 if the memory page renders as the logged-in user,
# 1 if it looks like a login/redirect page. Cheap title+marker probe.
mem_logged_in() {
  local raw val
  raw="$(mem_browse_eval '(() => JSON.stringify({t:document.title, hasList: !!document.querySelector("'"$MEM_DEL_SEL"'"), signin: /sign in|log in/i.test(document.title)}))')" || return 2
  val="$(printf '%s' "$raw" | mem_unwrap 2>/dev/null)" || return 2
  /usr/bin/python3 -c '
import sys,json
d=json.loads(sys.stdin.read())
# logged in if the memory list control exists OR the title is the memory page and not a signin
ok = bool(d.get("hasList")) or (("memory" in (d.get("t") or "").lower()) and not d.get("signin"))
sys.exit(0 if ok else 1)
' <<<"$val"
}

mem_notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"memory-curator\"" >/dev/null 2>&1 || true
}
